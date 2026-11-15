import os
import unittest
from unittest.mock import patch

import numpy as np
import requests
import requests

from speech_processor import SpeechProcessor


class FakeResponse:
    ok = True
    text = ""

    @staticmethod
    def raise_for_status():
        return None

    @staticmethod
    def json():
        return {"text": "Teste de voz."}

    content = b"RIFF-audio"


class SpeechProcessorRoutingTests(unittest.TestCase):
    def setUp(self):
        self.processor = SpeechProcessor(sample_rate=16000)
        self.audio = np.zeros(16000, dtype=np.float32)

    def test_vps_uses_audio_cpp_openai_transcription_route(self):
        with (
            patch.object(self.processor, "_ensure_remote_audio_model_loaded") as ensure,
            patch.object(requests, "post", return_value=FakeResponse()) as post,
            patch.dict(os.environ, {"DRISA_UNSLOTH_KEY": "", "DRISA_AUDIO_KEY": "", "DRISA_STT_KEY": ""}),
        ):
            result = self.processor._transcribe_api(
                self.audio, "pt", "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF",
                "vps", "http://127.0.0.1:8767/v1",
            )

        ensure.assert_called_once_with("http://127.0.0.1:8767/v1", "moss")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8767/v1/audio/transcriptions")
        self.assertEqual(post.call_args.kwargs["data"]["model"], "moss")
        self.assertEqual(result["text"], "Teste de voz.")

    def test_pc_fallback_uses_unsloth_studio_route_and_full_model_id(self):
        model = "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF"
        with (
            patch.object(self.processor, "_ensure_pc_stt_model_loaded") as ensure,
            patch.object(requests, "post", return_value=FakeResponse()) as post,
            patch.dict(os.environ, {"DRISA_UNSLOTH_KEY": "", "DRISA_AUDIO_KEY": "", "DRISA_STT_KEY": ""}),
        ):
            result = self.processor._transcribe_api(
                self.audio, "pt", model, "pc", "http://127.0.0.1:8888/v1",
            )

        ensure.assert_called_once_with(model, "http://127.0.0.1:8888")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8888/api/inference/audio/transcriptions")
        self.assertEqual(post.call_args.kwargs["data"]["model"], model)
        self.assertEqual(result["text"], "Teste de voz.")

    def test_vps_model_id_is_normalized_for_remote_audio_service(self):
        self.assertEqual(
            __import__("speech_processor")._normalize_api_model_id(
                "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF", "vps",
            ),
            "moss",
        )

    def test_tts_uses_laptop_kokoro_when_vps_is_unavailable(self):
        class SpeechResponse(FakeResponse):
            @staticmethod
            def raise_for_status():
                return None

        with (
            patch.dict(os.environ, {
                "DRISA_TTS_HOST": "vps", "DRISA_TTS_URL": "http://127.0.0.1:8767/v1",
                "DRISA_TTS_MODEL": "kokoro", "DRISA_TTS_FALLBACK_URL": "http://127.0.0.1:8888/v1",
                "DRISA_TTS_FALLBACK_MODEL": "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF",
                "DRISA_TTS_VOICE": "pf_dora", "DRISA_AUDIO_KEY": "", "DRISA_UNSLOTH_KEY": "",
            }),
            patch.object(self.processor, "_ensure_remote_audio_model_loaded"),
            patch.object(requests, "post", side_effect=[requests.ConnectionError("VPS down"), SpeechResponse()]) as post,
            patch("soundfile.read", return_value=(np.zeros(8, dtype=np.float32), 24000)),
            patch("sounddevice.play"),
            patch("sounddevice.wait"),
        ):
            result = self.processor.synthesize_speech("Sistema pronto.")

        self.assertTrue(result["success"])
        self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:8767/v1/audio/speech")
        self.assertEqual(post.call_args_list[1].args[0], "http://127.0.0.1:8888/v1/audio/speech")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF")


if __name__ == "__main__":
    unittest.main()
