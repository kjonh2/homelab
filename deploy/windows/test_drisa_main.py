import json
import logging
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

with patch("logging.basicConfig"):
    from drisa_main import DrisaAssistant


class DrisaFallbackTests(unittest.TestCase):
    def make_audio_gate_assistant(self, wake_word_enabled):
        class Detector:
            @staticmethod
            def process_audio(_audio):
                return False

        return SimpleNamespace(
            config={
                "audio": {"min_speech_samples": 10},
                "wake_word": {"enabled": wake_word_enabled},
            },
            wake_word_detector=Detector(),
            is_processing_speech=False,
            _gemini_processing=False,
            processing_lock=threading.Lock(),
            _speech_gate_lock=threading.Lock(),
            _last_speech_fingerprint=None,
            _last_speech_fingerprint_at=0.0,
            speech_queue=unittest.mock.Mock(),
            processing_thread=unittest.mock.Mock(is_alive=lambda: True),
        )

    def test_microphone_segment_is_queued_when_wake_word_is_disabled(self):
        assistant = self.make_audio_gate_assistant(wake_word_enabled=False)
        DrisaAssistant.on_speech_end(assistant, [0.1] * 100)
        assistant.speech_queue.put.assert_called_once()

    def test_microphone_segment_stays_gated_when_wake_word_is_enabled(self):
        assistant = self.make_audio_gate_assistant(wake_word_enabled=True)
        DrisaAssistant.on_speech_end(assistant, [0.1] * 100)
        assistant.speech_queue.put.assert_not_called()

    def test_microphone_segment_is_discarded_during_post_tts_echo_guard(self):
        assistant = self.make_audio_gate_assistant(wake_word_enabled=False)
        assistant._ignore_audio_until = 100.0
        with patch("drisa_main.time.monotonic", return_value=99.0):
            DrisaAssistant.on_speech_end(assistant, [0.1] * 100)
        assistant.speech_queue.put.assert_not_called()

    def test_local_llm_runs_when_gemini_cli_is_missing(self):
        utterance = "Qual é o estado dos meus serviços agora?"
        assistant = object.__new__(DrisaAssistant)
        assistant.config = {"llm": {"base_url": "http://127.0.0.1:1/v1", "model": "test-model"}}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return json.dumps({
                    "choices": [{"message": {"content": "Os três serviços estão ligados."}}]
                }).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir, patch("shutil.which", return_value=None), \
                patch("urllib.request.urlopen", return_value=FakeResponse()), \
                patch.dict(os.environ, {
                    "DRISA_UNSLOTH_URL": "http://127.0.0.1:1/v1",
                    "DRISA_UNSLOTH_KEY": "",
                    "DRISA_LLM_FALLBACK": "",
                }), patch("drisa_main.DRISA_HOME", Path(temp_dir)):
            response = assistant.process_command(utterance, "pt")

        self.assertEqual(response, "Os três serviços estão ligados.")

    def test_unavailable_llm_fallback_does_not_repeat_utterance(self):
        utterance = "Qual é o estado dos meus serviços agora?"
        assistant = object.__new__(DrisaAssistant)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("drisa_main.DRISA_HOME", Path(temp_dir)):
                response = assistant._simple_response(utterance, "pt")

        self.assertEqual(
            response,
            "Desculpa, não consegui preparar uma resposta agora. Podes tentar outra vez?",
        )
        self.assertNotIn(utterance.casefold(), response.casefold())

    def test_fallback_does_not_treat_oi_inside_depois_as_a_greeting(self):
        assistant = object.__new__(DrisaAssistant)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("drisa_main.DRISA_HOME", Path(temp_dir)):
                response = assistant._simple_response("Depois falamos sobre isso.", "pt")

        self.assertNotIn("Oi Kiko", response)

    def test_empty_local_completion_is_retried_with_more_tokens(self):
        utterance = "Explica em duas frases para que serve o Tailscale."
        assistant = object.__new__(DrisaAssistant)
        assistant.config = {"llm": {"base_url": "http://127.0.0.1:1/v1", "model": "test-model"}}

        class FakeResponse:
            def __init__(self, content):
                self.content = content

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": self.content}}]
                }).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir, patch("shutil.which", return_value=None), \
                patch("urllib.request.urlopen", side_effect=[FakeResponse(""), FakeResponse("Liga os teus dispositivos através de uma rede privada." )]) as request, \
                patch.dict(os.environ, {
                    "DRISA_UNSLOTH_URL": "http://127.0.0.1:1/v1",
                    "DRISA_UNSLOTH_KEY": "",
                    "DRISA_LLM_FALLBACK": "",
                }), patch("drisa_main.DRISA_HOME", Path(temp_dir)):
            response = assistant.process_command(utterance, "pt")

        self.assertEqual(response, "Liga os teus dispositivos através de uma rede privada.")
        self.assertEqual(request.call_count, 2)

    def test_selected_vps_is_used_before_local_pc(self):
        assistant = object.__new__(DrisaAssistant)
        assistant.config = {"llm": {"model": "test-model"}}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return json.dumps({"choices": [{"message": {"content": "Estou a ouvir, Kiko."}}]}).encode()

        with tempfile.TemporaryDirectory() as temp_dir, patch("shutil.which", return_value=None), \
                patch("urllib.request.urlopen", return_value=FakeResponse()) as request, \
                patch.dict(os.environ, {
                    "DRISA_LLM_HOST": "vps",
                    "DRISA_LLM_URL": "https://vps.example/v1",
                    "DRISA_LLM_KEY": "test-vps-key",
                    "DRISA_UNSLOTH_URL": "http://127.0.0.1:8888/v1",
                    "DRISA_UNSLOTH_KEY": "",
                    "DRISA_LLM_FALLBACK": "",
                }), patch("drisa_main.DRISA_HOME", Path(temp_dir)):
            response = assistant.process_command("Olá", "pt")

        self.assertEqual(response, "Estou a ouvir, Kiko.")
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].full_url.startswith("https://vps.example/v1/"))

    def test_selected_vps_falls_back_to_pc_after_empty_vps_retries(self):
        assistant = object.__new__(DrisaAssistant)
        assistant.config = {"llm": {"model": "test-model"}}

        class FakeResponse:
            def __init__(self, content):
                self.content = content

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()

        def response_by_host(request, timeout):
            if request.full_url.startswith("https://vps.example/"):
                return FakeResponse("")
            return FakeResponse("Posso ajudar com isso.")

        with tempfile.TemporaryDirectory() as temp_dir, patch("shutil.which", return_value=None), \
                patch("urllib.request.urlopen", side_effect=response_by_host) as request, \
                patch("drisa_main.ensure_local_llm_model_loaded") as ensure_local, \
                patch.dict(os.environ, {
                    "DRISA_LLM_HOST": "vps",
                    "DRISA_LLM_URL": "https://vps.example/v1",
                    "DRISA_LLM_KEY": "test-vps-key",
                    "DRISA_UNSLOTH_URL": "http://127.0.0.1:8888/v1",
                    "DRISA_UNSLOTH_KEY": "",
                    "DRISA_LLM_FALLBACK_MODEL": "local-test-model",
                    "DRISA_LLM_FALLBACK": "",
                }), patch("drisa_main.DRISA_HOME", Path(temp_dir)):
            response = assistant.process_command("O que podes fazer?", "pt")

        self.assertEqual(response, "Posso ajudar com isso.")
        self.assertEqual(request.call_count, 3)
        self.assertTrue(request.call_args.args[0].full_url.startswith("http://127.0.0.1:8888/v1/"))
        self.assertEqual(json.loads(request.call_args.args[0].data)["model"], "local-test-model")
        ensure_local.assert_called_once_with("http://127.0.0.1:8888/v1", "", "local-test-model")


if __name__ == "__main__":
    unittest.main()
