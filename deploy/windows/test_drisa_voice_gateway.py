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


class ModelCatalogTests(unittest.TestCase):
    def test_pc_catalog_filters_image_models_and_reports_loaded_state(self):
        import requests

        model_id = "AtomicChat/LFM3-1.7B-Uncensored-GGUF"

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            @staticmethod
            def raise_for_status():
                return None

            def json(self):
                return self.payload

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1", "key": ""}),
            patch.object(gateway, "load_config", return_value={
                "llm_host": "pc", "llm_model": model_id,
            }),
            patch.object(requests, "get", side_effect=[
                FakeResponse({"models": [
                    {"id": model_id, "task": "text-generation"},
                    {"id": "flux-3-image", "task": "text-generation"},
                ]}),
                FakeResponse({"data": [{"id": model_id, "loaded": True}]}),
            ]) as get,
        ):
            result = gateway.model_catalog("pc", "llm")

        self.assertEqual([call.args[0] for call in get.call_args_list], [
            "http://127.0.0.1:8888/api/models/local",
            "http://127.0.0.1:8888/api/inference/loaded-models",
        ])
        self.assertEqual(result["selected"], model_id)
        self.assertEqual(result["models"], [{"id": model_id, "loaded": True}])
        self.assertEqual(result["message"], "")

    def test_pc_tts_catalog_lists_downloaded_audio_models_and_load_state(self):
        import requests

        kokoro = "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF"

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            @staticmethod
            def raise_for_status():
                return None

            def json(self):
                return self.payload

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1", "key": ""}),
            patch.object(gateway, "load_config", return_value={"tts_host": "pc", "tts_model": kokoro}),
            patch.object(requests, "get", side_effect=[
                FakeResponse({"models": [
                    {"id": kokoro, "task": "tts", "downloaded": True},
                    {"id": "audio-cpp/audio.cpp-gguf/Not-Downloaded-TTS", "task": "tts", "downloaded": False},
                    {"id": "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF", "task": "asr", "downloaded": True},
                ]}),
                FakeResponse({"data": [{"id": kokoro, "loaded": True}]}),
            ]) as get,
        ):
            result = gateway.model_catalog("pc", "tts")

        self.assertEqual(get.call_args_list[0].args[0], "http://127.0.0.1:8888/api/inference/audio/catalog")
        self.assertEqual(get.call_args_list[0].kwargs["params"], {"source": "cache"})
        self.assertEqual(result["selected"], kokoro)
        self.assertEqual(result["models"], [{"id": kokoro, "loaded": True}])


class PcNativeModelManagementTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, payload=None, content=b"wav"):
            self.payload = payload or {}
            self.content = content

        @staticmethod
        def raise_for_status():
            return None

        def json(self):
            return self.payload

    def test_pc_llm_load_uses_native_studio_api(self):
        import requests

        model_id = "LiquidAI/LFM3-1.7B-GGUF"
        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1", "key": ""}),
            patch.object(gateway, "load_config", return_value={"llm_host": "pc", "llm_model": model_id}),
            patch.object(requests, "get", side_effect=[
                self.FakeResponse({"models": [{"id": model_id, "task": "text-generation"}]}),
                self.FakeResponse({"data": []}),
                self.FakeResponse({"data": []}),
                self.FakeResponse({"data": [{"id": model_id, "loaded": True}]}),
            ]) as get,
            patch.object(requests, "post", return_value=self.FakeResponse({"status": "loading", "model": model_id})) as post,
            patch.object(gateway, "_save_model_selection") as save_selection,
        ):
            result = gateway.load_model_for_app("pc", "llm", model_id)

        self.assertEqual(result, "Modelo carregado no portátil.")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8888/api/inference/load")
        self.assertEqual(post.call_args.kwargs["json"], {"model_path": model_id, "engine": "auto"})
        self.assertEqual(get.call_count, 4)
        save_selection.assert_called_once_with("pc", "llm", model_id)

    def test_pc_tts_load_uses_native_speech_api_and_confirms_loaded_state(self):
        import requests

        model_id = "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF"
        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1", "key": ""}),
            patch.object(gateway, "load_config", return_value={"tts_host": "pc", "tts_model": model_id}),
            patch.object(requests, "get", side_effect=[
                self.FakeResponse({"models": [{"id": model_id, "task": "tts", "downloaded": True}]}),
                self.FakeResponse({"data": []}),
                self.FakeResponse({"data": []}),
                self.FakeResponse({"data": [{"id": model_id, "loaded": True}]}),
            ]) as get,
            patch.object(requests, "post", return_value=self.FakeResponse()) as post,
            patch.object(gateway, "_save_model_selection") as save_selection,
        ):
            result = gateway.load_model_for_app("pc", "tts", model_id)

        self.assertEqual(result, "Modelo carregado no portátil.")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8888/v1/audio/speech")
        self.assertEqual(post.call_args.kwargs["json"], {"model": model_id, "input": "Pronto.", "response_format": "wav"})
        self.assertEqual(get.call_count, 4)
        save_selection.assert_called_once_with("pc", "tts", model_id)

    def test_vps_catalog_reports_available_and_loaded_models(self):
        import requests

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [
                    {"id": "lfm3-omni", "loaded": False},
                    {"id": "lfm3-uncensored", "status": {"value": "loaded"}},
                ]}

        with tempfile.TemporaryDirectory(prefix="drisa-vps-catalog-test-") as directory:
            key_file = Path(directory) / "iku_lfm3.key"
            key_file.write_text("test-vps-key", encoding="utf-8")
            with (
                patch.object(gateway, "BASE", Path(directory)),
                patch.object(gateway, "load_config", return_value={"llm_host": "vps", "llm_model": "lfm3-uncensored"}),
                patch.object(requests, "get", return_value=FakeResponse()) as get,
            ):
                result = gateway.model_catalog("vps", "llm")

        self.assertEqual(get.call_args.args[0], gateway._VPS_MODELS_URL)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer test-vps-key")
        self.assertEqual(result["selected"], "lfm3-uncensored")
        self.assertEqual(result["models"], [
            {"id": "lfm3-omni", "loaded": False},
            {"id": "lfm3-uncensored", "loaded": True},
        ])

    def test_vps_model_load_uses_private_api_and_saves_selection(self):
        import requests

        class CatalogResponse:
            def __init__(self, loaded):
                self.loaded = loaded

            @staticmethod
            def raise_for_status():
                return None

            def json(self):
                return {"data": [{"id": "lfm3-text", "loaded": self.loaded}]}

        class LoadResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"success": True}

        with tempfile.TemporaryDirectory(prefix="drisa-vps-load-test-") as directory:
            (Path(directory) / "iku_lfm3.key").write_text("test-vps-key", encoding="utf-8")
            with (
                patch.object(gateway, "BASE", Path(directory)),
                patch.object(gateway, "load_config", return_value={"llm_host": "vps", "llm_model": "lfm3-text"}),
                patch.object(requests, "get", side_effect=[CatalogResponse(False), CatalogResponse(False), CatalogResponse(True)]) as get,
                patch.object(requests, "post", return_value=LoadResponse()) as post,
                patch.object(gateway, "_save_model_selection") as save_selection,
                patch.object(gateway.time, "sleep") as sleep,
            ):
                result = gateway.load_model_for_app("vps", "llm", "lfm3-text")

        self.assertEqual(result, "Modelo carregado na VPS.")
        self.assertEqual(post.call_args.args[0], gateway._VPS_MODELS_URL + "/load")
        self.assertEqual(post.call_args.kwargs["json"], {"model": "lfm3-text"})
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-vps-key")
        self.assertEqual(get.call_count, 3)
        sleep.assert_called_once()
        save_selection.assert_called_once_with("vps", "llm", "lfm3-text")


