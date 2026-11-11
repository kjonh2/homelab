"""Create transactionally consistent SQLite copies for the Iku backup job."""

from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote


DATABASES = {
    "iku-auth": "/source/storage/pvc-*_iku_iku-auth-data/auth.sqlite3",
    "n8n": "/source/storage/pvc-*_iku_n8n-data/database.sqlite",
    "nextcloud": "/source/nextcloud-db/owncloud.db",
    "k3s-state": "/source/k3s-server/db/state.db",
}
OUTPUT = Path("/sqlite-backups")


def snapshot(name: str, pattern: str) -> None:
    matches = glob.glob(pattern)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} database; found {len(matches)}")

    source_path = Path(matches[0])
    print(f"Snapshot starting: {name}")
    source_uri = f"file:{quote(str(source_path), safe='/')}?mode=ro"
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
        for name, pattern in DATABASES.items():
            snapshot(name, pattern)
    except Exception as exc:
        print(f"SQLite backup preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
