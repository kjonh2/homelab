import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

_TEST_HOME = tempfile.TemporaryDirectory(prefix="drisa-voice-test-")
os.environ["DRISA_HOME"] = _TEST_HOME.name

import voice_loop_local as voice
from cryptography.fernet import Fernet
import requests


class VoiceLoopTests(unittest.TestCase):
    def test_gaming_stt_uses_dedicated_audio_endpoint_and_selected_model(self):
        class ModelsResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "moss", "loaded": True}]}

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"text": "Olá Kiko."}

        old_url, old_model = voice.STT_URL, voice.STT_MODEL
        voice.STT_URL, voice.STT_MODEL = "http://127.0.0.1:8766/v1", "moss"
        try:
            with tempfile.TemporaryDirectory(prefix="drisa-gaming-stt-test-") as directory:
                wav_path = Path(directory) / "input.wav"
                wav_path.write_bytes(b"RIFF-test")
                with (
                    patch.object(voice.requests, "get", return_value=ModelsResponse()),
                    patch.object(voice.requests, "post", return_value=FakeResponse()) as post,
                ):
                    transcript, _ = voice.stt_unsloth(str(wav_path))
            self.assertEqual(transcript, "Olá Kiko.")
            self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8766/v1/audio/transcriptions")
            self.assertEqual(post.call_args.kwargs["data"]["model"], "moss")
        finally:
            voice.STT_URL, voice.STT_MODEL = old_url, old_model

    def test_gaming_stt_loads_unloaded_fallback_model(self):
        class ModelsResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "parakeet", "loaded": False}]}

        class LoadResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"id": "parakeet", "loaded": True}

        class TranscriptionResponse(LoadResponse):
            @staticmethod
            def json():
                return {"text": "Teste do Parakeet."}

        old_url = voice.STT_URL
        voice.STT_URL = "http://127.0.0.1:8766/v1"
        try:
            with tempfile.TemporaryDirectory(prefix="drisa-gaming-stt-test-") as directory:
                wav_path = Path(directory) / "input.wav"
                wav_path.write_bytes(b"RIFF-test")
                with (
                    patch.object(voice.requests, "get", return_value=ModelsResponse()),
                    patch.object(voice.requests, "post", side_effect=[LoadResponse(), TranscriptionResponse()]) as post,
                ):
                    transcript, _ = voice.stt_unsloth(str(wav_path), "parakeet")
            self.assertEqual(transcript, "Teste do Parakeet.")
            self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:8766/v1/models/load")
            self.assertEqual(post.call_args_list[0].kwargs["json"], {
                "id": "parakeet", "package_id": "parakeet_tdt_q8_0", "task": "asr",
            })
            self.assertEqual(post.call_args_list[1].args[0], "http://127.0.0.1:8766/v1/audio/transcriptions")
        finally:
            voice.STT_URL = old_url

    def test_gaming_tts_uses_dedicated_audio_endpoint_and_kokoro(self):
        class ModelsResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "kokoro", "loaded": True}]}

        class FakeResponse:
            content = b"RIFF-test"

            @staticmethod
            def raise_for_status():
                return None

        old_url, old_model = voice.TTS_URL, voice.TTS_MODEL
        voice.TTS_URL, voice.TTS_MODEL = "http://127.0.0.1:8766/v1", "kokoro"
        try:
            with tempfile.TemporaryDirectory(prefix="drisa-gaming-tts-test-") as directory:
                with (
                    patch.object(voice.requests, "get", return_value=ModelsResponse()),
                    patch.object(voice.requests, "post", return_value=FakeResponse()) as post,
                    patch.object(voice.tempfile, "gettempdir", return_value=directory),
                ):
                    output = voice.tts_kokoro("Sistema pronto.")
                    self.assertEqual(Path(output).read_bytes(), b"RIFF-test")
                self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8766/v1/audio/speech")
                self.assertEqual(post.call_args.kwargs["json"]["model"], "kokoro")
        finally:
            voice.TTS_URL, voice.TTS_MODEL = old_url, old_model

    def test_pipeline_lock_is_released_after_success(self):
        lock = threading.Lock()
        lock.acquire()
        with patch.object(voice, "pipeline"):
            voice._run_pipeline_guarded(b"audio", "test mic", lock)
        self.assertTrue(lock.acquire(blocking=False))
        lock.release()

    def test_pipeline_lock_is_released_after_failure(self):
        lock = threading.Lock()
        lock.acquire()
        with patch.object(voice, "pipeline", side_effect=RuntimeError("inference failed")):
            with self.assertRaisesRegex(RuntimeError, "inference failed"):
                voice._run_pipeline_guarded(b"audio", "test mic", lock)
        self.assertTrue(lock.acquire(blocking=False))
        lock.release()

    def test_autosave_keeps_audio_encrypted_without_plain_wav_copy(self):
        old_audio_dir = voice.AUDIO_DIR
        old_fernet = voice._FERNET
        old_buffer = voice._enc_buf
        old_last_write = voice._last_enc_write
        old_last_check = voice._last_dec_check
        try:
            with tempfile.TemporaryDirectory(prefix="drisa-encrypted-audio-test-") as directory:
                voice.AUDIO_DIR = Path(directory)
                voice._FERNET = Fernet(Fernet.generate_key())
                voice._enc_buf = bytearray()
                voice._last_enc_write = 0
                with patch.object(voice, "log"):
                    voice.audio_autosave_tick(b"\0\0" * voice.SAMPLE_RATE, force=True)
                files = list(Path(directory).iterdir())
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0].suffix, ".bin")
                self.assertTrue(voice._last_dec_check["decrypt_ok"])
                self.assertTrue(voice._last_dec_check["encrypted_at_rest"])
        finally:
            voice.AUDIO_DIR = old_audio_dir
            voice._FERNET = old_fernet
            voice._enc_buf = old_buffer
            voice._last_enc_write = old_last_write
            voice._last_dec_check = old_last_check

    def test_status_server_is_loopback_only_no_cors_and_rejects_bad_host(self):
        old_port = voice.STATUS_PORT
        old_page = voice.STATUS_PAGE
        voice.STATUS_PAGE = Path(_TEST_HOME.name) / "drisa-status.html"
        voice.STATUS_PAGE.write_text("<p>Drisa status</p>", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), voice.Handler)
        voice.STATUS_PORT = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{voice.STATUS_PORT}"
        try:
            page = requests.get(base + "/", timeout=2)
            status = requests.get(base + "/status", timeout=2)
            self.assertEqual(page.status_code, 200)
            self.assertEqual(status.status_code, 200)
            self.assertNotIn("Access-Control-Allow-Origin", status.headers)
            rejected = requests.get(base + "/status", headers={"Host": "attacker.example"}, timeout=2)
            self.assertEqual(rejected.status_code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            voice.STATUS_PORT = old_port
            voice.STATUS_PAGE = old_page


def tearDownModule():
    _TEST_HOME.cleanup()


if __name__ == "__main__":
    unittest.main()
