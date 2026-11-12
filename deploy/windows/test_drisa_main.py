import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

with patch("logging.FileHandler", side_effect=lambda *_args, **_kwargs: logging.NullHandler()):
    from drisa_main import DrisaAssistant


class DrisaFallbackTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
