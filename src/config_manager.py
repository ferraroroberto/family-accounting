"""Load and validate JSON configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "partners",
        "income",
        "categories",
        "classification_rules",
        "accounts",
    ],
    "properties": {
        "partners": {"type": "object"},
        "income": {"type": "object"},
        "categories": {"type": "object"},
        "classification_rules": {"type": "object"},
        "accounts": {"type": "object"},
        "bank_imports": {"type": "object"},
    },
    "additionalProperties": True,
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    return project_root() / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or default_config_path()
    if not p.is_file():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    Draft202012Validator(CONFIG_SCHEMA).validate(data)
    return data


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Validate and write configuration to disk."""
    p = path or default_config_path()
    Draft202012Validator(CONFIG_SCHEMA).validate(data)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_path(cfg: dict[str, Any], relative: str) -> Path:
    """Resolve a path from config relative to project root.

    ``base_directory`` may be absolute (e.g. a synced OneDrive folder), in which
    case it wins over the project root — standard ``pathlib`` join semantics.
    """
    base = cfg.get("bank_imports", {}).get("base_directory")
    root = project_root()
    if base:
        return (root / base / relative).resolve()
    return (root / relative).resolve()


def resolve_source_file(cfg: dict[str, Any], relative: str) -> Path:
    """Resolve a ``bank_imports.sources[].file`` entry to one concrete file.

    Plain paths resolve exactly as :func:`resolve_path`. When the entry contains
    a glob wildcard (``*`` or ``?``) the newest match by modification time is
    returned, so a dated export (``..._2026-04-01_2026-08-24.XLS``) can be dropped
    into the source folder without editing the config each cycle.

    Raises FileNotFoundError when a pattern matches nothing, naming the directory
    and the pattern — a silent skip here would look like "no new transactions".
    """
    if not any(ch in relative for ch in "*?"):
        return resolve_path(cfg, relative)

    target = resolve_path(cfg, relative)
    directory, pattern = target.parent, target.name
    matches = [p for p in directory.glob(pattern) if p.is_file()]
    if not matches:
        raise FileNotFoundError(
            f"No file matching '{pattern}' in {directory}. "
            "Download the export into that folder, or fix the pattern in config.json."
        )
    return max(matches, key=lambda p: p.stat().st_mtime)


def partner_names(cfg: dict[str, Any]) -> tuple[str, str]:
    """Return ``(partner_a_name, partner_b_name)`` from config, with fallbacks."""
    pa = cfg.get("partners", {}).get("partner_a", {}).get("name", "Partner A")
    pb = cfg.get("partners", {}).get("partner_b", {}).get("name", "Partner B")
    return pa, pb
