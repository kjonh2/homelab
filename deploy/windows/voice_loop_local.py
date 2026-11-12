#!/usr/bin/env python3
# Drisa Voice Loop — portátil do Kiko (unsloth: STT+LLM+TTS API)
# mic -> VAD (webrtcvad) -> Unsloth STT -> Unsloth LLM -> Unsloth Kokoro -> sounddevice
# Servidor HTTP :8111 -> widget indicador (Hermes chat) + heartbeat do homelab
import os, sys, time, json, subprocess, tempfile, threading, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
# Ensure the local venv site-packages is visible even when launched from another Python.
_here = os.path.dirname(os.path.abspath(__file__))
_venv_sp = os.path.join(_here, "venv", "Lib", "site-packages")
if os.path.isdir(_venv_sp) and _venv_sp not in sys.path:
    sys.path.insert(0, _venv_sp)
BASE_DIR = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa")).expanduser().resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
BRIDGE_DIR = str(BASE_DIR) + os.sep
import numpy as np
import sounddevice as sd
import requests
from drisa_speech_text import prepare_spoken_text
try:
    import webrtcvad
except Exception:
    webrtcvad = None

KEY = os.environ.get("DRISA_UNSLOTH_KEY", "").strip()
if not KEY:
    try:
        KEY = (BASE_DIR / "unsloth.key").read_text(encoding="utf-8").strip()
    except OSError:
        KEY = ""
BASE_URL = os.environ.get("DRISA_UNSLOTH_URL", "http://localhost:8888/v1").rstrip("/")
AUDIO_URL = os.environ.get("DRISA_AUDIO_URL", "http://127.0.0.1:8766/v1").rstrip("/")
STT_URL = os.environ.get("DRISA_STT_URL", AUDIO_URL).rstrip("/")
TTS_URL = os.environ.get("DRISA_TTS_URL", AUDIO_URL).rstrip("/")
AUDIO_KEY = os.environ.get("DRISA_AUDIO_KEY", "").strip()
_AUDIO_MODELS = {
    "moss": {"package_id": "moss_transcribe_diarize_q4_k", "task": "asr"},
    "parakeet": {"package_id": "parakeet_tdt_q8_0", "task": "asr"},
    "kokoro": {"package_id": "kokoro_82m_q8_0", "task": "tts"},
}
_AUDIO_MODEL_ALIASES = {
    "moss": "moss", "moss-transcribe-diarize-gguf": "moss",
    "audio-cpp/audio.cpp-gguf/moss-transcribe-diarize-gguf": "moss",
    "moss_transcribe_diarize_q4_k": "moss",
    "parakeet": "parakeet", "parakeet-tdt-0.6b-v3-gguf": "parakeet",
    "audio-cpp/audio.cpp-gguf/parakeet-tdt-0.6b-v3-gguf": "parakeet",
    "parakeet_tdt_q8_0": "parakeet",
    "kokoro": "kokoro", "kokoro-82m-gguf": "kokoro",
    "audio-cpp/audio.cpp-gguf/kokoro-82m-gguf": "kokoro", "kokoro_82m_q8_0": "kokoro",
}

def _normalize_audio_model(value, default):
    key = str(value or default).strip().lower()
    return _AUDIO_MODEL_ALIASES.get(key, key)
_remote_llm_url = os.environ.get("DRISA_LLM_URL", "").strip()
LLM_URL = (_remote_llm_url or BASE_URL).rstrip("/")
LLM_KEY = os.environ.get("DRISA_LLM_KEY", "").strip()
if not LLM_KEY and _remote_llm_url:
    try:
        LLM_KEY = (BASE_DIR / "iku_lfm3.key").read_text(encoding="utf-8").strip()
    except OSError:
        LLM_KEY = ""
elif not LLM_KEY:
    LLM_KEY = KEY
