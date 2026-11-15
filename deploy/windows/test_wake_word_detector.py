import json
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from deploy.windows.wake_word_detector import WakeWordDetector


class WakeWordDetectorTests(unittest.TestCase):
    def test_accepts_drisa_with_or_without_portuguese_accent(self):
        self.assertTrue(WakeWordDetector.contains_wake_word("Olá Drisa, como estás?"))
        self.assertTrue(WakeWordDetector.contains_wake_word("Ola Drisa"))

    def test_accepts_wake_word_aliases(self):
        self.assertTrue(WakeWordDetector.contains_wake_word("driza"))
        self.assertTrue(WakeWordDetector.contains_wake_word("driça"))

    def test_rejects_unrelated_speech_and_late_mentions(self):
        self.assertFalse(WakeWordDetector.contains_wake_word("Teste de microfone"))
        self.assertFalse(WakeWordDetector.contains_wake_word("Hoje vou falar com a Drisa"))
        self.assertFalse(WakeWordDetector.contains_wake_word("Acho que a Drisa está ocupada"))

    def test_unavailable_model_never_opens_the_remote_stt_gate(self):
        detector = WakeWordDetector()
        self.assertFalse(detector.process_audio([0.0] * 16000))

    def test_process_audio_only_opens_gate_for_a_vosk_wake_result(self):
        class FakeRecognizer:
            def __init__(self, _model, _sample_rate, _grammar):
                pass

            def SetMaxAlternatives(self, _count):
                pass

            def AcceptWaveform(self, _pcm):
                return True

            def FinalResult(self):
                return json.dumps({"text": self.result})

        for recognized, expected in (("ola drisa", True), ("teste de microfone", False)):
            FakeRecognizer.result = recognized
            fake_vosk = types.ModuleType("vosk")
            fake_vosk.KaldiRecognizer = FakeRecognizer
            detector = WakeWordDetector()
            detector._model = object()
            with patch.dict(sys.modules, {"vosk": fake_vosk}):
                self.assertEqual(detector.process_audio(np.zeros(16000, dtype=np.float32)), expected)


if __name__ == "__main__":
    unittest.main()
