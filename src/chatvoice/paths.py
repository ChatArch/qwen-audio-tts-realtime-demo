"""Runtime path and database configuration for ChatVoice."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved ChatVoice runtime paths under ChatArch home."""

    root: Path
    data_dir: Path
    logs_dir: Path
    run_dir: Path
    temp_dir: Path
    model_cache_dir: Path
    database_path: Path

    def as_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def state_root(*, chatarch_home: str | Path | None = None, chatvoice_home: str | Path | None = None) -> Path:
    """Return the ChatVoice state root.

    Precedence is explicit ``chatvoice_home`` > ``CHATVOICE_RUNTIME_ROOT`` >
    ``CHATVOICE_HOME`` > explicit/ENV ``CHATARCH_HOME`` + ``chatvoice`` >
    ``~/.chatarch/chatvoice``.
    """

    explicit_chatvoice = chatvoice_home or os.getenv("CHATVOICE_RUNTIME_ROOT", "").strip() or os.getenv("CHATVOICE_HOME", "").strip()
    if explicit_chatvoice:
        return _expand_path(explicit_chatvoice)
    home = chatarch_home or os.getenv("CHATARCH_HOME", "").strip() or (Path.home() / ".chatarch")
    return _expand_path(home) / "chatvoice"


def state_paths(*, chatarch_home: str | Path | None = None, chatvoice_home: str | Path | None = None) -> RuntimePaths:
    """Resolve all local ChatVoice runtime directories without creating them."""

    root = state_root(chatarch_home=chatarch_home, chatvoice_home=chatvoice_home)
    data_dir = root / "data"
    return RuntimePaths(
        root=root,
        data_dir=data_dir,
        logs_dir=root / "logs",
        run_dir=root / "run",
        temp_dir=root / "temp",
        model_cache_dir=root / "model-cache",
        database_path=Path(
            os.getenv("MEETING_DB_PATH", "").strip()
            or os.getenv("CHATVOICE_SQLITE_PATH", "").strip()
            or data_dir / "meetings.sqlite3"
        ).expanduser(),
    )


def ensure_runtime_dirs(paths: RuntimePaths | None = None) -> RuntimePaths:
    """Create runtime directories and return the resolved paths."""

    resolved = paths or state_paths()
    for directory in (resolved.root, resolved.data_dir, resolved.logs_dir, resolved.run_dir, resolved.temp_dir, resolved.model_cache_dir):
        directory.mkdir(parents=True, exist_ok=True)
    resolved.database_path.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def database_settings() -> dict[str, object]:
    """Return a sanitized database configuration summary.

    ChatVoice stores its packaged web data in one SQLite database file. Backup
    and migration use file-level SQLite dumps/imports; there is no separate
    database URL configuration in the ChatVoice ChatEnv schema.
    """

    paths = state_paths()
    configured = bool(os.getenv("MEETING_DB_PATH", "").strip() or os.getenv("CHATVOICE_SQLITE_PATH", "").strip())
    return {
        "configured": configured,
        "backend": "sqlite",
        "supported_by_packaged_web_app": True,
        "sqlite_path": str(paths.database_path),
        "backup_unit": "single-sqlite-file",
        "concurrency": "single-node-wal",
        "note": "ChatVoice uses one SQLite database file. Use `chatvoice data dump` to create a consistent single-file backup and `chatvoice data import` to restore one.",
    }


__all__ = ["RuntimePaths", "database_settings", "ensure_runtime_dirs", "state_paths", "state_root"]
