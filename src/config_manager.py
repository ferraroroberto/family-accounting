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
    """Resolve a path from config relative to project root."""
    base = cfg.get("bank_imports", {}).get("base_directory")
    root = project_root()
    if base:
        return (root / base / relative).resolve()
    return (root / relative).resolve()
