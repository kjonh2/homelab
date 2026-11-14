"""Bounded log helpers for Drisa's long-running Windows processes."""

from __future__ import annotations

import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


_TEXT_LOG_LOCK = threading.Lock()
DEFAULT_MAX_LOG_BYTES = 8 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 4


def create_rotating_file_handler(
    filename: str | os.PathLike[str],
    *,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUPS,
) -> RotatingFileHandler:
    """Create a UTF-8 file handler with a fixed number of size-based backups."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if backup_count < 1:
        raise ValueError("backup_count must be at least one")
    return RotatingFileHandler(
        filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )


def append_rotating_text(
    filename: str | os.PathLike[str],
    message: str,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Append one UTF-8 line and rotate the oldest backup when the file is full."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if backup_count < 1:
        raise ValueError("backup_count must be at least one")

    path = Path(filename)
    normalized_message = message.rstrip("\r\n")
    line = f"{normalized_message}\n"
    line_bytes = len(line.encode("utf-8"))
    with _TEXT_LOG_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            current_bytes = path.stat().st_size
        except FileNotFoundError:
            current_bytes = 0

        if current_bytes and current_bytes + line_bytes > max_bytes:
            for index in range(backup_count, 0, -1):
                source = path if index == 1 else path.with_name(f"{path.name}.{index - 1}")
                destination = path.with_name(f"{path.name}.{index}")
                if source.exists():
                    os.replace(source, destination)

        with path.open("a", encoding="utf-8", newline="") as log_file:
            log_file.write(line)