# ---- Audio autosave encriptado (5s, 1 minuto local) ----
from cryptography.fernet import Fernet
AUDIO_DIR = BASE_DIR / "drisa-audio"
AUDIO_KEY_FILE = BASE_DIR / "drisa_audio.key"
AUDIO_CHUNK_SECONDS = 10
AUDIO_KEEP_CHUNKS = 6  # 6 * 10s = 1 minuto
os.makedirs(AUDIO_DIR, exist_ok=True)
if not os.path.exists(AUDIO_KEY_FILE):
    with open(AUDIO_KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())
with open(AUDIO_KEY_FILE, "rb") as f:
    _FERNET = Fernet(f.read().strip())
_enc_buf = bytearray()
_last_enc_write = time.time()
_last_dec_check = None

def audio_autosave_tick(chunk_bytes, force=False):
    """Acumula mic audio; a cada 5s grava encriptado, verifica decrypt e poda."""
    global _enc_buf, _last_enc_write, _last_dec_check
    _enc_buf += chunk_bytes
    now = time.time()
    if not force and (now - _last_enc_write) < AUDIO_CHUNK_SECONDS:
        return
    _last_enc_write = now
    if len(_enc_buf) < SAMPLE_RATE * 2:  # <1s? ignora
        _enc_buf.clear(); return
    data = bytes(_enc_buf); _enc_buf.clear()
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(AUDIO_DIR, f"enc_{ts}.bin")
    with open(path, "wb") as f:
        f.write(_FERNET.encrypt(data))
    # decrypt em tempo real para verificar
    t0 = time.time()
    with open(path, "rb") as f:
        dec = _FERNET.decrypt(f.read())
    dt = time.time() - t0
    ok = dec == data
    # last 5s sample desencriptado em tempo real (WAV pronto a enviar/ouvir)
    _last_dec_check = {
        "ficheiro": os.path.basename(path), "bytes": len(dec), "decrypt_ok": ok,
        "decrypt_s": round(dt, 4), "encrypted_at_rest": True,
    }
    STATE["local"]["autosave"] = _last_dec_check
    log(f"AUDIO autosave {os.path.basename(path)} ({len(data)//1024}KB) decrypt_ok={ok} ({dt*1000:.1f}ms)")
    # podar: manter so AUDIO_KEEP_CHUNKS
    snaps = sorted(p for p in os.listdir(AUDIO_DIR) if p.startswith("enc_") and p.endswith(".bin"))
    for old in snaps[:-AUDIO_KEEP_CHUNKS]:
        try: os.remove(os.path.join(AUDIO_DIR, old))
        except OSError: pass

LLM_MODEL = os.environ.get("DRISA_LLM_MODEL", "AtomicChat/LFM3-1.7B-Uncensored-GGUF")
STT_MODEL = _normalize_audio_model(os.environ.get("DRISA_STT_MODEL"), "moss")
STT_FALLBACK_MODEL = _normalize_audio_model(os.environ.get("DRISA_STT_FALLBACK_MODEL"), "parakeet")
TTS_MODEL = _normalize_audio_model(os.environ.get("DRISA_TTS_MODEL"), "kokoro")
TTS_VOICE = os.environ.get("DRISA_TTS_VOICE", "pf_dora")
WHISPER = r"C:\Whisper.Cpp\whisper-cli.exe"
WHISPER_MODEL = r"C:\Whisper.Cpp\models\ggml-base.bin"
GAIN = 6
SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME = SAMPLE_RATE * FRAME_MS // 1000
MAX_SILENCE_FRAMES = 60          # 1.8s
MIN_SPEECH_SAMPLES = 12000       # ~750ms

SYSTEM = ("Tu és a Drisa, assistente de voz PT-PT do Kiko. Dá apenas a resposta final, "
          "curta, natural e pronta para ser dita em voz alta pelo Kokoro. Não mostres raciocínio, "
          "análise, passos internos, etiquetas ou markdown. Se não souberes, dizes.")

LOG = os.path.expanduser(r"~\drisa_local.log")
def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")

STATE = {"local": {"ativo": False, "vad": 0, "fala": False, "ultimo_stt": "", "ult_ms": 0},
         "homelab": {"ativo": False, "vad": 0, "fala": False, "micro": "", "ts": 0}}
