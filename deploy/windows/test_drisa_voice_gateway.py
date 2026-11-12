import asyncio
import base64
import json
import os
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="drisa-gateway-test-")
os.environ["DRISA_HOME"] = _TEST_ROOT.name
os.environ["DRISA_VAULT_PATH"] = str(Path(_TEST_ROOT.name) / "vault")

import drisa_voice_gateway as gateway
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

    def test_llm_echo_is_not_returned_for_tts(self):
        import requests

        utterance = "Qual é o estado dos meus serviços agora?"

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": utterance}}]}

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={
                "llm_model": "test-model",
                "llm_url": "http://127.0.0.1:1/v1",
                "llm_key": "",
            }),
            patch.object(requests, "post", return_value=FakeResponse()),
        ):
            self.assertEqual(gateway.llm_reply(utterance), "")


class GatewayAsyncAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_inference_does_not_block_websocket_event_loop(self):
        wav = b"RIFF" + struct.pack("<I", 4) + b"WAVE"
        config = {
            "allowlist": ["test-device"],
            "policies": {"test-device": {"transcribe": True, "reply": True}},
            "unknown": {"transcribe": False, "reply": False},
        }

        class FakeWebSocket:
            remote_address = "test"

            def __init__(self):
                self.messages = iter([
                    json.dumps({"type": "hello", "device_id": "test-device", "token": "test-token"}),
                    json.dumps({"type": "audio", "audio_b64": base64.b64encode(wav).decode("ascii")}),
                ])
                self.sent = []

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    raise StopAsyncIteration

            async def send(self, message):
                self.sent.append(json.loads(message))

        def slow(value):
            time.sleep(0.08)
            return value

        socket = FakeWebSocket()
        ticks = 0
        finished = asyncio.Event()

        async def heartbeat():
            nonlocal ticks
            while not finished.is_set():
                ticks += 1
                await asyncio.sleep(0.01)

        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.object(gateway, "load_token", return_value="test-token"),
            patch.object(gateway, "transcribe", side_effect=lambda _: slow("hello")),
            patch.object(gateway, "llm_reply", side_effect=lambda _: slow("reply")),
            patch.object(gateway, "tts_kokoro", side_effect=lambda _: slow(b"wav")),
            patch.object(gateway, "log_to_obsidian"),
            patch.object(gateway, "send_to_drisa"),
        ):
            heartbeat_task = asyncio.create_task(heartbeat())
            await asyncio.wait_for(gateway.handle_client(socket), timeout=2)
            finished.set()
            await heartbeat_task

        self.assertGreaterEqual(ticks, 5)
        self.assertEqual([message["type"] for message in socket.sent], ["auth", "transcript", "reply", "tts"])


def tearDownModule():
    _TEST_ROOT.cleanup()


if __name__ == "__main__":
    unittest.main()
