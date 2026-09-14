import json
import sqlite3

import pytest

from willfly.storage.backup import BackupSource, create_state_backup, restore_state_backup


def test_state_backup_round_trips_sqlite_and_regular_files(tmp_path) -> None:
    source_dir = tmp_path / "state"
    source_dir.mkdir()
    database = source_dir / "feedback.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES ('durable')")
    (source_dir / "feedback.sqlite3-wal").write_bytes(b"transient sidecar")
    notes = source_dir / "notes.json"
    notes.write_text(json.dumps({"read_only": True}) + "\n", encoding="utf-8")
    archive = tmp_path / "state-backup.tar.gz"

    manifest = create_state_backup(archive, [BackupSource("feedback", source_dir)])
    assert manifest["schema_version"] == "willfly.state-backup.v0.1"
    assert len(manifest["entries"]) == 2
    assert all(not entry["path"].endswith(("-wal", "-shm")) for entry in manifest["entries"])
    restored = tmp_path / "restored"
    restored_manifest = restore_state_backup(archive, restored)
    assert restored_manifest["entries"] == manifest["entries"]
    with sqlite3.connect(restored / "state" / "feedback" / "feedback.sqlite3") as connection:
        assert connection.execute("SELECT value FROM values_table").fetchone()[0] == "durable"
    assert (restored / "state" / "feedback" / "notes.json").read_text(encoding="utf-8").endswith("\n")


def test_state_backup_and_restore_refuse_overwrite_and_symlinks(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("value", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    create_state_backup(archive, [BackupSource("source", source)])
    with pytest.raises(ValueError, match="already exists"):
        create_state_backup(archive, [BackupSource("source", source)])
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        restore_state_backup(archive, existing)

    symlink = source / "link"
    try:
        symlink.symlink_to(source / "value.txt")
    except OSError:
        pytest.skip("symlinks are unavailable in this environment")
    with pytest.raises(ValueError, match="symlink"):
        create_state_backup(tmp_path / "symlink.tar.gz", [BackupSource("source", source)])
