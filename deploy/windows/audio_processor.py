"""
AudioProcessor — VAD estilo Discord.

Gate combinado: um frame só conta como VOZ se o webrtcvad (agressivo) diz voz
E a energia passa o noise floor DINÂMICO (calibra sozinho com o ruído de fundo:
rua, cão, etc.). Abrir a fala exige 3 frames consecutivos de voz (ignora
latidos/cliques); fechar exige 1.8s de silêncio; o segmento só é emitido se
tiver >= 1.2s de voz e >= 35% de frames de voz. Durante o TTS da Drisa a
captura é MUTADA (anti-eco da própria voz).
"""
import numpy as np
import sounddevice as sd
import webrtcvad
import threading
import queue
import logging
import time
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self, sample_rate=16000, frame_duration_ms=30, vad_aggressiveness=3,
                 noise_reduce=True, energy_threshold=0.08, device=1, max_silence_frames=60):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        # VAD sempre no modo mais rigoroso (estilo Discord — corta ruído/ladidos)
        self.vad = webrtcvad.Vad(2)
        self.energy_threshold = energy_threshold  # usado como clamp mínimo absoluto (0.3x)
        self.device = device

        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.thread = None
        self.stream = None

        self.voice_callback = None
        self.speech_end_callback = None

        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
        self.max_silence_frames = max_silence_frames  # 60 frames * 30ms = ~1.8s
        # Bound a VAD segment that never reaches silence; otherwise background
        # audio can grow into an oversized upload and repeatedly trigger Drisa.
        self.max_segment_frames = max(1, int(60_000 / frame_duration_ms))

        # --- VAD mais permissivo para fala contínua ---
        self.open_frames_needed = 1          # abrir quase imediato
        self.pending_open = 0
        self.min_speech_frames = 10          # ~0.3s de voz mínima p/ emitir segmento
        self.min_voice_ratio = 0.05          # >= 5% dos frames do segmento são voz
        self.voice_frames_in_segment = 0
        self.muted = False

        # Noise floor dinâmico (calibra sozinho com o ruído ambiente)
        self.noise_floor_ema = None
        self.noise_floor = 0.02

    def set_voice_callback(self, callback):
        self.voice_callback = callback

    def set_speech_end_callback(self, callback):
        self.speech_end_callback = callback

    def set_muted(self, muted: bool):
        """Anti-eco: durante o TTS da Drisa a captura é descartada."""
        self.muted = muted
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
        self.pending_open = 0
        self.voice_frames_in_segment = 0
        if muted:
            logger.info("AudioProcessor MUTED (TTS em curso — anti-eco)")
        else:
            logger.info("AudioProcessor UNMUTED (a ouvir)")

    def start_listening(self):
        self.is_listening = True
        self.thread = threading.Thread(target=self._capture_and_process, daemon=True)
        self.thread.start()
        logger.info(f"AudioProcessor started on device {self.device} (VAD Discord-style)")

    def stop_listening(self):
        self.is_listening = False
        if self.stream:
            try:
                self.stream.stop()
            except Exception:
                pass
        logger.info("AudioProcessor stopped")

    def _update_noise_floor(self, energy: float):
        """Calibra o ruído de fundo (rua, cão) — só chamado fora de fala.
        Desce rápido para o mínimo medido, sobe muito devagar (picos não sobem o floor)."""
        if self.noise_floor_ema is None:
            self.noise_floor_ema = energy
        else:
            alpha = 0.06 if energy < self.noise_floor_ema else 0.004
            self.noise_floor_ema += alpha * (energy - self.noise_floor_ema)
        self.noise_floor = max(0.008, self.noise_floor_ema * 1.4, self.energy_threshold * 0.12)

    def _write_bridge(self, energy: float):
        """Drisa Bridge: nível de áudio p/ o mundo C++ (preserva o texto)."""
        try:
            existing_text = ""
            bridge_path = Path(os.environ.get("DRISA_HOME", Path(__file__).resolve().parent)) / "drisa_bridge.tmp"
            try:
                with open(bridge_path, "r", encoding="utf-8") as f:
                    parts = f.read().strip().split("|", 3)
                    if len(parts) == 4:
                        existing_text = parts[3]
            except Exception:
                pass
            state = "1" if self.is_speaking else "0"
            if existing_text:
                with open(bridge_path, "w", encoding="utf-8") as f:
                    f.write(f"{energy:.4f}|0|{state}|{existing_text}")
            else:
                with open(bridge_path, "w", encoding="utf-8") as f:
                    f.write(f"{energy:.4f}|0|{state}")
        except Exception:
            pass

    def _emit_segment(self):
        """Fecha o segmento: valida (duração + % voz) e emite, ou descarta como ruído."""
        buf = self.speech_buffer
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
        self.pending_open = 0

        total = len(buf)
        ratio = self.voice_frames_in_segment / max(1, total)
        if total >= self.min_speech_frames and ratio >= self.min_voice_ratio:
            if self.speech_end_callback:
                audio_data = np.concatenate(buf)
                self.speech_end_callback(audio_data)
        else:
            logger.info(
                f"Segmento descartado (ruído): {total*0.03:.1f}s, voz={ratio:.0%} "
                f"(< {self.min_speech_frames*0.03:.1f}s / {self.min_voice_ratio:.0%})"
            )
        self.voice_frames_in_segment = 0

    def _capture_and_process(self):
        """Capture audio using sounddevice and process with VAD (Discord-style gate)."""
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio status: {status}")
            if not self.is_listening:
                return
            if self.muted:
                return  # anti-eco: durante o TTS nada entra no buffer

            # Convert to mono float32
            frame = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()

            # Energy check
            energy = np.sqrt(np.mean(frame**2))

            self._write_bridge(energy)

            # Gate combinado: VAD ML E energia acima do noise floor dinâmico
            if not self.is_speaking:
                self._update_noise_floor(energy)

            pcm_data = (frame * 32767).astype(np.int16).tobytes()
            vad_says_speech = self.vad.is_speech(pcm_data, self.sample_rate)
            is_voice = vad_says_speech and (energy > self.noise_floor)

            if not self.is_speaking:
                # Exigir 3 frames consecutivos de voz p/ abrir (anti latido/clique)
                self.pending_open = self.pending_open + 1 if is_voice else 0
                if self.pending_open >= self.open_frames_needed:
                    self.is_speaking = True
                    self.silence_frames = 0
                    self.voice_frames_in_segment = self.pending_open
                    logger.info(f"Speech started (noise_floor={self.noise_floor:.4f})")
                else:
                    # Pré-roll ring: guarda ~0.3s de contexto p/ não cortar o início
                    self.speech_buffer.append(frame.copy())
                    if len(self.speech_buffer) > 12:
                        self.speech_buffer = self.speech_buffer[-10:]
                return

            # Em fala: apenda TUDO (voz + pausas naturais entre palavras)
            self.speech_buffer.append(frame.copy())
            if is_voice:
                self.voice_frames_in_segment += 1
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                if self.silence_frames >= self.max_silence_frames:
                    self._emit_segment()
                    return
            if len(self.speech_buffer) >= self.max_segment_frames:
                logger.warning(
                    "Speech segment reached %d seconds without confirmed silence; dropping it",
                    self.max_segment_frames * self.frame_duration_ms // 1000,
                )
                self.speech_buffer = []
                self.is_speaking = False
                self.silence_frames = 0
                self.pending_open = 0
                self.voice_frames_in_segment = 0

        try:
            with sd.InputStream(device=self.device, samplerate=self.sample_rate,
                                channels=1, dtype='float32', callback=callback,
                                blocksize=self.frame_size):
                while self.is_listening:
                    sd.sleep(100)
        except Exception as e:
            logger.error(f"Audio capture error: {e}")