class PcAudioCppRouteTests(unittest.TestCase):
    def test_pc_stt_catalog_uses_native_audio_cpp_status(self):
        import requests

        moss = "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF"
        parakeet = "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF"

        class StatusResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"audiocpp": {"downloaded_models": [moss, parakeet, "audiocpp-parakeet-tdt-0.6b-v3"], "loaded_model": parakeet}}

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1"}),
            patch.object(gateway, "load_config", return_value={"stt_host": "pc", "stt_model": moss}),
            patch.object(requests, "get", return_value=StatusResponse()) as get,
        ):
            result = gateway.model_catalog("pc", "stt")

        get.assert_called_once_with("http://127.0.0.1:8888/api/inference/audio/stt/status", timeout=(5, 15))
        self.assertEqual(result["selected"], moss)
        self.assertEqual(result["models"], [{"id": moss, "loaded": False}, {"id": parakeet, "loaded": True}])

    def test_pc_stt_load_uses_native_audio_cpp_api(self):
        import requests

        moss = "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF"
        parakeet = "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF"

        class StatusResponse:
            def __init__(self, loaded_model):
                self.loaded_model = loaded_model

            @staticmethod
            def raise_for_status():
                return None

            def json(self):
                return {"audiocpp": {"downloaded_models": [moss, parakeet], "loaded_model": self.loaded_model, "loading": False}}

        class LoadResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"success": True}

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1"}),
            patch.object(gateway, "load_config", return_value={"stt_host": "pc", "stt_model": parakeet}),
            patch.object(requests, "get", side_effect=[StatusResponse(parakeet), StatusResponse(parakeet), StatusResponse(moss)]) as get,
            patch.object(requests, "post", return_value=LoadResponse()) as post,
            patch.object(gateway, "_save_model_selection") as save_selection,
            patch.object(gateway.time, "sleep") as sleep,
        ):
            message = gateway.load_model_for_app("pc", "stt", moss)

        self.assertEqual(message, "Modelo carregado no portátil.")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8888/api/inference/audio/stt/load")
        self.assertEqual(post.call_args.kwargs["json"], {"model": moss, "engine": "audiocpp", "device": "auto"})
        self.assertEqual(get.call_count, 3)
        sleep.assert_not_called()
        save_selection.assert_called_once_with("pc", "stt", moss)

    def test_pc_moss_and_parakeet_use_native_audio_cpp_endpoint(self):
        import requests

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"text": "Texto reconhecido."}

        cfg = {
            "base_url": "http://127.0.0.1:8888/v1", "key": "pc-key",
            "audio_url": "http://127.0.0.1:8766/v1", "audio_key": "",
            "stt_url": "http://127.0.0.1:8888/v1", "stt_key": "",
            "tts_url": "http://127.0.0.1:8888/v1", "tts_key": "",
            "stt_model": "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF",
            "fallback_stt_model": "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF",
        }
        with tempfile.TemporaryDirectory(prefix="drisa-pc-audio-cpp-test-") as directory:
            wav = Path(directory) / "input.wav"
            wav.write_bytes(b"RIFF-test")
            cases = (
                (cfg["stt_model"], cfg["stt_model"]),
                (cfg["fallback_stt_model"], cfg["fallback_stt_model"]),
                ("parakeet", cfg["fallback_stt_model"]),
                ("moss", cfg["stt_model"]),
            )
            for model, expected_model in cases:
                with (
                    patch.object(gateway, "_unsloth_cfg", return_value=cfg),
                    patch.object(requests, "post", return_value=FakeResponse()) as post,
                    patch.object(gateway, "_ensure_pc_audio_cpp_model") as ensure_model,
                ):
                    self.assertEqual(gateway.unsloth_transcribe(wav, model), "Texto reconhecido.")
                self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8888/api/inference/audio/transcriptions")
                self.assertEqual(post.call_args.kwargs["data"], {"model": expected_model, "device": "auto"})
                self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer pc-key"})
                ensure_model.assert_called_once_with(requests, expected_model)


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

    def test_world_bridge_writes_plain_user_text_and_drisa_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            text_path = Path(directory) / "drisa_text.tmp"
            reply_path = Path(directory) / "drisa_response.tmp"
            with (
                patch.object(gateway, "BRIDGE_TEXT", text_path),
                patch.object(gateway, "BRIDGE_RESP", reply_path),
            ):
                gateway.send_to_drisa("  Olá, Drisa.  ", "redmi-note-11")
                gateway.send_reply_to_world("  Estou a ouvir.  ")

            self.assertEqual(text_path.read_text(encoding="utf-8"), "Olá, Drisa.\n")
            self.assertEqual(reply_path.read_text(encoding="utf-8"), "Estou a ouvir.\n")

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

    def test_transcript_is_posted_to_selected_lfm_chat_endpoint(self):
        import requests

        transcript = "Explica o estado do servidor."
        reply = "O servidor está ligado e a funcionar."

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": reply}}]}

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={
                "llm_model": "lfm3-uncensored",
                "llm_url": "https://vps.example/v1",
                "llm_key": "test-key",
            }),
            patch.object(requests, "post", return_value=FakeResponse()) as post,
        ):
            self.assertEqual(gateway.llm_reply(transcript), reply)

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://vps.example/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "lfm3-uncensored")
        self.assertEqual(kwargs["json"]["messages"][-1], {"role": "user", "content": transcript})

    def test_homelab_catalog_reports_audio_models_and_active_model(self):
        import requests

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "moss"}, {"id": "parakeet"}, {"id": "kokoro"}]}

        old_active = gateway._HOMELAB_ACTIVE_MODEL
        try:
            gateway._HOMELAB_ACTIVE_MODEL = "moss"
            with (
                patch.object(gateway, "_unsloth_cfg", return_value={"audio_url": "http://127.0.0.1:8766/v1", "stt_url": "", "tts_url": "", "audio_key": ""}),
                patch.object(gateway, "load_config", return_value={"stt_host": "homelab", "stt_model": "moss"}),
                patch.object(requests, "get", return_value=FakeResponse()) as get,
            ):
                result = gateway.model_catalog("homelab", "stt")
            self.assertEqual(get.call_args.args[0], "http://127.0.0.1:8766/v1/models")
            self.assertEqual(result["selected"], "moss")
            self.assertEqual(result["models"], [{"id": "moss", "loaded": True}, {"id": "parakeet", "loaded": False}])
        finally:
            gateway._HOMELAB_ACTIVE_MODEL = old_active

    def test_homelab_model_load_uses_installed_package(self):
        import requests

        class ModelsResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "moss"}, {"id": "parakeet"}, {"id": "kokoro"}]}

        class LoadResponse(ModelsResponse):
            @staticmethod
            def json():
                return {"id": "moss", "loaded": True}

        with (
            patch.object(gateway, "_unsloth_cfg", return_value={"audio_url": "http://127.0.0.1:8766/v1", "stt_url": "", "tts_url": "", "audio_key": ""}),
            patch.object(requests, "get", return_value=ModelsResponse()),
            patch.object(requests, "post", return_value=LoadResponse()) as post,
        ):
            message = gateway.load_model_for_app("homelab", "stt", "moss")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8766/v1/models/load")
        self.assertEqual(post.call_args.kwargs["json"], {"id": "moss", "package_id": "moss_transcribe_diarize_q4_k", "task": "asr"})
        self.assertEqual(gateway._HOMELAB_ACTIVE_MODEL, "moss")
        self.assertEqual(gateway.load_config()["stt_host"], "homelab")

    def test_audio_inference_uses_audio_url_separate_from_llm_url(self):
        import requests

        class FakeResponse:
            content = b"RIFF-wave"

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"text": "Olá Kiko."}

        class ModelsResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [
                    {"id": "moss", "loaded": True},
                    {"id": "parakeet", "loaded": True},
                    {"id": "kokoro", "loaded": True},
                ]}

        cfg = {
            "base_url": "http://127.0.0.1:8888/v1", "key": "unsloth-key",
            "audio_url": "http://127.0.0.1:8766/v1", "audio_key": "",
            "stt_url": "http://127.0.0.1:8766/v1", "tts_url": "http://127.0.0.1:8766/v1",
            "stt_key": "", "tts_key": "", "stt_model": "moss", "fallback_stt_model": "parakeet",
            "tts_model": "kokoro", "tts_voice": "pf_dora",
        }
        with tempfile.TemporaryDirectory(prefix="drisa-audio-api-test-") as directory:
            wav = Path(directory) / "input.wav"
            wav.write_bytes(b"RIFF-test")
            with (
                patch.object(gateway, "_unsloth_cfg", return_value=cfg),
                patch.object(requests, "get", return_value=ModelsResponse()),
                patch.object(requests, "post", side_effect=[FakeResponse(), FakeResponse()]) as post,
            ):
                self.assertEqual(gateway.unsloth_transcribe(wav, "moss"), "Olá Kiko.")
                self.assertEqual(gateway.tts_kokoro("Olá."), b"RIFF-wave")
        self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:8766/v1/audio/transcriptions")
        self.assertEqual(post.call_args_list[0].kwargs["data"]["model"], "moss")
        self.assertEqual(post.call_args_list[1].args[0], "http://127.0.0.1:8766/v1/audio/speech")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "kokoro")

    def test_homelab_stt_loads_model_before_transcription(self):
        import requests

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
                return {"text": "Teste de fallback."}

        cfg = {
            "base_url": "http://127.0.0.1:8888/v1", "key": "",
            "audio_url": "http://127.0.0.1:8766/v1", "audio_key": "",
            "stt_url": "http://127.0.0.1:8766/v1", "tts_url": "",
            "stt_key": "", "tts_key": "", "stt_model": "moss",
            "fallback_stt_model": "parakeet", "tts_model": "kokoro", "tts_voice": "pf_dora",
        }
        with tempfile.TemporaryDirectory(prefix="drisa-audio-api-test-") as directory:
            wav = Path(directory) / "input.wav"
            wav.write_bytes(b"RIFF-test")
            with (
                patch.object(gateway, "_unsloth_cfg", return_value=cfg),
                patch.object(requests, "get", return_value=ModelsResponse()),
                patch.object(requests, "post", side_effect=[LoadResponse(), TranscriptionResponse()]) as post,
            ):
                self.assertEqual(gateway.unsloth_transcribe(wav, "parakeet"), "Teste de fallback.")
        self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:8766/v1/models/load")
        self.assertEqual(post.call_args_list[0].kwargs["json"], {
            "id": "parakeet", "package_id": "parakeet_tdt_q8_0", "task": "asr",
        })
        self.assertEqual(post.call_args_list[1].args[0], "http://127.0.0.1:8766/v1/audio/transcriptions")

    def test_stt_falls_back_from_moss_to_parakeet(self):
        cfg = {"stt_model": "moss", "fallback_stt_model": "parakeet"}
        with (
            patch.object(gateway, "load_config", return_value={"stt_engine": "api", "fallback_local_stt": False}),
            patch.object(gateway, "_unsloth_cfg", return_value=cfg),
            patch.object(gateway, "unsloth_transcribe", side_effect=["", "Texto reconhecido."]) as transcribe,
        ):
            self.assertEqual(gateway.transcribe(Path("unused.wav")), "Texto reconhecido.")
        self.assertEqual([call.args[1] for call in transcribe.call_args_list], ["moss", "parakeet"])

    def test_stt_does_not_fallback_when_homelab_inference_may_still_run(self):
        with (
            patch.object(gateway, "load_config", return_value={"stt_engine": "api", "fallback_local_stt": False}),
            patch.object(gateway, "_unsloth_cfg", return_value={
                "stt_model": "moss", "stt_host": "homelab", "stt_url": "http://homelab/v1",
                "fallback_stt_model": "parakeet",
            }),
            patch.object(gateway, "unsloth_transcribe", side_effect=gateway.AudioBackendBusyError("busy")) as transcribe,
        ):
            with self.assertRaises(gateway.AudioBackendBusyError):
                gateway.transcribe(Path("unused.wav"))
        transcribe.assert_called_once_with(Path("unused.wav"), "moss", host="homelab", base_url="http://homelab/v1")

    def test_stt_falls_back_to_pc_when_vps_is_busy(self):
        cfg = {
            "stt_model": "moss", "stt_host": "vps", "stt_url": "http://vps/v1",
            "fallback_stt_model": "parakeet", "fallback_stt_host": "pc",
            "fallback_stt_url": "http://127.0.0.1:8888/v1", "base_url": "http://127.0.0.1:8888/v1",
        }
        with (
            patch.object(gateway, "load_config", return_value={"stt_engine": "api", "fallback_local_stt": False}),
            patch.object(gateway, "_unsloth_cfg", return_value=cfg),
            patch.object(gateway, "unsloth_transcribe", side_effect=[gateway.AudioBackendBusyError("busy"), "Texto do portátil."]) as transcribe,
        ):
            self.assertEqual(gateway.transcribe(Path("unused.wav")), "Texto do portátil.")
        self.assertEqual(transcribe.call_args_list[1].kwargs, {"host": "pc", "base_url": "http://127.0.0.1:8888/v1"})

    def test_unsloth_keeps_full_stt_package_ids(self):
        moss = "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF"
        parakeet = "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF"
        audio_url = "http://127.0.0.1:8766/v1"
        unsloth_url = "http://127.0.0.1:8888/v1"
        config = {
            "unsloth_url": unsloth_url, "llm_host": "pc", "llm_url": unsloth_url,
            "audio_url": audio_url, "stt_url": unsloth_url, "stt_host": "pc",
            "stt_model": moss, "fallback_stt_model": parakeet,
            "tts_url": audio_url, "tts_host": "homelab", "tts_model": "kokoro",
        }
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.dict(os.environ, {
                "DRISA_AUDIO_URL": audio_url, "DRISA_STT_URL": unsloth_url,
                "DRISA_TTS_URL": audio_url, "DRISA_STT_MODEL": moss,
                "DRISA_STT_FALLBACK_MODEL": parakeet, "DRISA_TTS_MODEL": "kokoro",
            }),
        ):
            resolved = gateway._unsloth_cfg()

        self.assertEqual(resolved["stt_model"], moss)
        self.assertEqual(resolved["fallback_stt_model"], parakeet)
        self.assertEqual(resolved["tts_model"], "kokoro")

    def test_audio_cpp_uses_short_stt_ids(self):
        audio_url = "http://127.0.0.1:8766/v1"
        config = {
            "unsloth_url": "http://127.0.0.1:8888/v1", "llm_host": "pc",
            "llm_url": "http://127.0.0.1:8888/v1", "audio_url": audio_url,
            "stt_url": audio_url, "stt_host": "homelab",
            "stt_model": "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF",
            "fallback_stt_model": "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF",
            "tts_url": audio_url, "tts_host": "homelab", "tts_model": "kokoro",
        }
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.dict(os.environ, {"DRISA_AUDIO_URL": audio_url, "DRISA_STT_URL": audio_url,
                                    "DRISA_TTS_URL": audio_url}),
        ):
            resolved = gateway._unsloth_cfg()

        self.assertEqual(resolved["stt_model"], "moss")
        self.assertEqual(resolved["fallback_stt_model"], "parakeet")

    def test_pc_audio_endpoint_defaults_stay_local_when_llm_is_remote(self):
        local_url = "http://127.0.0.1:8888/v1"
        config = {
            "unsloth_url": local_url, "llm_host": "vps",
            "llm_url": "https://vps.example/v1", "audio_url": "http://127.0.0.1:8766/v1",
            "stt_host": "pc", "tts_host": "pc",
            "stt_model": "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF",
            "fallback_stt_model": "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF",
            "tts_model": "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF",
        }
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.dict(os.environ, {
                "DRISA_UNSLOTH_URL": local_url,
                "DRISA_AUDIO_URL": config["audio_url"],
                "DRISA_LLM_URL": "",
                "DRISA_STT_URL": "",
                "DRISA_TTS_URL": "",
                "DRISA_STT_MODEL": config["stt_model"],
                "DRISA_STT_FALLBACK_MODEL": config["fallback_stt_model"],
                "DRISA_TTS_MODEL": config["tts_model"],
                "DRISA_LLM_KEY": "",
            }),
        ):
            resolved = gateway._unsloth_cfg()

        self.assertEqual(resolved["llm_url"], "https://vps.example/v1")
        self.assertEqual(resolved["stt_url"], local_url)
        self.assertEqual(resolved["tts_url"], local_url)
        self.assertEqual(resolved["stt_model"], config["stt_model"])
        self.assertEqual(resolved["fallback_stt_model"], config["fallback_stt_model"])


class GatewayAsyncAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_turn_requires_transcription_policy(self):
        config = {
            "allowlist": ["kiko-pc"],
            "policies": {"kiko-pc": {"transcribe": False, "reply": True}},
            "unknown": {"transcribe": False, "reply": False},
        }

        class FakeWebSocket:
            remote_address = "test"

            def __init__(self):
                self.messages = iter([
                    json.dumps({"type": "hello", "device_id": "kiko-pc", "token": "test-token"}),
                    json.dumps({"type": "text", "text": "Não autorizado."}),
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

        socket = FakeWebSocket()
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.object(gateway, "load_token", return_value="test-token"),
            patch.object(gateway, "llm_reply") as llm,
        ):
            await asyncio.wait_for(gateway.handle_client(socket), timeout=2)

        self.assertEqual([message["type"] for message in socket.sent], ["auth", "audio_error"])
        self.assertIn("não está autorizada", socket.sent[-1]["message"])
        llm.assert_not_called()

    async def test_publish_completed_turn_broadcasts_without_recalling_llm(self):
        config = {
            "allowlist": ["kiko-pc"],
            "policies": {"kiko-pc": {"transcribe": True, "reply": True}},
            "unknown": {"transcribe": False, "reply": False},
        }

        class FakeWebSocket:
            remote_address = "test"

            def __init__(self, messages=()):
                self.messages = iter(messages)
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

        source = FakeWebSocket([
            json.dumps({"type": "hello", "device_id": "kiko-pc", "user": "Kiko", "token": "test-token"}),
            json.dumps({"type": "publish", "text": "Qual é o estado da VPS?", "reply": "A VPS está operacional."}),
        ])
        android = FakeWebSocket()
        gateway.ACTIVE_CLIENTS.add(android)
        try:
            with (
                patch.object(gateway, "load_config", return_value=config),
                patch.object(gateway, "load_token", return_value="test-token"),
                patch.object(gateway, "log_to_obsidian"),
                patch.object(gateway, "tts_kokoro", return_value=b"RIFF-audio"),
                patch.object(gateway, "llm_reply") as llm,
                patch.object(gateway, "send_to_drisa") as bridge,
            ):
                await asyncio.wait_for(gateway.handle_client(source), timeout=2)
        finally:
            gateway.ACTIVE_CLIENTS.discard(android)

        llm.assert_not_called()
        bridge.assert_not_called()
        self.assertEqual([m["type"] for m in android.sent], ["transcript", "reply", "processing", "tts"])
        self.assertEqual(android.sent[0]["text"], "Qual é o estado da VPS?")
        self.assertEqual(android.sent[1]["text"], "A VPS está operacional.")

    async def test_text_turn_uses_shared_pipeline_and_broadcasts_to_android_clients(self):
        config = {
            "allowlist": ["kiko-pc"],
            "policies": {"kiko-pc": {"transcribe": True, "reply": True}},
            "unknown": {"transcribe": False, "reply": False},
        }

        class FakeWebSocket:
            remote_address = "test"

            def __init__(self, messages=()):
                self.messages = iter(messages)
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

        source = FakeWebSocket([
            json.dumps({"type": "hello", "device_id": "kiko-pc", "user": "Kiko", "token": "test-token"}),
            json.dumps({"type": "text", "text": "Qual é o estado da VPS?"}),
        ])
        android = FakeWebSocket()
        gateway.ACTIVE_CLIENTS.add(android)
        try:
            with (
                patch.object(gateway, "load_config", return_value=config),
                patch.object(gateway, "load_token", return_value="test-token"),
                patch.object(gateway, "log_to_obsidian"),
                patch.object(gateway, "send_to_drisa") as bridge_input,
                patch.object(gateway, "llm_reply", return_value="A VPS está operacional.") as llm,
                patch.object(gateway, "send_reply_to_world") as bridge_reply,
                patch.object(gateway, "tts_kokoro", return_value=b"RIFF-audio"),
            ):
                await asyncio.wait_for(gateway.handle_client(source), timeout=2)
        finally:
            gateway.ACTIVE_CLIENTS.discard(android)

        self.assertEqual(source.sent[0]["type"], "auth")
        self.assertEqual(bridge_input.call_args.args[0], "Qual é o estado da VPS?")
        self.assertEqual(bridge_reply.call_args.args[0], "A VPS está operacional.")
        llm.assert_called_once_with("Qual é o estado da VPS?")
        self.assertEqual([m["type"] for m in android.sent], ["transcript", "processing", "reply", "processing", "tts"])
        self.assertEqual(android.sent[-1]["audio_b64"], base64.b64encode(b"RIFF-audio").decode())

    async def test_invalid_reauthentication_revokes_model_access(self):
        config = {
            "allowlist": ["trusted-device", "other-device"],
            "policies": {
                "trusted-device": {"transcribe": True, "reply": True},
                "other-device": {"transcribe": True, "reply": True},
            },
            "unknown": {"transcribe": False, "reply": False},
        }

        class FakeWebSocket:
            remote_address = "test"

            def __init__(self):
                self.messages = iter([
                    json.dumps({"type": "hello", "device_id": "trusted-device", "token": "test-token"}),
                    json.dumps({"type": "hello", "device_id": "other-device", "token": "wrong-token"}),
                    json.dumps({"type": "models_list", "request_id": "catalog", "host": "vps", "category": "llm"}),
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

        socket = FakeWebSocket()
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.object(gateway, "load_token", return_value="test-token"),
            patch.object(gateway, "model_catalog") as catalog,
            patch.object(gateway, "log_to_obsidian"),
        ):
            await asyncio.wait_for(gateway.handle_client(socket), timeout=2)

        self.assertEqual([message["type"] for message in socket.sent], ["auth", "auth", "model_operation"])
        self.assertEqual(socket.sent[1]["ok"], False)
        self.assertEqual(socket.sent[2]["ok"], False)
        catalog.assert_not_called()

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
            patch.object(gateway, "llm_reply", side_effect=lambda _: slow("reply")) as llm,
            patch.object(gateway, "tts_kokoro", side_effect=lambda _: slow(b"wav")) as tts,
            patch.object(gateway, "log_to_obsidian"),
            patch.object(gateway, "send_to_drisa"),
        ):
            heartbeat_task = asyncio.create_task(heartbeat())
            await asyncio.wait_for(gateway.handle_client(socket), timeout=2)
            finished.set()
            await heartbeat_task

        self.assertGreaterEqual(ticks, 5)
        self.assertEqual(
            [message["type"] for message in socket.sent],
            ["auth", "processing", "transcript", "processing", "reply", "processing", "tts"],
        )
        llm.assert_called_once_with("hello")
        tts.assert_called_once_with("reply")

    async def test_empty_transcript_returns_terminal_audio_error(self):
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

        socket = FakeWebSocket()
        with (
            patch.object(gateway, "load_config", return_value=config),
            patch.object(gateway, "load_token", return_value="test-token"),
            patch.object(gateway, "transcribe", return_value=""),
            patch.object(gateway, "log_to_obsidian"),
        ):
            await asyncio.wait_for(gateway.handle_client(socket), timeout=2)

        self.assertEqual([message["type"] for message in socket.sent], ["auth", "processing", "audio_error"])
        self.assertIn("não conseguiram transcrever", socket.sent[-1]["message"])


def tearDownModule():
    _TEST_ROOT.cleanup()


if __name__ == "__main__":
    unittest.main()
