"""SQLite backup/import helpers for ChatVoice runtime data."""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chatvoice.paths import ensure_runtime_dirs, state_paths


class DataBackupError(RuntimeError):
    """Raised when a ChatVoice data backup/import operation cannot proceed."""


@dataclass(frozen=True)
class DataDumpResult:
    source: Path
    output: Path
    bytes: int
    integrity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "output": str(self.output),
            "bytes": self.bytes,
            "integrity": self.integrity,
        }


@dataclass(frozen=True)
class DataImportResult:
    input: Path
    database: Path
    backup: Path | None
    bytes: int
    integrity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": str(self.input),
            "database": str(self.database),
            "backup": str(self.backup) if self.backup else None,
            "bytes": self.bytes,
            "integrity": self.integrity,
        }


def _integrity_check(path: Path) -> str:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            value = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise DataBackupError(f"SQLite integrity check failed for {path}: {exc}") from exc
    result = str(value[0] if value else "")
    if result.lower() != "ok":
        raise DataBackupError(f"SQLite integrity check failed for {path}: {result or 'empty result'}")
    return result


def _backup_sqlite(source: Path, output: Path, *, overwrite: bool = False) -> DataDumpResult:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.exists():
        raise DataBackupError(f"ChatVoice SQLite database does not exist: {source}")
    if output.exists() and not overwrite:
        raise DataBackupError(f"Output already exists: {output}. Pass --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    try:
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
        try:
            dst = sqlite3.connect(str(tmp), timeout=30)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        integrity = _integrity_check(tmp)
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return DataDumpResult(source=source, output=output, bytes=output.stat().st_size, integrity=integrity)


def dump_database(output: str | Path, *, overwrite: bool = False) -> DataDumpResult:
    """Dump the active ChatVoice SQLite database to one consistent file."""

    paths = ensure_runtime_dirs()
    return _backup_sqlite(paths.database_path, Path(output), overwrite=overwrite)


def import_database(input_path: str | Path, *, backup_current: bool = True) -> DataImportResult:
    """Import one SQLite file as the active ChatVoice database.

    This is a local file-level restore operation. Stop the running service before
    importing in production, then restart and verify `/api/heartbeat`.
    """

    paths = ensure_runtime_dirs()
    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        raise DataBackupError(f"Input database file does not exist: {source}")
    integrity = _integrity_check(source)
    database = paths.database_path.expanduser().resolve()
    backup_path: Path | None = None
    if backup_current and database.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = paths.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"meetings-before-import-{stamp}.sqlite3"
        _backup_sqlite(database, backup_path)
    tmp = database.with_name(database.name + ".import-tmp")
    if tmp.exists():
        tmp.unlink()
    try:
        shutil.copy2(source, tmp)
        _integrity_check(tmp)
        os.replace(tmp, database)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return DataImportResult(input=source, database=database, backup=backup_path, bytes=database.stat().st_size, integrity=integrity)


__all__ = ["DataBackupError", "DataDumpResult", "DataImportResult", "dump_database", "import_database"]
