"""
Drisa Main Application
Orchestrates all components: audio processing, wake word detection, STT/TTS, noise adaptation
"""

import os
import sys
import json
import hashlib
import time
import logging
import threading
import queue
import signal

# Disable OpenBLAS threading to avoid memory conflicts
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'

import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drisa_speech_text import is_utterance_echo, prepare_spoken_text

# Import our modules
try:
    from audio_processor import AudioProcessor
    from wake_word_detector import WakeWordDetector
    from speech_processor import SpeechProcessor
    from noise_adaptation import OnlineNoiseAdapter
    HAS_CORE_MODULES = True
except ImportError as e:
    print(f"Warning: Could not import core modules: {e}")
    HAS_CORE_MODULES = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Warning: PyYAML not installed, using default config")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("drisa_v2.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DRISA_HOME = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa")).expanduser()
DRISA_HOME.mkdir(parents=True, exist_ok=True)


class DrisaAssistant:
    """
    Main Drisa voice assistant orchestrator
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize Drisa assistant

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self.load_config()

        # State
        self.is_running = False
        self.is_listening = False
        self.is_processing_speech = False
        self._speech_gate_lock = threading.Lock()
        self._last_speech_fingerprint = None
        self._last_speech_fingerprint_at = 0.0
        self.last_wake_word_time = 0
        self.wake_word_cooldown = 2.0  # seconds between wake word detections
        self.processing_lock = threading.Lock()

        # Components
        self.audio_processor: Optional[AudioProcessor] = None
        self.wake_word_detector: Optional[WakeWordDetector] = None
        self.speech_processor: Optional[SpeechProcessor] = None
        self.noise_adapter: Optional[OnlineNoiseAdapter] = None

        # Queues for inter-component communication
        self.audio_queue = queue.Queue()
        self.speech_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Conversation context (memory array)
        self.conversation_history = []  # List of {"role": "user"/"assistant", "content": str}
        self.max_context_tokens = 2000  # Approx token limit before summarization
        self.context_summary = ""  # Compressed summary when history gets too long

        # Threads
        self.audio_thread: Optional[threading.Thread] = None
        self.processing_thread: Optional[threading.Thread] = None
        self.response_thread: Optional[threading.Thread] = None

        # Callbacks for audio processor
        self.audio_processor_callbacks_set = False

        logger.info("Drisa Assistant initialized")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        # Default configuration
        default_config = {
            "audio": {
                "sample_rate": 16000,
                "energy_threshold": 0.05,
                "noise_suppression": True,
                "vad_aggressiveness": 2,
                "frame_duration_ms": 30,
                "max_silence_frames": 60  # ~1.8s of silence before speech ends (60 frames * 30ms)
            },
            "wake_word": {
                "phrase": "olá drisa",
                "sensitivity": 0.7,
                "language": "pt",
                "cooldown_seconds": 2.0
            },
            "stt": {
                "primary": "api",
                "whisper_model": "models/ggml-base.bin",
                "deepgram_enabled": False,
                "confidence_threshold": 0.6
            },
            "tts": {
                "primary": "api",
                "espeak_voice": "pt",
                "deepgram_fallback": False,
                "speed": 150,
                "pitch": 50,
                "amplitude": 100
            },
            "llm": {
                "base_url": "http://127.0.0.1:8888/v1",
                "model": "AtomicChat/LFM3-1.7B-Uncensored-GGUF",
                "max_tokens": 150,
                "temperature": 0.7
            },
            "noise_adaptation": {
                "enabled": True,
                "model_update_interval": 300,
                "gpu_device": 0,
                "model_path": "models/noise_adaptation_model.pt"
            },
            "interface": {
                "system_tray": True,
                "web_port": 8765,
                "manual_controls": True
            },
            "paths": {
                "whisper_model_dir": "models/",
                "temp_dir": os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Drisa", "temp"),
                "log_dir": "./logs/",
                "audio_archive_dir": os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Drisa", "audio-archive")
            },
            "retention": {
                "urgent_free_gb": 6,
                "min_free_gb": 10,
                "max_local_hours": 24,
                "compress_audio": False
            },
            "nextcloud": {
                "enabled": True,
                "base_url": "https://cloud.iknowu.org/remote.php/dav/files",
                "username": "",
                "password": "",
                "remote_dir": "Drisa/Audio"
            }
        }

        if os.path.exists(self.config_path) and HAS_YAML:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                # Merge with defaults
                self._deep_update(default_config, user_config)
                logger.info(f"Loaded configuration from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load config from {self.config_path}: {e}")
                logger.info("Using default configuration")
        else:
            if not os.path.exists(self.config_path):
                logger.info(f"Config file {self.config_path} not found, using defaults")
            elif not HAS_YAML:
                logger.warning("PyYAML not installed, using default configuration")

        # Normalize stale placeholders to the local Unsloth API
        llm_cfg = default_config.setdefault("llm", {})
        if not llm_cfg.get("base_url") or "[IP_ADDRESS]" in str(llm_cfg.get("base_url", "")):
            llm_cfg["base_url"] = "http://127.0.0.1:8888/v1"
        default_config.setdefault("stt", {}).setdefault("primary", "api")
        default_config.setdefault("tts", {}).setdefault("primary", "api")

        # Ensure directories exist
        for path_key in ["whisper_model_dir", "temp_dir", "log_dir", "audio_archive_dir"]:
            path = Path(default_config["paths"][path_key])
            path.mkdir(parents=True, exist_ok=True)

        return default_config

    def _deep_update(self, target: dict, source: dict):
        """Recursively update nested dictionary"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value

    def initialize_components(self):
        """Initialize all components"""
        logger.info("Initializing components...")

        if not HAS_CORE_MODULES:
            logger.error("Core modules not available, cannot initialize")
            return False

        try:
            # Initialize audio processor
            logger.info("Initializing audio processor...")
            self.audio_processor = AudioProcessor(
                sample_rate=self.config["audio"]["sample_rate"],
                frame_duration_ms=self.config["audio"]["frame_duration_ms"],
                vad_aggressiveness=self.config["audio"]["vad_aggressiveness"],
                noise_reduce=self.config["audio"]["noise_suppression"],
                energy_threshold=self.config["audio"]["energy_threshold"],
                device=int(os.environ["DRISA_INPUT_DEVICE"]) if os.environ.get("DRISA_INPUT_DEVICE", "").strip().isdigit() else None,
                max_silence_frames=self.config["audio"].get("max_silence_frames", 60)
            )

            # Initialize wake word detector
            logger.info("Initializing wake word detector...")
            # For now, we'll use a simple approach - in production, use a proper wake word model
            self.wake_word_detector = WakeWordDetector(
                model_path=None,  # Placeholder - would use actual model in production
                sample_rate=self.config["audio"]["sample_rate"],
                chunk_duration_ms=1000,  # 1 second chunks
                threshold=self.config["wake_word"]["sensitivity"]
            )

            # Initialize speech processor
            logger.info("Initializing speech processor...")
            self.speech_processor = SpeechProcessor(
                model_size="base",
                device="cpu",
                compute_type="int8",
                sample_rate=16000
            )

            # Initialize noise adaptation
            logger.info("Initializing noise adaptation...")
            if self.config["noise_adaptation"]["enabled"]:
                model_path = os.path.join(
                    self.config["paths"]["whisper_model_dir"],
                    os.path.basename(self.config["noise_adaptation"]["model_path"])
                )
                self.noise_adapter = OnlineNoiseAdapter(
                    model_path=model_path if os.path.exists(model_path) else None,
                    device=None,  # Auto-detect CUDA/CPU
                    update_interval=self.config["noise_adaptation"]["model_update_interval"]
                )

            # Set up callbacks
            self.setup_callbacks()

            logger.info("All components initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            return False


    def _disk_free_gb(self) -> float:
        try:
            import shutil
            temp_dir = Path(self.config["paths"].get("temp_dir", "./temp/"))
            root = temp_dir.anchor or "C:/"
            usage = shutil.disk_usage(root)
            return usage.free / (1024**3)
        except Exception as e:
            logger.warning(f"Could not measure disk free space: {e}")
            return 999.0

    def _nextcloud_upload(self, local_path: str, rel_path: str) -> bool:
        cfg = self.config.get("nextcloud", {})
        if not cfg.get("enabled"):
            return False
        user = os.environ.get("DRISA_NEXTCLOUD_USER", cfg.get("username", "")).strip()
        pw = os.environ.get("DRISA_NEXTCLOUD_PASSWORD", cfg.get("password", "")).strip()
        if not user or not pw:
            logger.info("Nextcloud upload skipped: missing credentials")
            return False
        base = cfg.get("base_url", "").rstrip("/")
        remote_dir = cfg.get("remote_dir", "Drisa/Audio").strip("/")
        url = f"{base}/{user}/{remote_dir}/{rel_path}".replace("//", "/").replace("https:/", "https://").replace("http:/", "http://")
        try:
            import requests
            with open(local_path, "rb") as f:
                r = requests.put(url, data=f, auth=(user, pw), timeout=120)
            ok = r.status_code in (200, 201, 204)
            logger.info(f"Nextcloud upload {'ok' if ok else 'failed'}: {r.status_code} {url}")
            return ok
        except Exception as e:
            logger.error(f"Nextcloud upload failed: {e}")
            return False

    def _retain_or_offload_audio(self, path: Path) -> None:
        free_gb = self._disk_free_gb()
        retention = self.config.get("retention", {})
        urgent = free_gb < retention.get("urgent_free_gb", 6)
        low = free_gb < retention.get("min_free_gb", 10)
        rel_path = f"{time.strftime('%Y%m%d')}/{path.name}"
        if urgent:
            logger.warning(f"DISK URGENT: free={free_gb:.2f}GB — offloading {path.name}")
            self._nextcloud_upload(str(path), rel_path)
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return
        if low:
            logger.info(f"Low disk: free={free_gb:.2f}GB — queueing {path.name} for offload")
            self.offload_queue.put((str(path), rel_path))

    def setup_callbacks(self):
        """Set up callbacks between components"""
        if self.audio_processor:
            self.audio_processor.set_voice_callback(self.on_voice_detected)
            self.audio_processor.set_speech_end_callback(self.on_speech_end)

        if self.wake_word_detector:
            self.wake_word_detector.set_detection_callback(self.on_wake_word_detected)

    def on_voice_detected(self):
        """Callback when voice activity is detected"""
        logger.debug("Voice activity detected")
        # This could be used to update UI or trigger visual feedback

    def on_speech_end(self, audio_data: np.ndarray):
        """
        Callback when speech ends - process the audio

        Args:
            audio_data: Audio signal as numpy array
        """
        # Check if Gemini is still processing
        if hasattr(self, '_gemini_processing') and self._gemini_processing:
            logger.info("Gemini still processing, ignoring speech segment")
            return

        # Also verify minimum audio duration (ignore very short segments - likely noise)
        min_samples = self.config.get("audio", {}).get("min_speech_samples", 12000)  # ~750ms at 16kHz
        if len(audio_data) < min_samples:
            logger.debug(f"Speech segment too short ({len(audio_data)} samples), ignoring")
            return

        current_time = time.monotonic()
        fingerprint = hashlib.sha256(np.ascontiguousarray(audio_data).tobytes()).digest()
        with self._speech_gate_lock:
            if self.is_processing_speech:
                logger.debug("Already processing speech, ignoring")
                return
            if (
                fingerprint == self._last_speech_fingerprint
                and current_time - self._last_speech_fingerprint_at < 30.0
            ):
                logger.debug("Duplicate audio segment ignored")
                return
            self._last_speech_fingerprint = fingerprint
            self._last_speech_fingerprint_at = current_time
            self.is_processing_speech = True

        logger.info("Speech ended, starting processing...")
        # Put audio data in queue for processing
        self.speech_queue.put(audio_data)

        # Start processing thread if not already running
        if not self.processing_thread or not self.processing_thread.is_alive():
            self.processing_thread = threading.Thread(target=self.process_speech_loop, daemon=True)
            self.processing_thread.start()

    def on_wake_word_detected(self, confidence: float):
        """
        Callback when wake word is detected

        Args:
            confidence: Detection confidence (0-1)
        """
        current_time = time.time()

        # Check cooldown to prevent multiple detections
        if current_time - self.last_wake_word_time < self.wake_word_cooldown:
            logger.debug(f"Wake word ignored due to cooldown (confidence: {confidence:.2f})")
            return

        logger.info(f"Wake word 'Olá Drisa' detected! Confidence: {confidence:.2f}")
        self.last_wake_word_time = current_time

        # Here we could trigger a listening mode or visual feedback
        # For now, we'll let the normal speech processing handle it
        # In a more advanced implementation, we might start recording immediately

    def process_speech_loop(self):
        """Main speech processing loop"""
        logger.info("Speech processing loop started")

        while self.is_running:
            try:
                # Get audio data with timeout
                audio_data = self.speech_queue.get(timeout=1.0)

                # Process the speech
                self.process_speech_segment(audio_data)

                self.speech_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in speech processing loop: {e}", exc_info=True)
                self.is_processing_speech = False

        logger.info("Speech processing loop ended")

    def process_speech_segment(self, audio_data: np.ndarray):
        """Process a speech segment: noise adaptation, STT, intent, TTS"""
        with self.processing_lock:
            self._process_speech_segment_internal(audio_data)

    def _process_speech_segment_internal(self, audio_data: np.ndarray):
        """
        Process a speech segment: noise adaptation, STT, intent, TTS

        Args:
            audio_data: Audio signal as numpy array
        """
        try:
            logger.info(f"Processing speech segment: {len(audio_data)} samples")

            # Accept raw numpy audio or a WAV file path
            if isinstance(audio_data, str):
                import soundfile as sf
                if os.path.exists(audio_data):
                    logger.warning(f"audio_data is a path; loading WAV from {audio_data}")
                    audio_data, _sr = sf.read(audio_data, dtype="float32")
                else:
                    logger.error(f"audio_data is a string, not numpy array: {audio_data[:100]}")
                    return
            if not isinstance(audio_data, np.ndarray):
                logger.error(f"audio_data is {type(audio_data)}, not numpy array")
                return

            # Apply noise adaptation if enabled
            processed_audio = audio_data
            if self.noise_adapter and self.config["noise_adaptation"]["enabled"]:
                # Determine if voice is active (simple energy-based)
                energy = np.sqrt(np.mean(audio_data**2))
                is_voice_active = energy > self.config["audio"]["energy_threshold"]

                # Process frame by frame (in practice, we'd do this in real-time)
                # For simplicity, we'll process the whole segment
                if hasattr(self.noise_adapter, "process_frame"):
                    processed_audio = self.noise_adapter.process_frame(
                        audio_data,
                        sample_rate=self.config["audio"]["sample_rate"],
                        is_voice_active=is_voice_active
                    )
                else:
                    logger.warning("Noise adapter has no process_frame; skipping noise adaptation")

            # Save audio to a persistent file for later review + a temp file for STT
            import tempfile
            from pathlib import Path
            try:
                import soundfile as sf
                HAS_SOUNDFILE = True
            except ImportError:
                HAS_SOUNDFILE = False
                logger.warning("soundfile not available, using wave module instead")
                import wave

            audio_dir = Path(self.config["paths"].get("audio_archive_dir", self.config["paths"].get("temp_dir", "./temp/")))
            audio_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            persistent_audio_path = audio_dir / f"drisa_{stamp}.wav"

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=self.config["paths"].get("temp_dir")) as tmp_file:
                tmp_filename = tmp_file.name
                # Write audio as 16-bit PCM WAV
                audio_int16 = (processed_audio * 32767).astype(np.int16)

                if HAS_SOUNDFILE:
                    sf.write(tmp_filename, audio_int16, self.config["audio"]["sample_rate"])
                    sf.write(str(persistent_audio_path), audio_int16, self.config["audio"]["sample_rate"])
                else:
                    # Write using wave module
                    with wave.open(tmp_filename, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # 16-bit
                        wf.setframerate(self.config["audio"]["sample_rate"])
                        wf.writeframes(audio_int16.tobytes())
                    with wave.open(str(persistent_audio_path), 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.config["audio"]["sample_rate"])
                        wf.writeframes(audio_int16.tobytes())
            logger.info(f"Saved audio to {persistent_audio_path}")
            self._retain_or_offload_audio(persistent_audio_path)

            try:
                # Detect language (simple approach: assume PT unless we detect English words)
                # In practice, we'd use a language detection model
                language = self.detect_language_simple(audio_data)

                stt_engine = os.environ.get("DRISA_STT_ENGINE", self.config["stt"].get("primary", "local")).strip().lower()
                if self.config["stt"].get("deepgram_enabled") and stt_engine in ("deepgram", "auto"):
                    stt_engine = "deepgram"
                logger.info(f"Using STT engine: {stt_engine} (lang={language})")

                # Transcribe
                logger.info("Starting transcription...")
                stt_result = self.speech_processor.transcribe(processed_audio, language, engine=stt_engine)

                if isinstance(stt_result, str):
                    transcript_text = stt_result.strip()
                    stt_ok = bool(transcript_text)
                    stt_conf = 1.0 if stt_ok else 0.0
                else:
                    transcript_text = (stt_result.get("text", "") or "").strip()
                    stt_ok = bool(transcript_text)
                    stt_conf = float(stt_result.get("confidence", 0.0) or 0.0)

                if stt_ok:

                    # Filter out non-speech transcriptions (Whisper outputs [MUSIC], [NOISE], etc.)
                    non_speech_keywords = ['MÚSICA', 'MUSIC', 'FUNDO', 'NOISE', 'SILÊNCIO', 'SILENCE', 'BACKGROUND']
                    is_non_speech = False
                    for kw in non_speech_keywords:
                        if kw in transcript_text.upper():
                            is_non_speech = True
                            break
                    if is_non_speech:
                        logger.info(f"Ignoring non-speech transcription: '{transcript_text}'")
                        return

                    timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    logger.info(f"Transcription: '{transcript_text}' (confidence: {stt_conf:.2f}) @ {timestamp_iso}")

                    # Write transcription to bridge file for C++ world
                    try:
                        # Write to a dedicated text bridge file (separate from audio level)
                        text_path = DRISA_HOME / "drisa_text.tmp"
                        with open(text_path, "w", encoding="utf-8") as f:
                            f.write(f"{timestamp_iso} | {transcript_text}")
                        logger.info(f"Wrote transcription to bridge: '{transcript_text}'")
                    except Exception as e:
                        logger.error(f"Failed to write bridge: {e}")

                    # Process the command/query
                    response_text = self.process_command(transcript_text, language)

                    if response_text:
                        logger.info(f"Response: '{response_text}'")

                        # Synthesize response
                        logger.info("Starting speech synthesis...")
                        # Anti-eco: descarta a captura do micro enquanto a Drisa fala
                        try:
                            self.audio_processor.set_muted(True)
                        except Exception:
                            pass
                        try:
                            tts_result = self.speech_processor.synthesize_speech(response_text, language)
                        finally:
                            try:
                                self.audio_processor.set_muted(False)
                            except Exception:
                                pass

                        if tts_result["success"]:
                            logger.info(f"TTS successful: {tts_result['audio_file_path']}")
                            # In a real implementation, we would play this audio
                            # For now, we just log it
                            self.play_audio_response(tts_result["audio_file_path"])
                        else:
                            logger.error(f"TTS failed: {tts_result['error']}")

                            # Fallback to eSpeak if Deepgram failed
                            if tts_result.get("provider") == "deepgram" and self.config["tts"]["deepgram_fallback"]:
                                logger.info("Falling back to eSpeak NG for TTS")
                                try:
                                    fallback_result = self.speech_processor.tts_provider.synthesize(
                                        response_text,
                                        tts_result["audio_file_path"],
                                        language
                                    )
                                    if fallback_result["success"]:
                                        logger.info(f"Fallback TTS successful: {fallback_result['audio_file_path']}")
                                        self.play_audio_response(fallback_result["audio_file_path"])
                                    else:
                                        logger.error(f"Fallback TTS also failed: {fallback_result['error']}")
                                except Exception as e:
                                    logger.error(f"TTS fallback internal error: {e}")
                    else:
                        logger.info("No response generated from command")
                else:
                    logger.warning("Transcription empty or failed")

            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_filename)
                except:
                    pass

        except Exception as e:
            logger.error(f"Error processing speech segment: {e}", exc_info=True)
        finally:
            self.is_processing_speech = False

    def detect_language_simple(self, audio_data: np.ndarray) -> str:
        """
        Simple language detection based on audio characteristics
        In practice, we'd use a proper language identification model

        Args:
            audio_data: Audio signal

        Returns:
            Language code ("pt" or "en")
        """
        # This is a placeholder - real language detection would be more sophisticated
        # For now, default to Portuguese as requested
        return "pt"

    def process_command(self, text: str, language: str) -> str:
        """
        Process transcribed text using Gemini CLI

        Args:
            text: Transcribed text
            language: Language code

        Returns:
            Response text
        """
        logger.info(f"Processing command: '{text}' ({language})")

        # Set flag to prevent other speech processing while responding
        self._gemini_processing = True

        try:
            import subprocess
            import shutil

            # Find gemini CLI
            gemini = shutil.which("gemini")
            if not gemini:
                gemini = shutil.which("gemini.cmd")
            if not gemini:
                for p in [
                    os.path.expanduser("~/.npm-global/bin/gemini"),
                    os.path.expanduser("~/AppData/Roaming/npm/gemini"),
                    os.path.expanduser("~/AppData/Roaming/npm/gemini.cmd"),
                ]:
                    if os.path.isfile(p):
                        gemini = p
                        break

            if not gemini:
                logger.info("Gemini CLI unavailable; trying the configured local LLM")

            # Try LOCAL LLM first (unsloth server neste PC — zero custo, zero OpenRouter)
            try:
                import json as _json
                import urllib.request

                llm_cfg = self.config.get("llm", {})
                base_url = os.environ.get("DRISA_UNSLOTH_URL", llm_cfg.get("base_url", "http://127.0.0.1:8888/v1")).rstrip("/")
                key = os.environ.get("DRISA_UNSLOTH_KEY", "").strip()
                model = os.environ.get("DRISA_LLM_MODEL", llm_cfg.get("model", "AtomicChat/LFM3-1.7B-Uncensored-GGUF"))
                max_tokens = int(os.environ.get("DRISA_LLM_MAX_TOKENS", llm_cfg.get("max_tokens", 150)))
                temperature = float(os.environ.get("DRISA_LLM_TEMPERATURE", llm_cfg.get("temperature", 0.7)))

                payload = _json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": (
                            "Tu és a Drisa, uma assistente de voz amigável e entusiasta. "
                            "O teu nome é Drisa (diminutivo de Adriana). "
                            "Falas com o Kiko, o teu utilizador. "
                            "Responde de forma natural, direta e em português de Portugal. "
                            "Dá apenas a resposta final, curta, natural e pronta para ser dita em voz alta pelo Kokoro. "
                            "Não mostres raciocínio, análise, passos internos, etiquetas ou markdown. "
                            "Não uses emojis. Se não souberes, dizes."
                        )},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }).encode("utf-8")

                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=payload,
                    headers=headers
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))

                response = prepare_spoken_text(data["choices"][0]["message"]["content"])
                if is_utterance_echo(text, response):
                    logger.warning("Unsloth LLM echoed the utterance; ignoring the response")
                    response = ""
                if response:
                    logger.info(f"Local LLM response: '{response}'")
                    try:
                        with open(DRISA_HOME / "drisa_response.tmp", "w", encoding="utf-8") as f:
                            f.write(response)
                    except Exception as e:
                        logger.error(f"Failed to write response bridge: {e}")
                    self._gemini_processing = False
                    return response
                logger.warning("Unsloth LLM returned empty response")
            except Exception as e:
                logger.warning(f"Unsloth LLM failed: {e}")

            if os.environ.get("DRISA_LLM_FALLBACK", "").strip().lower() not in ("1", "true", "yes", "gemini"):
                logger.warning("Unsloth LLM failed, Gemini fallback disabled")
                self._gemini_processing = False
                return self._simple_response(text, language)

            if not gemini:
                logger.warning("Gemini fallback requested but the CLI is unavailable")
                self._gemini_processing = False
                return self._simple_response(text, language)

            # Build prompt
            prompt = (
                "Tu és a Drisa, uma assistente de voz amigável e entusiasta. "
                "O teu nome é Drisa (diminutivo de Adriana). "
                "Falas com o Kiko, o teu utilizador. "
                "Responde de forma natural, direta e em português de Portugal. "
                "Mantém as respostas curtas e conversacionais (máximo 2-3 frases). "
                "Nunca uses markdown ou formatação especial. "
                "Responde apenas com texto simples.\n\n"
                f"Kiko disse: {text}"
            )

            # Call Gemini CLI
            result = subprocess.run(
                [gemini, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "GEMINI_CLI_NO_COLOR": "1", "TERM": "dumb"}
            )

            if result.returncode == 0 and result.stdout.strip():
                response = prepare_spoken_text(result.stdout)
                if is_utterance_echo(text, response):
                    logger.warning("Gemini echoed the utterance; ignoring the response")
                    response = ""
                if response:
                    logger.info(f"Gemini response: '{response}'")

                    # Write response to bridge file for C++ world chat
                    try:
                        text_path = DRISA_HOME / "drisa_response.tmp"
                        with open(text_path, "w", encoding="utf-8") as f:
                            f.write(response)
                    except Exception as e:
                        logger.error(f"Failed to write response bridge: {e}")

                    self._gemini_processing = False
                    return response
            else:
                logger.warning(f"Gemini failed (exit={result.returncode})")

        except subprocess.TimeoutExpired:
            logger.warning("Gemini timed out")
        except FileNotFoundError:
            logger.warning("Gemini CLI not found")
        except Exception as e:
            logger.error(f"Gemini error: {e}")

        self._gemini_processing = False
        return self._simple_response(text, language)

    def _simple_response(self, text: str, language: str) -> str:
        """Return a safe fallback without repeating the user's utterance."""
        text_lower = text.lower().strip()

        if any(greeting in text_lower for greeting in ["oi", "olá", "hello", "hi"]):
            resp = "Oi Kiko! Tudo bem? Como posso ajudar você hoje?"
        elif any(thanks in text_lower for thanks in ["obrigado", "obrigada", "thanks", "thank you"]):
            resp = "De nada, Kiko! Fico feliz em ajudar."
        elif any(bye in text_lower for bye in ["tchau", "adeus", "bye", "goodbye"]):
            resp = "Tchau Kiko! Até a próxima!"
        elif "como você está" in text_lower or "how are you" in text_lower:
            resp = "Estou ótima, Kiko! Pronto para ajudar você com o que precisar."
        elif "que horas são" in text_lower or "what time is it" in text_lower:
            import datetime
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M")
            resp = f"São {time_str}, Kiko."
        else:
            resp = "Desculpa, não consegui preparar uma resposta agora. Podes tentar outra vez?"

        # Write fallback response to bridge too
        try:
            text_path = DRISA_HOME / "drisa_response.tmp"
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(resp)
        except Exception as e:
            logger.error(f"Failed to write fallback response bridge: {e}")

        return resp

    def play_audio_response(self, audio_file_path: str):
        """
        Play audio response (placeholder - in practice would use audio playback)

        Args:
            audio_file_path: Path to audio file
        """
        logger.info(f"Playing audio response: {audio_file_path}")
        # In a real implementation, we would use:
        # - simpleaudio
        # - pydub
        # - winsound (Windows)
        # - or system audio player
        # For now, we just log that we would play it
        pass

    def start(self):
        """Start the Drisa assistant"""
        if self.is_running:
            logger.warning("Drisa is already running")
            return False

        logger.info("Starting Drisa Assistant...")

        # Initialize components
        if not self.initialize_components():
            logger.error("Failed to initialize components")
            return False

        # Set running flag
        self.is_running = True

        # Start audio processing
        logger.info("Starting audio processing...")
        self.audio_processor.start_listening()

        # Start wake word detection
        logger.info("Starting wake word detection...")
        self.wake_word_detector.start_listening()

        # Start response thread (for playing audio, etc.)
        self.response_thread = threading.Thread(target=self.response_loop, daemon=True)
        self.response_thread.start()

        logger.info("Drisa Assistant started successfully!")
        logger.info("Say 'Olá Drisa' to activate voice control")
        return True

    def stop(self):
        """Stop the Drisa assistant"""
        if not self.is_running:
            logger.warning("Drisa is not running")
            return False

        logger.info("Stopping Drisa Assistant...")

        # Set running flag
        self.is_running = False

        # Stop components
        if self.audio_processor:
            self.audio_processor.stop_listening()

        if self.wake_word_detector:
            self.wake_word_detector.stop_listening()

        # Wait for threads to finish
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)

        if self.response_thread and self.response_thread.is_alive():
            self.response_thread.join(timeout=5.0)

        logger.info("Drisa Assistant stopped")
        return True

    def response_loop(self):
        """Response loop for handling TTS playback and other responses"""
        logger.info("Response loop started")

        while self.is_running:
            try:
                # In a more complete implementation, this would handle:
                # - Playing audio responses
                # - Sending notifications
                # - Updating UI
                # - Handling commands that don't require speech
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in response loop: {e}")
                time.sleep(1)

        logger.info("Response loop ended")

    def run_interactive(self):
        """Run in interactive mode (for testing)"""
        logger.info("Starting Drisa in interactive mode")

        if not self.start():
            logger.error("Failed to start Drisa")
            return

        try:
            print("\nDrisa Voice Assistant is running!")
            print("Say 'Olá Drisa' to activate voice control")
            print("Press Ctrl+C to stop\n")

            # Keep main thread alive
            while self.is_running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    if 'drisa' in globals() and drisa:
        drisa.stop()
    sys.exit(0)


def main():
    """Main entry point"""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run Drisa assistant
    global drisa
    drisa = DrisaAssistant()

    # Check if we should run as service or interactive
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        logger.info("Starting as Windows service...")
        drisa.start()
        # Keep running until stopped
        try:
            while drisa.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            drisa.stop()
    else:
        # Run interactively
        drisa.run_interactive()


if __name__ == "__main__":
    main()