if os.environ.get("DRISA_STT_ENGINE", "api").strip().lower() in ("local", "whisper", "whisper.cpp"):
    STATE["local"]["stt_engine"] = "Whisper.cpp"
else:
    STATE["local"]["stt_engine"] = "MOSS + Parakeet"
_lock = threading.Lock()
_audio_request_lock = threading.RLock()

def ensure_audio_model(api_url, model, headers):
    if api_url.rstrip("/") != AUDIO_URL or model not in _AUDIO_MODELS:
        return
    response = requests.get(f"{api_url}/models", headers=headers, timeout=(5, 15))
    response.raise_for_status()
    models = response.json().get("data", [])
    current = next((item for item in models if item.get("id") == model), None)
    if not current:
        raise RuntimeError(f"Modelo {model} não encontrado no homelab.")
    if current.get("loaded") is True:
        return
    response = requests.post(f"{api_url}/models/load", headers={**headers, "Content-Type": "application/json"},
                             json={"id": model, **_AUDIO_MODELS[model]}, timeout=(5, 120))
    response.raise_for_status()
    result = response.json()
    if result.get("success") is False or result.get("error"):
        raise RuntimeError(str(result.get("error") or f"Falha ao carregar {model}."))

NON_SPEECH = ("[MÚSICA]", "[MUSIC]", "[MUSICA]", "[APLAUSO]", "[APPLAUSE]", "[RISADA]",
              "[LAUGHTER]", "[SILÊNCIO]", "[SILENCE]", "[RUÍDO]", "[NOISE]",
              "[BLANK_AUDIO]", "[INAUDIBLE]")
def filtro(txt):
    t = txt.strip().upper()
    return not t or any(m in t for m in NON_SPEECH)

def stt_whisper_cpp(wav_path):
    t0 = time.time()
    r = subprocess.run([WHISPER, "-t", "4", "-m", WHISPER_MODEL, "-l", "pt", "-nt", "-f", wav_path],
                       capture_output=True, text=True, timeout=120)
    txt = r.stdout.strip()
    log(f"STT local {time.time()-t0:.1f}s -> {txt!r}")
    return txt, time.time()-t0

def stt_unsloth(wav_path, model=None):
    t0 = time.time()
    headers = {}
    if AUDIO_KEY:
        headers["Authorization"] = f"Bearer {AUDIO_KEY}"
    with open(wav_path, "rb") as f:
        data = f.read()
    files = {"file": (os.path.basename(wav_path), data, "audio/wav")}
    selected_model = model or STT_MODEL
    with _audio_request_lock:
        ensure_audio_model(STT_URL, selected_model, headers)
        timeout = (5, 30 if STT_URL == AUDIO_URL and selected_model == "moss" else 120)
        r = requests.post(f"{STT_URL}/audio/transcriptions", headers=headers, files=files,
                          data={"model": selected_model}, timeout=timeout)
        r.raise_for_status()
    txt = (r.json().get("text") or "").strip()
    log(f"STT audio service {time.time()-t0:.1f}s -> {txt!r}")
    return txt, time.time()-t0
