import base64
import os
import struct
import tempfile
import unittest
from pathlib import Path

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="drisa-gateway-test-")
os.environ["DRISA_HOME"] = _TEST_ROOT.name
os.environ["DRISA_VAULT_PATH"] = str(Path(_TEST_ROOT.name) / "vault")

from drisa_voice_gateway import MAX_AUDIO_BYTES, decode_audio_payload


class AudioPayloadTests(unittest.TestCase):
    @staticmethod
    def make_wav(payload: bytes) -> bytes:
        return b"RIFF" + struct.pack("<I", len(payload) + 36) + b"WAVE" + b"\0" * 32 + payload

    def test_decodes_bounded_wave(self):
        wav = self.make_wav(b"\0\0" * 160)
        self.assertEqual(decode_audio_payload(base64.b64encode(wav).decode("ascii")), wav)

    def test_rejects_malformed_base64(self):
        with self.assertRaises(ValueError):
            decode_audio_payload("%%%not-base64%%")

    def test_rejects_non_wave_payload(self):
        with self.assertRaises(ValueError):
            decode_audio_payload(base64.b64encode(b"not a wav file").decode("ascii"))

    def test_rejects_inconsistent_riff_length(self):
        wav = bytearray(self.make_wav(b"\0\0" * 4))
        wav[4:8] = struct.pack("<I", 1)
        with self.assertRaises(ValueError):
            decode_audio_payload(base64.b64encode(wav).decode("ascii"))

    def test_rejects_payload_above_limit_before_decoding(self):
        encoded = "A" * (((MAX_AUDIO_BYTES + 2) // 3) * 4 + 4)
        with self.assertRaises(ValueError):
            decode_audio_payload(encoded)


def tearDownModule():
    _TEST_ROOT.cleanup()


if __name__ == "__main__":
    unittest.main()
