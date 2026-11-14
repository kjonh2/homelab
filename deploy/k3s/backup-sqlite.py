"""Create transactionally consistent SQLite copies for the Iku backup job."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


DATABASES = {
    "iku-auth": "/source/auth-db/auth.sqlite3",
    "n8n": "/source/n8n-db/database.sqlite",
    "nextcloud": "/source/nextcloud-db/owncloud.db",
    "k3s-state": "/source/k3s-db/state.db",
}
OUTPUT = Path("/sqlite-backups")
DRISA_DUMP = Path("/source/storage").glob("*/drisa-memory/backups/drisa-memory.dump")


def snapshot(name: str, pattern: str) -> None:
    source_path = Path(pattern)
    if not source_path.is_file():
        raise RuntimeError(f"Expected {name} database at {source_path}")

    print(f"Snapshot starting: {name}", flush=True)
    source_stat = source_path.stat()

    def repair_sidecar_ownership() -> None:
        # The backup init container runs as root to read databases owned by
        # several services. SQLite can create WAL sidecars when opening a
        # read-only source; restore their ownership before and after the
        # snapshot connection is released. Their existing mode is sufficient:
        # a newly created 0600 sidecar becomes writable by its owner after chown.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{source_path}{suffix}")
            try:
                os.chown(sidecar, source_stat.st_uid, source_stat.st_gid)
            except FileNotFoundError:
                continue

    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    output_path = OUTPUT / f"{name}.sqlite3"
    source_connection: sqlite3.Connection | None = None
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(source_uri, uri=True, timeout=60)
        # Opening the source as root may create 0600 WAL sidecars owned by
        # root. Restore the database owner's access immediately, then again
        # after the connection closes in case SQLite recreates either file.
        repair_sidecar_ownership()
        target_connection = sqlite3.connect(output_path, timeout=60)
        source_connection.backup(target_connection, pages=1024, sleep=0.05)
        result = target_connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {name}")
    except sqlite3.Error as exc:
        raise RuntimeError(f"SQLite snapshot failed for {name}: {exc}") from exc
    finally:
        if target_connection is not None:
            target_connection.close()
        if source_connection is not None:
            source_connection.close()
        repair_sidecar_ownership()

    print(f"SQLite snapshot verified: {name}")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        names = sys.argv[1:] or list(DATABASES)
        for name in names:
            if name not in DATABASES:
                raise RuntimeError(f"Unknown SQLite database: {name}")
            snapshot(name, DATABASES[name])
        # PostgreSQL writes a fresh logical dump through the pod's loopback
        # address. Copy it into the same Restic input as SQLite
        # snapshots so restore validation has a stable path.
        if sys.argv[1:] == []:
            dumps = list(DRISA_DUMP)
            if len(dumps) != 1 or not dumps[0].is_file() or dumps[0].stat().st_size == 0:
                raise RuntimeError(f"Expected exactly one non-empty Drisa PostgreSQL dump, found {len(dumps)}")
            shutil.copy2(dumps[0], OUTPUT / "drisa-memory.dump")
            print("PostgreSQL dump copied: drisa-memory", flush=True)
    except Exception as exc:
        print(f"SQLite backup preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