def llm(texto):
    t0 = time.time()
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = f"Bearer {LLM_KEY}"
    r = requests.post(f"{LLM_URL}/chat/completions",
        headers=headers,
        json={"model": LLM_MODEL, "max_tokens": 600, "temperature": 0.7,
              "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}]},
        timeout=180)
    r.raise_for_status()
    resp = prepare_spoken_text(r.json()["choices"][0]["message"].get("content") or "")
    log(f"LLM {time.time()-t0:.1f}s -> {resp[:100]!r}")
    return resp

def tts_kokoro(texto):
    t0 = time.time()
    headers = {"Content-Type": "application/json"}
    if AUDIO_KEY:
        headers["Authorization"] = f"Bearer {AUDIO_KEY}"
    with _audio_request_lock:
        ensure_audio_model(TTS_URL, TTS_MODEL, headers)
        r = requests.post(f"{TTS_URL}/audio/speech",
            headers=headers,
            json={"model": TTS_MODEL, "input": texto, "voice": TTS_VOICE, "response_format": "wav"},
            timeout=(5, 120))
        r.raise_for_status()
    tmp = os.path.join(tempfile.gettempdir(), "drisa_tts_local.wav")
    with open(tmp, "wb") as f:
        f.write(r.content)
    log(f"TTS kokoro {time.time()-t0:.1f}s ({len(r.content)//1024}KB)")
    return tmp

def tocar(wav_path):
    with wave.open(wav_path, "rb") as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    sd.play(data, sr)
    sd.wait()

def falar(texto):
    if os.environ.get("DRISA_TTS_ENGINE", "api").strip().lower() in ("sapi", "system", "windows"):
        text_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
                f.write(texto)
                text_path = f.name
            script = os.path.join(_here, "drisa_tts_sapi.ps1")
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", script, "-TextFile", text_path],
                           capture_output=True, text=True, timeout=90, check=True)
            log("TTS Windows SAPI")
            return
        finally:
            if text_path and os.path.exists(text_path):
                os.remove(text_path)
    wav = tts_kokoro(texto)
    try:
        tocar(wav)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass

def pipeline(samples, mic_name):
    wav_path = None
    with _lock:
        STATE["local"]["fala"] = True
    try:
        a = np.frombuffer(samples, dtype=np.int16).astype(np.float32) * GAIN
        samples = np.clip(a, -32767, 32767).astype(np.int16).tobytes()
        with tempfile.NamedTemporaryFile(suffix=".wav", prefix="drisa_seg_", delete=False) as temp_audio:
            wav_path = temp_audio.name
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE)
            w.writeframes(samples)
        if os.environ.get("DRISA_STT_ENGINE", "api").strip().lower() in ("local", "whisper", "whisper.cpp"):
            try:
                txt, t_stt = stt_whisper_cpp(wav_path)
            except Exception as e:
                log(f"STT local falhou: {e}")
                txt, t_stt = "", 0.0
        else:
            try:
                txt, t_stt = stt_unsloth(wav_path)
            except Exception as e:
                log(f"STT unsloth falhou: {e}")
                txt, t_stt = "", 0.0
            if not txt and STT_FALLBACK_MODEL != STT_MODEL:
                try:
                    txt, t_stt = stt_unsloth(wav_path, STT_FALLBACK_MODEL)
                    log(f"STT fallback Parakeet {t_stt:.1f}s")
                except Exception as e:
                    log(f"STT fallback Parakeet falhou: {e}")
                    txt, t_stt = "", 0.0
        if not txt and os.environ.get("DRISA_STT_FALLBACK", "").strip().lower() in ("1", "true", "yes", "local", "whisper"):
            txt, t_stt = stt_whisper_cpp(wav_path)
        if filtro(txt):
            with _lock:
                STATE["local"]["ultimo_stt"] = "(não-fala)"
            return
        with _lock:
            STATE["local"]["ultimo_stt"] = txt
            STATE["local"]["ult_ms"] = int(t_stt*1000)
        with open(BRIDGE_DIR + "drisa_text.tmp", "w", encoding="utf-8") as f:
            f.write(txt)
        try:
            resp = llm(txt)
            resp = prepare_spoken_text(resp)
            if resp:
                with open(BRIDGE_DIR + "drisa_response.tmp", "w", encoding="utf-8") as f:
                    f.write(resp)
                falar(resp)
        except Exception as e:
            log(f"LLM/TTS falhou: {e}")
    except Exception as e:
        log(f"pipeline falhou: {e}")
    finally:
        if wav_path:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        with _lock:
            STATE["local"]["fala"] = False


def _run_pipeline_guarded(samples, microphone, lock):
    try:
        pipeline(samples, microphone)
    finally:
        lock.release()

STATUS_PORT = int(os.environ.get("DRISA_STATUS_PORT", "8111"))
STATUS_PAGE = BASE_DIR / "drisa-status.html"

