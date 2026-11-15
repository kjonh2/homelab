import logging
import tempfile
import unittest
from pathlib import Path

from drisa_log_rotation import append_rotating_text, create_rotating_file_handler


class DrisaLogRotationTests(unittest.TestCase):
    def test_text_log_keeps_only_configured_backups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log = Path(temp_dir) / "drisa.log"
            for message in ("aaaa", "bbbb", "cccc", "dddd"):
                append_rotating_text(log, message, max_bytes=5, backup_count=2)

            self.assertEqual(log.read_text(encoding="utf-8"), "dddd\n")
            self.assertEqual(log.with_name("drisa.log.1").read_text(encoding="utf-8"), "cccc\n")
            self.assertEqual(log.with_name("drisa.log.2").read_text(encoding="utf-8"), "bbbb\n")
            self.assertFalse(log.with_name("drisa.log.3").exists())

    def test_file_handler_rotates_and_uses_utf8(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log = Path(temp_dir) / "drisa.log"
            handler = create_rotating_file_handler(log, max_bytes=5, backup_count=1)
            try:
                handler.emit(logging.makeLogRecord({"msg": "áá", "levelno": logging.INFO}))
                handler.emit(logging.makeLogRecord({"msg": "bbbb", "levelno": logging.INFO}))
                handler.flush()
            finally:
                handler.close()

            self.assertEqual(log.read_text(encoding="utf-8"), "bbbb\n")
            self.assertEqual(log.with_name("drisa.log.1").read_text(encoding="utf-8"), "áá\n")


if __name__ == "__main__":
    unittest.main()
