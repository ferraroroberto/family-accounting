"""Runtime check that a caller-supplied write target is not beside the code."""

from __future__ import annotations

from pathlib import Path

# Derived here, not imported from config_manager, which imports this module.
_ROOT = Path(__file__).resolve().parents[1]

# Mirrors the default code_folders of [runtime_write_ratchet] in .fleet.toml: the folders
# where runtime output must never land. Gitignored state at the repo root (config.json,
# data/) stays allowed.
CODE_FOLDERS = ("src", "app", "scripts", "hooks", "skills")


def outside_code_folders(path: Path) -> Path:
    """Return ``path`` resolved, or raise ValueError if it is under a code folder.

    The runtime-write ratchet cannot resolve a path passed in as a parameter, so the
    callers that take one (``save_config``, ``connect``) route it through here and the
    guarantee holds at runtime instead of resting on a marker.
    """
    resolved = Path(path).resolve()
    for folder in CODE_FOLDERS:
        if resolved.is_relative_to(_ROOT / folder):
            raise ValueError(f"Refusing to write under the code folder {folder}/: {resolved}")
    return resolved