class Handler(BaseHTTPRequestHandler):
    def _valid_host(self):
        return self.headers.get("Host", "").lower() in {
            f"127.0.0.1:{STATUS_PORT}", f"localhost:{STATUS_PORT}"
        }

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(405); self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        if not self._valid_host():
            self._send(400, "text/plain; charset=utf-8", b"invalid host")
        elif self.path in ("/", "/index.html"):
            try:
                self._send(200, "text/html; charset=utf-8", STATUS_PAGE.read_bytes())
            except OSError:
                self._send(503, "text/plain; charset=utf-8", b"status page unavailable")
        elif self.path == "/status":
            with _lock:
                hl = dict(STATE["homelab"])
                hl["ativo"] = (time.time() - hl.get("ts", 0)) < 10 and hl["ts"] > 0
                st = {"local": dict(STATE["local"]), "homelab": hl, "ts": time.time()}
            body = json.dumps(st).encode()
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")
    def do_POST(self):
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://127.0.0.1:{STATUS_PORT}", f"http://localhost:{STATUS_PORT}"}
        if not self._valid_host() or (origin and origin not in allowed_origins):
            self._send(403, "text/plain; charset=utf-8", b"forbidden")
            return
        if self.path == "/heartbeat":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n < 0 or n > 4096:
                    self._send(413, "text/plain; charset=utf-8", b"request too large")
                    return
                d = json.loads(self.rfile.read(n))
                if not isinstance(d, dict):
                    raise ValueError("heartbeat must be an object")
                allowed = {key: d[key] for key in ("ativo", "vad", "fala", "micro") if key in d}
                with _lock:
                    STATE["homelab"].update(allowed); STATE["homelab"]["ts"] = time.time()
                self._send(200, "application/json; charset=utf-8", b'{"ok":true}')
            except Exception:
                self._send(400, "text/plain; charset=utf-8", b"invalid heartbeat")
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")
    def log_message(self, *a): pass

def http_server():
    srv = ThreadingHTTPServer(("127.0.0.1", STATUS_PORT), Handler)
    srv.serve_forever()

def main():
    log("=== Drisa Voice Loop a arrancar (Unsloth STT+LLM+TTS) ===")
    threading.Thread(target=http_server, daemon=True).start()
    log(f"HTTP em 127.0.0.1:{STATUS_PORT}")
    devices = sd.query_devices()
    default_in = sd.default.device[0]
    mic_name = devices[default_in]["name"]
    log(f"Micro: {mic_name}")
    vad = webrtcvad.Vad(2) if webrtcvad else None
    ring = bytearray(); silence = 0; in_speech = False
    proc_lock = threading.Lock()

    def callback(indata, frames, t, status):
        nonlocal ring, silence, in_speech
        chunk = bytes(indata)
        try:
            audio_autosave_tick(chunk)
        except Exception as e:
            log(f"audio autosave falhou: {e}")
        a = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) * GAIN
        level = float(np.sqrt((a ** 2).mean()))
        if level > 3000: level = 3000
        with _lock:
            STATE["local"]["vad"] = int(level / 30)
            STATE["local"]["ativo"] = True
        is_speech = vad.is_speech(chunk, SAMPLE_RATE) if vad else (level > 600)
        if is_speech:
            ring += chunk; silence = 0
            if not in_speech and len(ring) // 2 >= MIN_SPEECH_SAMPLES // 3:
                in_speech = True
        else:
            if in_speech:
                ring += chunk; silence += 1
                if silence >= MAX_SILENCE_FRAMES:
                    in_speech = False
                    samples = bytes(ring[:-MAX_SILENCE_FRAMES * FRAME * 2])
                    ring.clear(); silence = 0
                    dur = len(samples) / 2 / SAMPLE_RATE
                    if dur >= 0.75 and proc_lock.acquire(blocking=False):
                        log(f"VAD fim: {dur:.1f}s")
                        try:
                            threading.Thread(target=_run_pipeline_guarded, args=(samples, mic_name, proc_lock), daemon=True).start()
                        except Exception:
                            proc_lock.release()
                            raise

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=FRAME, callback=callback, device=None):
        log("InputStream ativo — loop VAD a correr")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()

