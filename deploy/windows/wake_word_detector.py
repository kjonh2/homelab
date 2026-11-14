"""Offline wake-word gate for the always-on laptop microphone."""

import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_WAKE_ALIASES = {"drisa", "driza", "drissa", "drica"}
_WAKE_GRAMMAR = json.dumps(
    ["olá drisa", "ola drisa", "drisa", "[unk]"], ensure_ascii=False
)


class WakeWordDetector:
    def __init__(self, model_path=None, sample_rate=16000, chunk_duration_ms=1000, threshold=0.5):
        self.model_path = model_path or os.environ.get("DRISA_WAKE_MODEL")
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.detection_callback = None
        self._model = None
        self._last_detection = 0.0
        self._cooldown_seconds = 2.0

    def set_detection_callback(self, callback):
        self.detection_callback = callback

    def start_listening(self):
        """Load the small Portuguese Vosk model; no user audio leaves this device."""
        try:
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            model_path = Path(self.model_path).expanduser() if self.model_path else None
            self._model = Model(str(model_path)) if model_path and model_path.is_dir() else Model(lang="pt")
            logger.info("Offline Portuguese wake-word detector ready")
        except Exception as exc:
            self._model = None
            logger.error(
                "Offline wake-word model unavailable; microphone segments will be ignored (%s)",
                type(exc).__name__,
            )

    def stop_listening(self):
        self._model = None
        logger.info("Offline wake-word detector stopped")

    @staticmethod
    def contains_wake_word(text):
        normalized = unicodedata.normalize("NFKD", str(text).casefold())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        words = re.findall(r"[a-z0-9]+", normalized)
        return any(word in _WAKE_ALIASES for word in words[:3])

    def process_audio(self, audio_chunk):
        """Return True only when a recent segment starts with the Drisa wake word."""
        if self._model is None:
            return False
        try:
            from vosk import KaldiRecognizer

            audio = np.asarray(audio_chunk, dtype=np.float32).reshape(-1)
            if audio.size < int(self.sample_rate * 0.25):
                return False
            if not np.isfinite(audio).all():
                return False
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            recognizer = KaldiRecognizer(self._model, self.sample_rate, _WAKE_GRAMMAR)
            recognizer.SetMaxAlternatives(3)
            recognizer.AcceptWaveform(pcm)
            result = json.loads(recognizer.FinalResult())
            candidates = [result.get("text", "")]
            candidates.extend(
                item.get("text", "") for item in result.get("alternatives", [])
                if isinstance(item, dict)
            )
            if not any(self.contains_wake_word(candidate) for candidate in candidates):
                return False
            now = time.monotonic()
            if now - self._last_detection < self._cooldown_seconds:
                return False
            self._last_detection = now
            if self.detection_callback:
                self.detection_callback(1.0)
            return True
        except Exception as exc:
            logger.warning("Offline wake-word check failed (%s)", type(exc).__name__)
            return False
