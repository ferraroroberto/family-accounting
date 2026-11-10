"""The classification state of one stored transaction, derived in one place.

A transaction's classification mode is held by five columns together: ``category``,
``direction``, ``rule``, ``partner`` and ``manual_override``. Four writers set them
(the classifier at import, ``reclassify_all``, ``set_manual_override`` and
``clear_manual_override``), so a reader that tests one column sees only part of the
mode. :func:`derive_tx_state` maps a row to one closed :class:`TxState`; every reader
asks that, or one of the predicates below, instead of testing a column itself.

The derive function reports, it never rejects: a stored row is never changed or
refused because of its state. A row whose columns fit no state is ``UNKNOWN`` with a
reason, so the odd row is counted rather than read as the nearest ordinary one.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class TxState(Enum):
    """Every classification state a stored transaction can be in."""

    # Classified by the importer or by the last reclassify (no pin, no manual rule).
    DEFAULT = "default"  # no keyword matched; stored as an ordinary 'other' spend
    RULED = "ruled"  # a keyword rule put the row in its category
    PERSONAL_INCOME = "personal_income"  # an inflow on a personal account
    CONTRIBUTION = "contribution"  # a partner's transfer into the joint account, partner attributed
    CONTRIBUTION_NO_PARTNER = "contribution_no_partner"  # a contribution no partner can be credited for
    UNSORTED_JOINT_INFLOW = "unsorted_joint_inflow"  # a joint inflow no keyword matched; neutral, not a contribution

    # Pinned: manual_override = 1, shielded from reclassify.
    PINNED = "pinned"  # pinned to an ordinary category
    PINNED_CONTRIBUTION = "pinned_contribution"  # pinned as a contribution with a partner
    PINNED_CONTRIBUTION_NO_PARTNER = "pinned_contribution_no_partner"  # pinned as a contribution, partner (none)
    PINNED_UNSORTED_JOINT_INFLOW = "pinned_unsorted_joint_inflow"  # pinned to 'other' on a joint inflow

    # Released: manual_override cleared but the pinned columns kept until the next reclassify.
    RELEASED = "released"  # released, still carrying the pinned category
    RELEASED_CONTRIBUTION = "released_contribution"  # released, still a contribution with a partner
    RELEASED_CONTRIBUTION_NO_PARTNER = "released_contribution_no_partner"  # released, still a contribution without one
    RELEASED_UNSORTED_JOINT_INFLOW = "released_unsorted_joint_inflow"  # released, still a neutral joint inflow

    UNKNOWN = "unknown"  # the columns fit no state above; the reading carries why


@dataclass(frozen=True)
class TxReading:
    """A derived state and, for ``UNKNOWN``, why no other state fits."""

    state: TxState
    reason: str = ""


@dataclass(frozen=True)
class AmbiguousCounts:
    """Rows whose stored mode is ambiguous; shown to the user, never used to change a sum."""

    contribution_without_partner: int
    released_not_reclassified: int
    unknown: int


_CONTRIBUTION = "contribution"
_OTHER = "other"
_MANUAL_RULE = "manual"
_DEFAULT_RULE = "default"
_EXPENSE = "expense"
_PARTNERS = ("partner_a", "partner_b")
_DIRECTIONS = (_EXPENSE, "income", _CONTRIBUTION)

# Rows the Dashboard and the monthly report credit to a partner (category == contribution).
PARTNER_CONTRIBUTION_STATES = frozenset(
    {
        TxState.CONTRIBUTION,
        TxState.CONTRIBUTION_NO_PARTNER,
        TxState.PINNED_CONTRIBUTION,
        TxState.PINNED_CONTRIBUTION_NO_PARTNER,
        TxState.RELEASED_CONTRIBUTION,
        TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
    }
)

# Rows stored with direction == contribution: the partner contributions plus the unsorted joint inflows.
CONTRIBUTION_DIRECTION_STATES = PARTNER_CONTRIBUTION_STATES | frozenset(
    {
        TxState.UNSORTED_JOINT_INFLOW,
        TxState.PINNED_UNSORTED_JOINT_INFLOW,
        TxState.RELEASED_UNSORTED_JOINT_INFLOW,
    }
)

_CONTRIBUTION_NO_PARTNER_STATES = frozenset(
    {
        TxState.CONTRIBUTION_NO_PARTNER,
        TxState.PINNED_CONTRIBUTION_NO_PARTNER,
        TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
    }
)

_RELEASED_STATES = frozenset(
    {
        TxState.RELEASED,
        TxState.RELEASED_CONTRIBUTION,
        TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
        TxState.RELEASED_UNSORTED_JOINT_INFLOW,
    }
)

# (role, provenance) -> state, for every pairing except an unpinned ordinary row, which
# depends on the rule and the direction.
_ROLE_PROVENANCE: dict[tuple[str, str], TxState] = {
    ("contribution", "auto"): TxState.CONTRIBUTION,
    ("contribution", "pinned"): TxState.PINNED_CONTRIBUTION,
    ("contribution", "released"): TxState.RELEASED_CONTRIBUTION,
    ("no_partner", "auto"): TxState.CONTRIBUTION_NO_PARTNER,
    ("no_partner", "pinned"): TxState.PINNED_CONTRIBUTION_NO_PARTNER,
    ("no_partner", "released"): TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
    ("unsorted", "auto"): TxState.UNSORTED_JOINT_INFLOW,
    ("unsorted", "pinned"): TxState.PINNED_UNSORTED_JOINT_INFLOW,
    ("unsorted", "released"): TxState.RELEASED_UNSORTED_JOINT_INFLOW,
    ("plain", "pinned"): TxState.PINNED,
    ("plain", "released"): TxState.RELEASED,
}


def is_partner_contribution(state: TxState) -> bool:
    """True when the row is stored in the contribution category."""
    return state in PARTNER_CONTRIBUTION_STATES


def is_contribution_direction(state: TxState) -> bool:
    """True when the row is stored with the contribution direction (neutral in the split, not an expense)."""
    return state in CONTRIBUTION_DIRECTION_STATES


def _field(row: Any, key: str) -> Any:
    """The column value, or ``None`` when the row lacks it or holds a blank or NaN."""
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _text(row: Any, key: str) -> str | None:
    value = _field(row, key)
    return None if value is None else str(value).strip()


def _pin_flag(row: Any) -> int | None:
    """``manual_override`` as 0 or 1 (an absent column is 0); ``None`` when it holds anything else."""
    value = _field(row, "manual_override")
    if value is None:
        return 0
    try:
        flag = int(value)
    except (TypeError, ValueError):
        return None
    return flag if flag in (0, 1) and flag == value else None


def _unknown(reason: str) -> TxReading:
    return TxReading(TxState.UNKNOWN, reason)


def _role(category: str, direction: str, partner: str | None) -> str:
    if category == _CONTRIBUTION:
        return "contribution" if partner in _PARTNERS else "no_partner"
    if direction == _CONTRIBUTION:
        return "unsorted"
    return "plain"


def _inconsistency(category: str, direction: str, partner: str | None) -> str | None:
    """Why the classification columns contradict each other, or ``None`` when they agree."""
    if direction not in _DIRECTIONS:
        return f"direction {direction!r} is not one of {', '.join(_DIRECTIONS)}"
    if category == _CONTRIBUTION and direction != _CONTRIBUTION:
        return f"category is {_CONTRIBUTION} but direction is {direction}"
    if direction == _CONTRIBUTION and category not in (_CONTRIBUTION, _OTHER):
        return f"direction is {_CONTRIBUTION} on the {category} category"
    if partner and category != _CONTRIBUTION:
        return f"partner {partner} is set on a {category} row"
    return None


def derive_tx_state(row: Any) -> TxReading:
    """Map one transaction row to its state.

    *row* is anything indexable by column name (a dict, ``sqlite3.Row`` or pandas
    row). An absent or blank column takes the stored default (category ``other``, rule
    ``default``, no partner, not pinned); an absent direction follows the category the
    way the classifier assigns it.
    """
    category = _text(row, "category") or _OTHER
    direction = _text(row, "direction") or (_CONTRIBUTION if category == _CONTRIBUTION else _EXPENSE)
    rule = _text(row, "rule") or _DEFAULT_RULE
    partner = _text(row, "partner")
    pinned = _pin_flag(row)
    if pinned is None:
        return _unknown(f"manual_override {_field(row, 'manual_override')!r} is not 0 or 1")
    reason = _inconsistency(category, direction, partner)
    if reason:
        return _unknown(reason)

    role = _role(category, direction, partner)
    if pinned:
        provenance = "pinned"
    elif rule == _MANUAL_RULE:
        provenance = "released"
    else:
        provenance = "auto"
    if (role, provenance) in _ROLE_PROVENANCE:
        return TxReading(_ROLE_PROVENANCE[(role, provenance)])
    if direction == "income":
        return TxReading(TxState.PERSONAL_INCOME)
    return TxReading(TxState.DEFAULT if rule == _DEFAULT_RULE else TxState.RULED)


def tx_states(df: pd.DataFrame) -> pd.Series:
    """The derived state of every row of *df*, on *df*'s index."""
    return pd.Series([derive_tx_state(r).state for r in df.to_dict("records")], index=df.index, dtype=object)


def count_ambiguous(states: Iterable[TxState]) -> AmbiguousCounts:
    """Count the rows whose stored mode is ambiguous."""
    no_partner = released = unknown = 0
    for state in states:
        if state in _CONTRIBUTION_NO_PARTNER_STATES:
            no_partner += 1
        if state in _RELEASED_STATES:
            released += 1
        if state is TxState.UNKNOWN:
            unknown += 1
    return AmbiguousCounts(no_partner, released, unknown)
