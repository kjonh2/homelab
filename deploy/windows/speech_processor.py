import os
import logging
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import threading
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SpeechProcessor:
    _whisper_lock = threading.Lock()  # Only 1 transcription at a time
    _whisper_model = None
    
    def __init__(self, model_size="base", 
                 temp_dir=None,
                 sample_rate=16000,
                 device="cpu",
                 compute_type="int8"):
        self.model_size = model_size
        self.temp_dir = temp_dir or os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Drisa", "temp"
        )
        self.sample_rate = sample_rate
        self.device = device
        self.compute_type = compute_type
        
        # Ensure temp dir exists
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
        
        # Kokoro TTS
        try:
            from kokoro_tts import speak as kokoro_speak
            self.kokoro_speak = kokoro_speak
        except ImportError:
            logger.warning("KokoroTTS module not found, using placeholder")
            self.kokoro_speak = None

    def _get_model(self):
        """Lazy-load the Whisper model"""
        if SpeechProcessor._whisper_model is None:
            logger.info(f"Loading faster-whisper {self.model_size} model (device={self.device}, compute={self.compute_type})...")
            from faster_whisper import WhisperModel
            SpeechProcessor._whisper_model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=4,
                num_workers=1
            )
            logger.info("Model loaded successfully")
        return SpeechProcessor._whisper_model

    def transcribe(self, audio_data: np.ndarray, language: str = "pt", engine: str = None) -> Dict[str, Any]:
        """Transcribe audio with a selectable engine.
        Supported engines:
        - local: faster-whisper local
        - api: unsloth/OpenAI-compatible server
        - deepgram: direct Deepgram API
        Falls back to local when the selected engine fails."""
        import os
        engine = (engine or os.environ.get("DRISA_STT_ENGINE", "api")).strip().lower()
        if engine == "deepgram":
            try:
                result = self._transcribe_deepgram(audio_data, language)
                if result.get("text"):
                    return result
                logger.warning("Deepgram sem texto, fallback local")
            except Exception as e:
                logger.warning(f"Deepgram failed ({e}), fallback local")
        elif engine == "api":
            try:
                result = self._transcribe_api(audio_data, language)
                if result.get("text"):
                    return result
                logger.warning("STT API sem texto, fallback local")
            except Exception as e:
                logger.warning(f"STT API failed ({e}), fallback local")
        fallback = os.environ.get("DRISA_STT_FALLBACK", "").strip().lower()
        if fallback in ("1", "true", "yes", "local", "whisper"):
            return self._transcribe_local(audio_data, language)
        return {"text": "", "confidence": 0.0, "success": False, "error": f"{engine} stt failed"}

    def _transcribe_api(self, audio_data: np.ndarray, language: str) -> Dict[str, Any]:
        """STT via servidor unsloth (/v1/audio/transcriptions)."""
        import requests, io, os, time
        import soundfile as sf
        base = os.environ.get("DRISA_UNSLOTH_URL", "http://localhost:8888/v1")
        if "[IP_ADDRESS]" in base or not base.strip():
            base = "http://localhost:8888/v1"
        key = os.environ.get("DRISA_UNSLOTH_KEY", "").strip()
        model = os.environ.get("DRISA_STT_MODEL", "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF")
        buf = io.BytesIO()
        sf.write(buf, audio_data.astype(np.float32), self.sample_rate, format="WAV", subtype="PCM_16")
        t0 = time.time()
        headers = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        r = requests.post(
            f"{base}/audio/transcriptions",
            headers=headers,
            files={"file": ("chunk.wav", buf.getvalue(), "audio/wav")},
            data={"model": model, "language": language},
            timeout=180,
        )
        r.raise_for_status()
        text = (r.json().get("text") or "").strip()
        logger.info(f"STT API ({model}): '{text}' ({time.time()-t0:.1f}s)")
        if text:
            return {"text": text, "confidence": 1.0, "success": True}
        return {"text": "", "confidence": 0.0, "success": False, "error": "no speech detected"}

    def _transcribe_deepgram(self, audio_data: np.ndarray, language: str = "pt") -> Dict[str, Any]:
        """STT via Deepgram direto, usando deepgram.key ou env DEEPGRAM_API_KEY."""
        import io, os, time, requests
        import soundfile as sf
        key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if not key:
            key_file = os.path.join(os.path.dirname(__file__), "deepgram.key")
            if os.path.exists(key_file):
                with open(key_file, "r", encoding="utf-8") as f:
                    key = f.read().strip()
        if not key:
            return {"text": "", "confidence": 0.0, "success": False, "error": "missing deepgram key"}
        model = os.environ.get("DRISA_DEEPGRAM_MODEL", "nova-3")
        lang = os.environ.get("DRISA_DEEPGRAM_LANGUAGE", language or "pt")
        if lang in ("pt", "pt-pt", "portuguese", "português"):
            lang = "pt"
        elif lang in ("en", "english"):
            lang = "en"
        elif lang not in ("multi", "auto"):
            lang = "multi"
        buf = io.BytesIO()
        sf.write(buf, audio_data.astype(np.float32), self.sample_rate, format="WAV", subtype="PCM_16")
        t0 = time.time()
        url = f"https://api.deepgram.com/v1/listen?model={model}&language={lang}&smart_format=true&punctuate=true"
        r = requests.post(
            url,
            headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
            data=buf.getvalue(),
            timeout=180,
        )
        r.raise_for_status()
        payload = r.json()
        text = ""
        try:
            text = (payload["results"]["channels"][0]["alternatives"][0]["transcript"] or "").strip()
        except Exception:
            text = (payload.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript") or "").strip()
        logger.info(f"Deepgram ({model}/{lang}): '{text}' ({time.time()-t0:.1f}s)")
        if text:
            return {"text": text, "confidence": 1.0, "success": True}
        return {"text": "", "confidence": 0.0, "success": False, "error": "no speech detected"}

    def _transcribe_local(self, audio_data: np.ndarray, language: str = "pt") -> Dict[str, Any]:
        """Transcribe audio using faster-whisper (local, CPU int8)"""
        with self._whisper_lock:
            try:
                model = self._get_model()

                # Accept either ndarray or a WAV file path
                if isinstance(audio_data, (str, bytes, os.PathLike)):
                    import soundfile as sf
                    audio_data, _sr = sf.read(str(audio_data), dtype="float32")
                    if _sr != self.sample_rate:
                        logger.warning(f"Loaded WAV sample_rate={_sr}, expected {self.sample_rate}")
                # Ensure audio is float32 mono
                if len(audio_data.shape) > 1:
                    audio_data = audio_data.flatten()
                audio_data = audio_data.astype(np.float32)

                logger.info(f"Transcribing {len(audio_data)} samples...")

                # Transcribe
                segments, info = model.transcribe(
                    audio_data,
                    language=language if language != "auto" else None,
                    beam_size=5,
                    vad_filter=False,  # Disable internal VAD, we use our own
                )

                # Collect all segments
                text = ""
                for segment in segments:
                    text += segment.text + " "

                text = text.strip()
                logger.info(f"Transcription: '{text}' (lang: {info.language}, prob: {info.language_probability:.2f})")

                if text:
                    return {"text": text, "confidence": info.language_probability, "success": True}
                else:
                    logger.warning("faster-whisper returned empty text, trying whisper.cpp fallback")
                    return self._transcribe_whisper_cpp(audio_data, language)

            except Exception as e:
                logger.error(f"STT Error: {e}")
                return self._transcribe_whisper_cpp(audio_data, language, error=str(e))


    def _transcribe_whisper_cpp(self, audio_data: np.ndarray, language: str = "pt", error: str = "") -> Dict[str, Any]:
        """Transcribe with whisper.cpp CLI as a reliable local fallback."""
        import subprocess, tempfile, os, time
        from pathlib import Path

        try:
            if isinstance(audio_data, (str, bytes, os.PathLike)):
                wav_path = Path(str(audio_data))
            else:
                if len(audio_data.shape) > 1:
                    audio_data = audio_data.flatten()
                audio_data = audio_data.astype(np.float32)
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=self.temp_dir)
                tmp.close()
                wav_path = Path(tmp.name)
                import soundfile as sf
                sf.write(str(wav_path), audio_data, self.sample_rate)

            exe = r"C:\Whisper.Cpp\whisper-cli.exe"
            model = r"C:\Whisper.Cpp\models\ggml-base.bin"
            out_prefix = wav_path.with_suffix("")
            cmd = [
                exe,
                "-m", model,
                "-f", str(wav_path),
                "-l", language if language else "pt",
                "-otxt",
                "-of", str(out_prefix),
            ]
            t0 = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            txt_path = Path(str(out_prefix) + ".txt")
            text = txt_path.read_text(encoding="utf-8", errors="ignore").strip() if txt_path.exists() else ""
            logger.info(f"whisper.cpp rc={r.returncode} text='{text}'")
            if text:
                return {"text": text, "confidence": 1.0, "success": True, "provider": "whisper.cpp"}
            return {"text": "", "confidence": 0.0, "success": False, "error": error or "whisper.cpp returned empty"}
        except Exception as e:
            logger.error(f"whisper.cpp fallback failed: {e}")
            return {"text": "", "confidence": 0.0, "success": False, "error": str(e)}

    def synthesize_speech(self, text: str, language: str = "pt") -> Dict[str, Any]:
        """Synthesize speech — API Kokoro (rápida, default) ou Kokoro local torch (lento).
        DRISA_TTS_ENGINE=api (default) | local."""
        import os
        logger.info(f"Synthesizing: {text}")

        engine = os.environ.get("DRISA_TTS_ENGINE", "api").strip().lower()
        if engine == "api":
            try:
                return self._tts_api(text)
            except Exception as e:
                logger.warning(f"TTS API failed ({e}), fallback kokoro local")

        fallback = os.environ.get("DRISA_TTS_FALLBACK", "").strip().lower()
        if fallback in ("1", "true", "yes", "local", "kokoro") and self.kokoro_speak:
            try:
                # Kokoro speak generates and plays audio via sounddevice
                self.kokoro_speak(text)
                return {"success": True, "audio_file_path": "", "provider": "kokoro"}
            except Exception as e:
                logger.error(f"TTS Error: {e}")
                return {"success": False, "error": str(e), "provider": "kokoro"}
        logger.warning("No TTS fallback enabled")
        return {"success": False, "error": "TTS API failed", "provider": "api"}

    def _tts_api(self, text: str) -> Dict[str, Any]:
        """TTS via servidor unsloth (Kokoro GGUF, /v1/audio/speech) — toca via sounddevice."""
        import requests, io, os, time
        import sounddevice as sd
        import soundfile as sf
        base = os.environ.get("DRISA_UNSLOTH_URL", "http://localhost:8888/v1")
        if "[IP_ADDRESS]" in base or not base.strip():
            base = "http://localhost:8888/v1"
        key = os.environ.get("DRISA_UNSLOTH_KEY", "").strip()
        model = os.environ.get("DRISA_TTS_MODEL", "audio-cpp/audio.cpp-gguf/Kokoro-82M-GGUF")
        voice = os.environ.get("DRISA_TTS_VOICE", "pf_dora")
        t0 = time.time()
        headers = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        r = requests.post(
            f"{base}/audio/speech",
            headers=headers,
            json={"model": model, "input": text, "voice": voice, "response_format": "wav"},
            timeout=120,
        )
        r.raise_for_status()
        data, sr = sf.read(io.BytesIO(r.content), dtype="float32")
        sd.play(data, sr)
        sd.wait()
        logger.info(f"TTS API ({model}): {len(data)/sr:.1f}s de áudio em {time.time()-t0:.1f}s")
        return {"success": True, "audio_file_path": "", "provider": "api-kokoro"}
