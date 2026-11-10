# Transaction classification state

Every stored transaction has a classification mode: did a keyword put it in its category, is it a partner contribution, was it pinned by hand, was the pin released. No column holds that mode. Five columns hold it together (`category`, `direction`, `rule`, `partner`, `manual_override`), and four writers set them: the classifier at import, `reclassify_all`, `set_manual_override` and `clear_manual_override`.

`src/tx_state.py` declares the mode once. `TxState` is the closed set of states and `derive_tx_state(row)` is the only function that maps the five columns to one of them. It is also declared in `.fleet.toml` as the `tx_classification` machine, which tells the conventions ratchet that this module owns the state and that any other module re-spelling it is a finding.

## Why it is declared

Before the state existed, each reader tested its own column to answer "is this a contribution?", and the answers disagreed on the same row. A joint-account inflow no keyword matches is stored as category `other`, direction `contribution`, no partner. The per-row split treated it as a neutral contribution, the monthly report dropped it from the expense side without crediting it to anyone, and the dashboard counted it as neither. Two more combinations were reachable that nothing named: a released pin keeps its pinned category, direction and `manual` rule until the next reclassify, and a pin to `contribution` with "(none)" as the partner is a contribution no partner is credited for.

## The states

| State | Columns | Meaning |
|---|---|---|
| `default` | not pinned, rule `default`, direction `expense` | no keyword matched; an ordinary `other` spend |
| `ruled` | not pinned, a keyword rule, direction `expense` | a keyword rule chose the category |
| `personal_income` | not pinned, direction `income` | an inflow on a personal account |
| `contribution` | category `contribution`, partner `partner_a` or `partner_b` | a partner's transfer into the joint account |
| `contribution_no_partner` | category `contribution`, any other partner | a contribution no partner can be credited for |
| `unsorted_joint_inflow` | category `other`, direction `contribution` | a joint inflow no keyword matched: neutral in the split, not a contribution |
| `pinned` | `manual_override = 1` | pinned to an ordinary category |
| `pinned_contribution` | pinned, category `contribution`, partner set | pinned as a contribution |
| `pinned_contribution_no_partner` | pinned, category `contribution`, no partner | pinned as an explicitly neutral contribution |
| `pinned_unsorted_joint_inflow` | pinned, category `other`, direction `contribution` | pinned to `other` on a joint inflow |
| `released` | `manual_override = 0`, rule `manual` | released, still carrying the pinned category until the next reclassify |
| `released_contribution` | released, category `contribution`, partner set | released, still a contribution |
| `released_contribution_no_partner` | released, category `contribution`, no partner | released, still a contribution without a partner |
| `released_unsorted_joint_inflow` | released, category `other`, direction `contribution` | released, still a neutral joint inflow |
| `unknown` | none of the above | the columns contradict each other; the reading carries the reason |

An absent or blank column takes its stored default (category `other`, rule `default`, no partner, not pinned), and an absent direction follows the category the way the classifier assigns it. A row is `unknown` when the direction is outside `expense` / `income` / `contribution`, the category is `contribution` with another direction, the direction is `contribution` on a spend category, a partner sits on a non-contribution row, or `manual_override` is not 0 or 1. No write path produces these; the state exists so such a row is counted instead of read as the nearest ordinary one.

## What reads it

Readers ask a predicate over the state, never a column:

| Reader | Predicate | Meaning |
|---|---|---|
| `app/dashboard.py` `_split_joint_frames` | `is_partner_contribution` | stored in the contribution category |
| `src/reports.py` `monthly_compensation_report`, contribution rows | `is_partner_contribution` | stored in the contribution category |
| `src/reports.py` `monthly_compensation_report`, expense rows | not `is_contribution_direction` | stored with the contribution direction is not an expense |
| `src/calculator.py` `share_for_transaction_row` | `is_contribution_direction` | stored with the contribution direction is split 50/50 |
| `app/dashboard.py` ambiguity caption | `count_ambiguous` | contributions with no partner, released rows, unknown rows |

The two predicates differ on exactly the unsorted joint inflows, which is the disagreement the state makes visible. `tx_states(df)` derives the state of every row of a frame, on the frame's index. A new reader calls these; it does not test `category == "contribution"` or `direction == "contribution"` itself. A mode that needs a fact the columns do not carry adds it to `derive_tx_state`, not to a reader.

## Behaviour it keeps

Declaring the state changes no total. `tests/test_tx_characterisation.py` builds a fixture containing every row kind through the real write paths and pins the monthly report, the dashboard split frames and the per-row split. The dashboard shows the three ambiguous counts as a caption when any is non-zero and leaves every sum as it was.

The derive function reports and never rejects: a stored row is never changed or refused because of its state. A row in `unknown` is read as an ordinary row by both predicates, the legacy answer for a vocabulary the app does not write. Whether the sums should treat an unsorted inflow or a partner-less contribution differently, and whether releasing a pin should reclassify the row, are separate decisions that start from these counts.

## Transitions

A row moves between states only through the four writers.

| Writer | Moves a row |
|---|---|
| import (`classify_full`) | to `default`, `ruled`, `personal_income`, `contribution` or `unsorted_joint_inflow` |
| `reclassify_all` | any unpinned state to an unpinned state; it never touches a pinned row |
| `set_manual_override` | any state to a `pinned*` state; a missing row is refused |
| `clear_manual_override` | a `pinned*` state to the matching `released*` state; a row that is not pinned is refused |

`tests/test_tx_state.py` carries the table test of every column combination and a test per refused move.
