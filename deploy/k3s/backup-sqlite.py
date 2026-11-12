"""Create transactionally consistent SQLite copies for the Iku backup job."""

from __future__ import annotations

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


def snapshot(name: str, pattern: str) -> None:
    source_path = Path(pattern)
    if not source_path.is_file():
        raise RuntimeError(f"Expected {name} database at {source_path}")

    print(f"Snapshot starting: {name}", flush=True)
    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    output_path = OUTPUT / f"{name}.sqlite3"
    try:
        source_connection = sqlite3.connect(source_uri, uri=True, timeout=60)
    except sqlite3.Error as exc:
        raise RuntimeError(f"Cannot open {name} source {source_path}: {exc}") from exc
    try:
        target_connection = sqlite3.connect(output_path, timeout=60)
    except sqlite3.Error as exc:
        source_connection.close()
        raise RuntimeError(f"Cannot open {name} snapshot {output_path}: {exc}") from exc

    with source_connection as source:
        with target_connection as target:
            try:
                source.backup(target, pages=1024, sleep=0.05)
                result = target.execute("PRAGMA integrity_check").fetchone()
            except sqlite3.Error as exc:
                raise RuntimeError(f"SQLite operation failed for {name}: {exc}") from exc
            if not result or result[0] != "ok":
                raise RuntimeError(f"SQLite integrity check failed for {name}")

    print(f"SQLite snapshot verified: {name}")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        names = sys.argv[1:] or list(DATABASES)
        for name in names:
            if name not in DATABASES:
                raise RuntimeError(f"Unknown SQLite database: {name}")
            snapshot(name, DATABASES[name])
    except Exception as exc:
        print(f"SQLite backup preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
