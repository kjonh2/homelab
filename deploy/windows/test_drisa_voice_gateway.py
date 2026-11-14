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


class ModelManagementErrorTests(unittest.TestCase):
    def test_mcp_auth_and_disabled_errors_are_actionable(self):
        import requests

        for status, expected in (
            (401, "Settings > API"),
            (404, "Settings > Agents"),
        ):
            with self.subTest(status=status):
                response = type("FakeResponse", (), {"status_code": status})()
                with (
                    patch.object(gateway, "_unsloth_cfg", return_value={"base_url": "http://127.0.0.1:8888/v1", "key": ""}),
                    patch.object(requests, "post", return_value=response),
                ):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        gateway._mcp_tool("list_models", {"kind": "llm"})


class ModelCatalogTests(unittest.TestCase):
    def test_pc_catalog_filters_image_models_and_reports_loaded_state(self):
        with (
            patch.object(gateway, "_mcp_tool", return_value={"models": [
                {"id": "AtomicChat/LFM3-1.7B-Uncensored-GGUF", "loaded": True},
                {"id": "flux-3-image", "loaded": False},
            ]}) as mcp_tool,
            patch.object(gateway, "load_config", return_value={
                "llm_host": "pc", "llm_model": "AtomicChat/LFM3-1.7B-Uncensored-GGUF",
            }),
        ):
            result = gateway.model_catalog("pc", "llm")

        self.assertEqual(mcp_tool.call_args.args, ("list_models", {"kind": "llm", "source": "local", "loaded_only": False}))
        self.assertEqual(result["selected"], "AtomicChat/LFM3-1.7B-Uncensored-GGUF")
        self.assertEqual(result["models"], [{"id": "AtomicChat/LFM3-1.7B-Uncensored-GGUF", "loaded": True}])

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
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"data": [{"id": "lfm3-text", "loaded": False}]}

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
                patch.object(requests, "get", return_value=CatalogResponse()),
                patch.object(requests, "post", return_value=LoadResponse()) as post,
                patch.object(gateway, "_save_model_selection") as save_selection,
            ):
                result = gateway.load_model_for_app("vps", "llm", "lfm3-text")

        self.assertEqual(result, "Modelo carregado na VPS.")
        self.assertEqual(post.call_args.args[0], gateway._VPS_MODELS_URL + "/load")
        self.assertEqual(post.call_args.kwargs["json"], {"model": "lfm3-text"})
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-vps-key")
        save_selection.assert_called_once_with("vps", "llm", "lfm3-text")


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
        self.assertEqual([message["type"] for message in socket.sent], ["auth", "transcript", "reply", "tts"])
        llm.assert_called_once_with("hello")
        tts.assert_called_once_with("reply")


def tearDownModule():
    _TEST_ROOT.cleanup()


if __name__ == "__main__":
    unittest.main()
