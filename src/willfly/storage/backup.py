"""Atomic, manifest-verified backups for local Willfly state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import shutil
import sqlite3
import tarfile
import tempfile
from typing import Any, Iterable


_SCHEMA = "willfly.state-backup.v0.1"


@dataclass(frozen=True)
class BackupSource:
    """One explicitly named local state path included in a backup."""

    name: str
    path: Path

    def __post_init__(self) -> None:
        if not self.name or self.name in {".", ".."} or "/" in self.name or "\\" in self.name:
            raise ValueError("backup source names must be simple path components")
        if not self.path.exists():
            raise ValueError(f"backup source does not exist: {self.path}")
        if self.path.is_symlink():
            raise ValueError(f"backup source cannot be a symlink: {self.path}")


def create_state_backup(output_path: str | Path, sources: Iterable[BackupSource]) -> dict[str, Any]:
    """Create a verified gzip tar backup without replacing an existing archive.

    SQLite files are copied through SQLite's online backup API. Other files are
    copied into a staging tree first, so the archive is published atomically
    only after its manifest is complete.
    """

    output = Path(output_path)
    source_list = tuple(sources)
    if not source_list:
        raise ValueError("at least one backup source is required")
    if output.exists():
        raise ValueError(f"backup output already exists: {output}")
    names = [source.name for source in source_list]
    if len(set(names)) != len(names):
        raise ValueError("backup source names must be unique")
    output.parent.mkdir(parents=True, exist_ok=True)
    output_resolved = output.resolve()
    for source in source_list:
        source_resolved = source.path.resolve()
        if source_resolved.is_dir() and output_resolved.is_relative_to(source_resolved):
            raise ValueError("backup output cannot be inside a source directory")
        if source_resolved.is_file() and output_resolved == source_resolved:
            raise ValueError("backup output cannot replace a source file")

    temp_root = Path(tempfile.mkdtemp(prefix="willfly-backup-", dir=output.parent))
    temporary_archive = output.parent / f".{output.name}.tmp-{os.getpid()}"
    try:
        staged_state = temp_root / "state"
        staged_state.mkdir()
        for source in source_list:
            _stage_path(source.path, staged_state / source.name)
        entries = _manifest_entries(staged_state)
        manifest = {
            "schema_version": _SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sources": [
                {
                    "name": source.name,
                    "path": str(source.path),
                    "kind": "directory" if source.path.is_dir() else "file",
                }
                for source in source_list
            ],
            "entries": entries,
            "operating_mode": "read_only_state_backup",
            "signing": False,
            "broadcast": False,
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with tarfile.open(temporary_archive, mode="w:gz") as archive:
            archive.add(temp_root / "manifest.json", arcname="manifest.json", recursive=False)
            archive.add(staged_state, arcname="state", recursive=True)
        _validate_archive(temporary_archive)
        os.replace(temporary_archive, output)
        return manifest
    finally:
        if temporary_archive.exists():
            temporary_archive.unlink()
        shutil.rmtree(temp_root, ignore_errors=True)


def restore_state_backup(archive_path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Restore a verified archive into a new directory, never overwriting it."""

    archive = Path(archive_path)
    target = Path(destination)
    if not archive.is_file():
        raise ValueError(f"backup archive does not exist: {archive}")
    if target.exists():
        raise ValueError(f"restore destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="willfly-restore-", dir=target.parent))
    try:
        with tarfile.open(archive, mode="r:gz") as handle:
            members = handle.getmembers()
            _validate_members(members)
            for member in members:
                if member.name == "manifest.json":
                    extracted = handle.extractfile(member)
                    if extracted is None:
                        raise ValueError("backup manifest is unreadable")
                    (temporary / "manifest.json").write_bytes(extracted.read())
                    continue
                relative = _safe_relative(member.name)
                destination_path = temporary / relative
                if member.isdir():
                    destination_path.mkdir(parents=True, exist_ok=True)
                    continue
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                extracted = handle.extractfile(member)
                if extracted is None:
                    raise ValueError(f"backup member is unreadable: {member.name}")
                with destination_path.open("wb") as output_file:
                    shutil.copyfileobj(extracted, output_file)
                destination_path.chmod(member.mode & 0o777)
        try:
            manifest = json.loads((temporary / "manifest.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ValueError("backup manifest is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("schema_version") != _SCHEMA:
            raise ValueError("unsupported backup manifest schema")
        _verify_manifest(temporary, manifest)
        os.replace(temporary, target)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _stage_path(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"backup source cannot contain symlinks: {source}")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(source, destination)
        return
    if not source.is_dir():
        raise ValueError(f"unsupported backup source type: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        if _is_sqlite_sidecar(child):
            # The main file was copied through sqlite3.Connection.backup;
            # transient WAL/SHM files must not be restored beside that snapshot.
            continue
        _stage_path(child, destination / child.name)


def _copy_file(source: Path, destination: Path) -> None:
    if source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        try:
            with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
                source_connection.backup(destination_connection)
            shutil.copystat(source, destination)
            return
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"SQLite backup failed for {source}") from exc
    shutil.copy2(source, destination)


def _is_sqlite_sidecar(path: Path) -> bool:
    if not path.name.endswith(("-wal", "-shm")):
        return False
    database_name = path.name.rsplit("-", 1)[0]
    return Path(database_name).suffix.lower() in {".sqlite", ".sqlite3", ".db"}


def _manifest_entries(staged_state: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((item for item in staged_state.rglob("*") if item.is_file()), key=lambda item: str(item)):
        relative = PurePosixPath("state", *path.relative_to(staged_state).parts).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "size": path.stat().st_size, "sha256": digest})
    return entries


def _validate_archive(archive_path: Path) -> None:
    with tarfile.open(archive_path, mode="r:gz") as handle:
        members = handle.getmembers()
        _validate_members(members)
        names = {member.name for member in members}
        if "manifest.json" not in names or "state" not in names:
            raise ValueError("backup archive is missing manifest or state root")


def _validate_members(members: Iterable[tarfile.TarInfo]) -> None:
    names: set[str] = set()
    for member in members:
        if member.name in names:
            raise ValueError(f"backup archive contains duplicate member: {member.name}")
        names.add(member.name)
        if member.name != "manifest.json" and not member.name.startswith("state/") and member.name != "state":
            raise ValueError(f"backup archive contains an unexpected member: {member.name}")
        if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
            raise ValueError(f"backup archive contains an unsafe member: {member.name}")
        _safe_relative(member.name)


def _safe_relative(name: str) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
        raise ValueError(f"unsafe backup path: {name}")
    return Path(*pure.parts)


def _verify_manifest(root: Path, manifest: dict[str, Any]) -> None:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("backup manifest entries are invalid")
    expected: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("backup manifest entry is invalid")
        relative = _safe_relative(entry["path"])
        if not entry["path"].startswith("state/") or entry["path"] in expected:
            raise ValueError("backup manifest contains an invalid or duplicate path")
        expected.add(entry["path"])
        path = root / relative
        if not path.is_file() or path.stat().st_size != entry.get("size"):
            raise ValueError(f"backup file size mismatch: {entry['path']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise ValueError(f"backup file hash mismatch: {entry['path']}")
        if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            try:
                with sqlite3.connect(path) as connection:
                    result = connection.execute("PRAGMA quick_check").fetchone()
            except sqlite3.DatabaseError as exc:
                raise ValueError(f"restored SQLite state is invalid: {entry['path']}") from exc
            if not result or result[0] != "ok":
                raise ValueError(f"restored SQLite state failed quick_check: {entry['path']}")
    actual = {
        PurePosixPath("state", *path.relative_to(root / "state").parts).as_posix()
        for path in (root / "state").rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError("backup manifest does not cover the restored state")


__all__ = ["BackupSource", "create_state_backup", "restore_state_backup"]
