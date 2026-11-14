"""
Drisa Voice Gateway — Homeland PC
WebSocket server: app Android (ou qualquer cliente) liga-se, envia áudio,
recebe transcrição, resposta LLM e TTS do backend Unsloth (via bridge
Drisa para o mundo 3D) .

Política (decidida pelo Kiko):
  - TUDO é gravado em disco (recordings/) e transcrito para o vault Obsidian.
  - Só dispositivos com token válido + device_id na allowlist têm resposta.
  - Dispositivos desconhecidos: áudio gravado + registado em Obsidian, sem resposta.

Config: gateway_config.json (port, allowlist, policies por dispositivo)
"""
import asyncio
import base64
import binascii
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import websockets
from drisa_speech_text import is_utterance_echo, prepare_spoken_text
from drisa_memory import chat as memory_chat

BASE = Path(os.environ.get("DRISA_HOME", str(Path.home() / "workspace" / "drisa")))
WHISPER_EXE = Path(os.environ.get("DRISA_WHISPER_EXE", r"C:\Whisper.Cpp\whisper-cli.exe"))
WHISPER_MODEL = Path(os.environ.get("DRISA_WHISPER_MODEL", r"C:\Whisper.Cpp\models\ggml-base.bin"))
VAULT = Path(os.environ.get("DRISA_VAULT_PATH", str(Path.home() / "Documents" / "Obsidian Vault" / "Drisa" / "Voice Gateway")))
RECORDINGS = BASE / "recordings"
CONFIG_PATH = BASE / "gateway_config.json"
TOKEN_PATH = BASE / "gateway_token.txt"
BRIDGE_TEXT = BASE / "drisa_text.tmp"
BRIDGE_RESP = BASE / "drisa_response.tmp"
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_AUDIO_BASE64_CHARS = ((MAX_AUDIO_BYTES + 2) // 3) * 4
MAX_WEBSOCKET_MESSAGE_BYTES = 8 * 1024 * 1024

RECORDINGS.mkdir(exist_ok=True)
VAULT.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "port": 8765,
    "stt_engine": "api",                # "api" | "whisper" | "deepgram"
    "unsloth_url": "http://127.0.0.1:8888/v1",
    "stt_model": "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF",
    "fallback_stt_model": "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF",
    "llm_model": "AtomicChat/LFM3-1.7B-Uncensored-GGUF",
    "tts_model": "kokoro",
    "tts_voice": "pf_dora",
    "allowlist": [],
    "policies": {},
    "unknown": {"transcribe": True, "reply": False, "priority": False}
}

_AUDIO_MODEL_ALIASES = {
    "moss": "moss",
    "moss-transcribe-diarize-gguf": "moss",
    "audio-cpp/audio.cpp-gguf/moss-transcribe-diarize-gguf": "moss",
    "moss_transcribe_diarize_q4_k": "moss",
    "parakeet": "parakeet",
    "parakeet-tdt-0.6b-v3-gguf": "parakeet",
    "audio-cpp/audio.cpp-gguf/parakeet-tdt-0.6b-v3-gguf": "parakeet",
    "parakeet_tdt_q8_0": "parakeet",
    "kokoro": "kokoro",
    "kokoro-82m-gguf": "kokoro",
    "audio-cpp/audio.cpp-gguf/kokoro-82m-gguf": "kokoro",
    "kokoro_82m_q8_0": "kokoro",
}


def _normalize_audio_model(value: str, default: str) -> str:
    key = str(value or default).strip().lower()
    return _AUDIO_MODEL_ALIASES.get(key, key)


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Keep the selected model IDs intact here: Unsloth expects full package IDs,
    # while audio.cpp on the homelab expects short IDs (moss/parakeet/kokoro).
    if cfg.get("unsloth_url") == "http://127.0.0.1:8888/v1":
        cfg["unsloth_url"] = "http://127.0.0.1:8888/v1"
    return cfg


def load_token():
    if not TOKEN_PATH.exists():
        import secrets
        TOKEN_PATH.write_text(secrets.token_hex(24))
    return TOKEN_PATH.read_text().strip()


def _unsloth_cfg():
    cfg = load_config()
    llm_host = os.environ.get("DRISA_LLM_HOST", cfg.get("llm_host", "pc")).strip().lower()
    llm_url = os.environ.get("DRISA_LLM_URL", "").strip()
    if not llm_url:
        llm_url = cfg.get("llm_url", "").strip()
    if not llm_url:
        llm_url = os.environ.get("DRISA_UNSLOTH_URL", cfg.get("unsloth_url", "http://127.0.0.1:8888/v1")).strip()
    llm_url = llm_url.rstrip("/")

    llm_key = os.environ.get("DRISA_LLM_KEY", "").strip()
    if not llm_key and llm_host == "vps":
        try:
            llm_key = (BASE / "iku_lfm3.key").read_text(encoding="utf-8").strip()
        except OSError:
            llm_key = ""
    if not llm_key and llm_host != "vps":
        llm_key = os.environ.get("DRISA_UNSLOTH_KEY", cfg.get("unsloth_key", "")).strip()

    local_url = os.environ.get("DRISA_UNSLOTH_URL", cfg.get("unsloth_url", "http://127.0.0.1:8888/v1")).strip().rstrip("/")
    audio_url = os.environ.get("DRISA_AUDIO_URL", cfg.get("audio_url", "")).strip().rstrip("/")
    stt_url = os.environ.get("DRISA_STT_URL", cfg.get("stt_url", "")).strip().rstrip("/")
    if not stt_url:
        stt_url = audio_url if cfg.get("stt_host") == "homelab" else local_url
    tts_url = os.environ.get("DRISA_TTS_URL", cfg.get("tts_url", "")).strip().rstrip("/")
    if not tts_url:
        tts_url = audio_url if cfg.get("tts_host") == "homelab" else local_url

    def model_id(value, default, endpoint):
        selected = str(value or default).strip()
        return _normalize_audio_model(selected, default) if audio_url and endpoint == audio_url else selected

    return {
        "base_url": local_url,
        "key": os.environ.get("DRISA_UNSLOTH_KEY", cfg.get("unsloth_key", "")).strip(),
        "audio_url": os.environ.get("DRISA_AUDIO_URL", cfg.get("audio_url", "")).strip().rstrip("/"),
        "audio_key": os.environ.get("DRISA_AUDIO_KEY", cfg.get("audio_key", "")).strip(),
        "stt_url": stt_url,
        "tts_url": tts_url,
        "stt_key": os.environ.get("DRISA_STT_KEY", cfg.get("stt_key", "")).strip(),
        "tts_key": os.environ.get("DRISA_TTS_KEY", cfg.get("tts_key", "")).strip(),
        "llm_host": llm_host,
        "llm_url": llm_url,
        "llm_key": llm_key,
        "stt_model": model_id(os.environ.get("DRISA_STT_MODEL", cfg.get("stt_model")), "audio-cpp/audio.cpp-gguf/MOSS-Transcribe-Diarize-GGUF", stt_url),
        "fallback_stt_model": model_id(os.environ.get("DRISA_STT_FALLBACK_MODEL", cfg.get("fallback_stt_model")), "audio-cpp/audio.cpp-gguf/Parakeet-TDT-0.6B-v3-GGUF", stt_url),
        "llm_model": os.environ.get("DRISA_LLM_MODEL", cfg.get("llm_model", "AtomicChat/LFM3-1.7B-Uncensored-GGUF")),
        "tts_model": model_id(os.environ.get("DRISA_TTS_MODEL", cfg.get("tts_model")), "kokoro", tts_url),
        "tts_voice": os.environ.get("DRISA_TTS_VOICE", cfg.get("tts_voice", "pf_dora")),
    }


_MODEL_CONFIG_LOCK = threading.Lock()
_AUDIO_REQUEST_LOCK = threading.RLock()
_HOMELAB_ACTIVE_MODEL: str | None = None
_HOMELAB_MODEL_PACKAGES = {
    "moss": {"package_id": "moss_transcribe_diarize_q4_k", "task": "asr"},
    "parakeet": {"package_id": "parakeet_tdt_q8_0", "task": "asr"},
    "kokoro": {"package_id": "kokoro_82m_q8_0", "task": "tts"},
}
_VPS_LLM_URL = "https://vps-4e5174e4.tail2931da.ts.net:8445/v1"
_VPS_MODELS_URL = "https://vps-4e5174e4.tail2931da.ts.net:8445/models"


def _mcp_tool(name: str, arguments: dict) -> dict:
    import requests
    cfg = _unsloth_cfg()
    base = cfg["base_url"].removesuffix("/v1") + "/mcp/"
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if cfg["key"]:
        headers["Authorization"] = f"Bearer {cfg['key']}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    response = requests.post(base, json=body, headers=headers, timeout=(5, 260))
    if response.status_code == 401:
        raise RuntimeError("O Unsloth Studio recusou a API key da Drisa. Configura uma chave válida em Settings > API.")
    if response.status_code == 404:
        raise RuntimeError("O MCP do Unsloth Studio está desativado. Ativa Allow agent connections em Settings > Agents.")
    response.raise_for_status()
    envelope = None
    for line in response.text.splitlines():
        if line.startswith("data: "):
            try:
                envelope = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    if envelope is None:
        try:
            envelope = response.json()
        except ValueError as exc:
            raise RuntimeError("Resposta MCP inválida do Unsloth.") from exc
    if envelope.get("error"):
        raise RuntimeError(str(envelope["error"].get("message", "Erro MCP do Unsloth.")))
    result = envelope.get("result", {})
    if result.get("isError"):
        contents = result.get("content", [])
        detail = next((item.get("text", "") for item in contents if item.get("type") == "text"), "Erro ao gerir modelos no Unsloth.")
        raise RuntimeError(detail[:500])
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    contents = result.get("content", [])
    detail = next((item.get("text", "") for item in contents if item.get("type") == "text"), "")
    try:
        return json.loads(detail)
    except (TypeError, json.JSONDecodeError):
        return {"message": detail}


def _is_image_generation_model(item: dict) -> bool:
    """Hide image-generation entries misclassified by the MCP catalog as LLMs."""
    identity = " ".join(str(item.get(field, "")) for field in ("id", "display_name")).lower()
    markers = ("flux-3-image", "stable-diffusion", "dall-e", "dalle", "text-to-image", "image-generation")
    return any(marker in identity for marker in markers)


def _pc_model_catalog(category: str) -> dict:
    if category not in ("llm", "stt", "tts"):
        raise ValueError("Categoria de modelo inválida.")
    result = _mcp_tool("list_models", {"kind": category, "source": "local", "loaded_only": False})
    entries = result.get("models", [])
    if category == "llm":
        entries = [item for item in entries if not _is_image_generation_model(item)]
    models = [{"id": item.get("id", ""), "loaded": bool(item.get("loaded", False))}
              for item in entries if item.get("id")]
    return {"models": models, "selected": _selected_model(load_config(), "pc", category), "message": ""}


def _vps_model_catalog(category: str) -> dict:
    if category != "llm":
        return {"models": [], "selected": "", "message": "A VPS tem modelos de texto; transcrição e Kokoro estão no portátil."}
    import requests
    key_path = BASE / "iku_lfm3.key"
    if not key_path.exists():
        raise RuntimeError("A chave privada da API da VPS não está configurada no portátil.")
    response = requests.get(_VPS_MODELS_URL, headers={"Authorization": f"Bearer {key_path.read_text(encoding='utf-8').strip()}"}, timeout=(5, 15))
    response.raise_for_status()
    body = response.json()
    models = []
    for item in body.get("data", body.get("models", [])):
        model_id = item.get("id") or item.get("model") or item.get("name")
        if not model_id:
            continue
        raw_status = item.get("status", item.get("state", ""))
        if isinstance(raw_status, dict):
            raw_status = raw_status.get("value", raw_status.get("state", ""))
        status = str(raw_status).lower()
        models.append({"id": model_id, "loaded": item.get("loaded") is True or status == "loaded"})
    return {"models": models, "selected": _selected_model(load_config(), "vps", category), "message": ""}


def _homelab_model_catalog(category: str) -> dict:
    global _HOMELAB_ACTIVE_MODEL
    if category == "llm":
        return {"models": [], "selected": "", "message": "O homelab serve áudio; os modelos de texto estão no portátil ou na VPS."}
    allowed = {"stt": {"moss", "parakeet"}, "tts": {"kokoro"}}
    if category not in allowed:
        raise ValueError("Categoria de modelo inválida.")
    import requests
    cfg = _unsloth_cfg()
    base_url = cfg["audio_url"] or cfg["stt_url"] or cfg["tts_url"]
    if not base_url:
        raise RuntimeError("O endereço do serviço de áudio do homelab não está configurado.")
    headers = {"Authorization": f"Bearer {cfg['audio_key']}"} if cfg["audio_key"] else {}
    response = requests.get(f"{base_url}/models", headers=headers, timeout=(5, 15))
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("data", payload.get("models", []))
    entry_by_id = {str(item.get("id", "")): item for item in entries if isinstance(item, dict)}
    available = set(entry_by_id)
    configured = sorted(allowed[category] & available)
    with _AUDIO_REQUEST_LOCK:
        loaded_model = _HOMELAB_ACTIVE_MODEL
    models = [{"id": model_id, "loaded": (
        bool(entry_by_id[model_id]["loaded"]) if isinstance(entry_by_id[model_id].get("loaded"), bool)
        else model_id == loaded_model
    )} for model_id in configured]
    return {"models": models, "selected": _selected_model(load_config(), "homelab", category), "message": ""}


def _selected_model(cfg: dict, host: str, category: str) -> str:
    if category == "llm":
        if cfg.get("llm_host", "pc") != host:
            return ""
        return str(cfg.get("llm_model", ""))
    if host not in ("pc", "homelab"):
        return ""
    if cfg.get(f"{category}_host", "pc") != host:
        return ""
    selected = str(cfg.get({"stt": "stt_model", "tts": "tts_model"}.get(category, ""), ""))
    return _normalize_audio_model(selected, selected) if host == "homelab" else selected


def model_catalog(host: str, category: str) -> dict:
    host = str(host).lower()
    category = str(category).lower()
    if host == "pc":
        return _pc_model_catalog(category)
    if host == "vps":
        return _vps_model_catalog(category)
    if host == "homelab":
        return _homelab_model_catalog(category)
    raise ValueError("Host desconhecido.")


def _save_model_selection(host: str, category: str, model_id: str) -> None:
    with _MODEL_CONFIG_LOCK:
        cfg = load_config()
        if category == "llm":
            cfg["llm_model"] = model_id
            cfg["llm_host"] = host
            cfg["llm_url"] = _VPS_LLM_URL if host == "vps" else os.environ.get("DRISA_UNSLOTH_URL", cfg.get("unsloth_url", "http://127.0.0.1:8888/v1")).rstrip("/")
            os.environ["DRISA_LLM_HOST"] = host
            os.environ["DRISA_LLM_MODEL"] = model_id
            os.environ["DRISA_LLM_URL"] = cfg["llm_url"]
        elif category == "stt" and host == "pc":
            cfg["stt_model"] = model_id
            cfg["stt_host"] = "pc"
            cfg["stt_url"] = os.environ.get("DRISA_UNSLOTH_URL", cfg.get("unsloth_url", "http://127.0.0.1:8888/v1")).rstrip("/")
            os.environ["DRISA_STT_MODEL"] = model_id
            os.environ["DRISA_STT_URL"] = cfg["stt_url"]
        elif category == "tts" and host == "pc":
            cfg["tts_model"] = model_id
            cfg["tts_host"] = "pc"
            cfg["tts_url"] = os.environ.get("DRISA_UNSLOTH_URL", cfg.get("unsloth_url", "http://127.0.0.1:8888/v1")).rstrip("/")
            os.environ["DRISA_TTS_MODEL"] = model_id
            os.environ["DRISA_TTS_URL"] = cfg["tts_url"]
        elif category == "stt" and host == "homelab":
            previous_model = _normalize_audio_model(cfg.get("stt_model"), "moss")
            fallback_model = _normalize_audio_model(cfg.get("fallback_stt_model"), "parakeet")
            if model_id != previous_model and fallback_model == model_id:
                cfg["fallback_stt_model"] = previous_model
                os.environ["DRISA_STT_FALLBACK_MODEL"] = previous_model
            cfg["stt_model"] = model_id
            cfg["stt_host"] = "homelab"
            cfg["stt_url"] = os.environ.get("DRISA_AUDIO_URL", cfg.get("audio_url", "http://127.0.0.1:8766/v1")).rstrip("/")
            os.environ["DRISA_STT_MODEL"] = model_id
            os.environ["DRISA_STT_URL"] = cfg["stt_url"]
        elif category == "tts" and host == "homelab":
            cfg["tts_model"] = model_id
            cfg["tts_host"] = "homelab"
            cfg["tts_url"] = os.environ.get("DRISA_AUDIO_URL", cfg.get("audio_url", "http://127.0.0.1:8766/v1")).rstrip("/")
            os.environ["DRISA_TTS_MODEL"] = model_id
            os.environ["DRISA_TTS_URL"] = cfg["tts_url"]
        else:
            raise ValueError("Esta categoria não pode ser carregada nesse host.")
        temp_path = CONFIG_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(CONFIG_PATH)


def load_model_for_app(host: str, category: str, model_id: str) -> str:
    host = str(host).lower()
    category = str(category).lower()
    model_id = str(model_id).strip()
    if not model_id or len(model_id) > 300:
        raise ValueError("Seleciona um modelo válido.")
    catalog = model_catalog(host, category)
    if model_id not in {item["id"] for item in catalog["models"]}:
        raise ValueError("Esse modelo não aparece no catálogo deste host.")
    if host == "pc":
        result = _mcp_tool("load_model", {"kind": category, "model": model_id, "wait_s": 240})
        _save_model_selection(host, category, model_id)
        return str(result.get("message") or "Modelo carregado no portátil.")
    if host == "vps" and category == "llm":
        import requests
        key_path = BASE / "iku_lfm3.key"
        key = key_path.read_text(encoding="utf-8").strip()
        response = requests.post(_VPS_MODELS_URL + "/load", json={"model": model_id},
                                 headers={"Authorization": f"Bearer {key}"}, timeout=(5, 260))
        response.raise_for_status()
        result = response.json()
        if result.get("success") is False:
            raise RuntimeError("A VPS recusou o carregamento do modelo.")
        deadline = time.monotonic() + 240
        while True:
            loaded_model = next((item for item in _vps_model_catalog("llm")["models"]
                                 if item["id"] == model_id), None)
            if loaded_model and loaded_model["loaded"]:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"O modelo {model_id} não ficou pronto na VPS dentro do prazo.")
            time.sleep(min(2, remaining))
        _save_model_selection(host, category, model_id)
        return "Modelo carregado na VPS."
    if host == "homelab" and category in ("stt", "tts"):
        package = _HOMELAB_MODEL_PACKAGES.get(model_id)
        if not package or model_id not in {item["id"] for item in catalog["models"]}:
            raise ValueError("Este modelo não está instalado no homelab.")
        import requests
        cfg = _unsloth_cfg()
        base_url = cfg["audio_url"] or cfg["stt_url"] or cfg["tts_url"]
        headers = {"Content-Type": "application/json"}
        if cfg["audio_key"]:
            headers["Authorization"] = f"Bearer {cfg['audio_key']}"
        with _AUDIO_REQUEST_LOCK:
            response = requests.post(f"{base_url}/models/load",
                                     json={"id": model_id, **package},
                                     headers=headers, timeout=(5, 260))
            response.raise_for_status()
            result = response.json()
            if result.get("success") is False or result.get("error"):
                raise RuntimeError(str(result.get("error") or "O servidor de áudio recusou o modelo."))
            _save_model_selection(host, category, model_id)
            global _HOMELAB_ACTIVE_MODEL
            _HOMELAB_ACTIVE_MODEL = model_id
        return f"Modelo {model_id} carregado no homelab."
    raise ValueError("Esta categoria não pode ser carregada nesse host.")


def _recording_device_slug(device_id: str) -> str:
    """Restrict untrusted device IDs to a safe filename component."""
    safe = "".join(char if char.isascii() and (char.isalnum() or char in "_-") else "_"
                    for char in str(device_id)[:64]).strip("_")
    return safe or "unknown"


def decode_audio_payload(encoded: object) -> bytes:
    """Decode one bounded base64 RIFF/WAVE payload from the Android client."""
    if not isinstance(encoded, str) or len(encoded) > MAX_AUDIO_BASE64_CHARS:
        raise ValueError("audio payload too large or invalid")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio payload is not valid base64") from exc
    if (
        len(audio) > MAX_AUDIO_BYTES
        or len(audio) < 12
        or audio[:4] != b"RIFF"
        or audio[8:12] != b"WAVE"
        or int.from_bytes(audio[4:8], "little") != len(audio) - 8
    ):
        raise ValueError("audio payload is not a bounded RIFF/WAVE file")
    return audio


def _auth_headers():
    cfg = _unsloth_cfg()
    headers = {"Content-Type": "application/json"}
    if cfg["key"]:
        headers["Authorization"] = f"Bearer {cfg['key']}"
    return headers


def _ensure_homelab_model(requests, base_url: str, headers: dict, model_id: str) -> None:
    """Load a configured homelab audio model before sending inference to it."""
    package = _HOMELAB_MODEL_PACKAGES.get(model_id)
    if not package:
        raise ValueError(f"Modelo de áudio do homelab desconhecido: {model_id}")
    response = requests.get(f"{base_url}/models", headers=headers, timeout=(5, 15))
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("data", payload.get("models", []))
    model = next((item for item in entries if isinstance(item, dict) and item.get("id") == model_id), None)
    if not model:
        raise RuntimeError(f"O modelo {model_id} não está configurado no homelab.")
    if model.get("loaded") is True:
        return
    load_response = requests.post(
        f"{base_url}/models/load",
        json={"id": model_id, **package},
        headers={**headers, "Content-Type": "application/json"},
        timeout=(5, 120),
    )
    load_response.raise_for_status()
    loaded = load_response.json()
    if loaded.get("success") is False or loaded.get("error"):
        raise RuntimeError(str(loaded.get("error") or f"Não foi possível carregar {model_id}."))


def unsloth_transcribe(wav_path: Path, model: str | None = None) -> str:
    """STT via Unsloth OpenAI-compatible endpoint."""
    try:
        import requests
        cfg = _unsloth_cfg()
        base_url = cfg["stt_url"] or cfg["audio_url"] or cfg["base_url"]
        key = cfg["stt_key"] or (cfg["audio_key"] if base_url == cfg["audio_url"] else cfg["key"])
        files = {"file": (wav_path.name, wav_path.read_bytes(), "audio/wav")}
        data = {"model": model or cfg["stt_model"]}
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        with _AUDIO_REQUEST_LOCK:
            is_homelab = bool(cfg["audio_url"]) and base_url == cfg["audio_url"]
            if is_homelab:
                _ensure_homelab_model(requests, base_url, headers, data["model"])
            inference_timeout = 30 if is_homelab and data["model"] == "moss" else 120
            r = requests.post(f"{base_url}/audio/transcriptions", headers=headers, files=files, data=data,
                              timeout=(5, inference_timeout))
            r.raise_for_status()
            if is_homelab:
                global _HOMELAB_ACTIVE_MODEL
                _HOMELAB_ACTIVE_MODEL = data["model"]
        payload = r.json()
        return (payload.get("text") or "").strip()
    except Exception as e:
        print(f"[unsloth/stt] erro: {e}")
        return ""


def whisper_transcribe(wav_path: Path) -> str:
    """Fallback STT local, convertido para 16k mono se preciso."""
    try:
        prepared = wav_path.with_suffix(".16k.wav")
        try:
            import soundfile as sf
            import numpy as np
            data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
            mono = data.mean(axis=1)
            target = 16000
            if sr != target:
                n_out = int(len(mono) * target / sr)
                x_old = np.linspace(0.0, 1.0, len(mono), endpoint=False)
                x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
                mono = np.interp(x_new, x_old, mono)
            sf.write(str(prepared), mono, target, format="WAV")
        except Exception as e:
            print(f"[prep] conversão falhou, uso original: {e}")
            prepared = wav_path
        out = subprocess.run(
            [str(WHISPER_EXE), "-m", str(WHISPER_MODEL), "-f", str(prepared),
             "-l", "auto", "-nt", "--no-prints"],
            capture_output=True, text=True, timeout=120
        )
        text = out.stdout.strip()
        return text
    except Exception as e:
        print(f"[whisper] erro: {e}")
        return ""


def log_to_obsidian(device_id: str, user: str, text: str, kind: str = "transcript"):
    """Append diário no vault. Tudo fica registado no Homeland."""
    day = datetime.now().strftime("%Y-%m-%d")
    note = VAULT / f"{day}.md"
    ts = datetime.now().strftime("%H:%M:%S")
    with open(note, "a", encoding="utf-8") as f:
        f.write(f"- **{ts}** `{device_id}` ({kind}): {text}\n")


def llm_reply(text: str) -> str:
    """Resposta da Drisa via Unsloth chat/completions."""
    try:
        import requests
        cfg = _unsloth_cfg()
        owner = os.environ.get("DRISA_OWNER_NAME", cfg.get("assistant_owner", "utilizador")).strip() or "utilizador"
        system_prompt = f"És a Drisa, assistente pessoal de {owner}. Responde em português de Portugal com uma resposta final, natural e pronta a ser dita em voz alta pelo Kokoro. Limita-te a duas frases curtas e, sempre que possível, a 40 palavras. Não mostres raciocínio, análise, passos internos, etiquetas ou markdown. Se não souberes, dizes."
        headers = {"Content-Type": "application/json"}
        if cfg["llm_key"]:
            headers["Authorization"] = f"Bearer {cfg['llm_key']}"
        reply = memory_chat(
            text, system_prompt=system_prompt, base_url=cfg["llm_url"], key=cfg["llm_key"],
            model=cfg["llm_model"], max_tokens=120, temperature=0.7,
            spoken_cleaner=prepare_spoken_text,
        )
        if reply is None:
            payload = {"model": cfg["llm_model"], "messages": [
                {"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
                "max_tokens": 120, "temperature": 0.7}
            r = requests.post(f"{cfg['llm_url']}/chat/completions", json=payload, headers=headers, timeout=90)
            r.raise_for_status()
            reply = prepare_spoken_text(r.json()["choices"][0]["message"]["content"])
        if is_utterance_echo(text, reply):
            print("[llm] resposta igual à transcrição ignorada")
            return ""
        return reply
    except Exception as e:
        print(f"[llm] erro: {e}")
        return ""


def send_to_drisa(text: str, user: str):
    """Escreve no bridge para o mundo Drisa apanhar (mantém integração com o mundo 3D)."""
    try:
        with open(BRIDGE_TEXT, "a", encoding="utf-8") as f:
            f.write(f"[Tu]: {text}\n")
    except Exception as e:
        print(f"[bridge] erro: {e}")


def read_drisa_reply():
    """Lê a última resposta da Drisa no bridge (se houver)."""
    try:
        lines = BRIDGE_RESP.read_text(encoding="utf-8").strip().splitlines()
        return lines[-1] if lines else ""
    except Exception:
        return ""


def tts_kokoro(text: str) -> bytes | None:
    """Gera WAV via Unsloth Kokoro e devolve bytes (para o telemóvel reproduzir)."""
    try:
        if os.environ.get("DRISA_TTS_ENGINE", "api").strip().lower() in ("sapi", "system", "windows"):
            text_path = wave_path = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
                    f.write(text)
                    text_path = f.name
                with tempfile.NamedTemporaryFile("wb", suffix=".wav", delete=False) as f:
                    wave_path = f.name
                subprocess.run([
                    "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-File", str(BASE / "drisa_tts_sapi.ps1"), "-TextFile", text_path, "-WaveFile", wave_path,
                ], capture_output=True, text=True, timeout=120, check=True)
                return Path(wave_path).read_bytes()
            finally:
                for path in (text_path, wave_path):
                    if path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
        import requests
        cfg = _unsloth_cfg()
        base_url = cfg["tts_url"] or cfg["audio_url"] or cfg["base_url"]
        key = cfg["tts_key"] or (cfg["audio_key"] if base_url == cfg["audio_url"] else cfg["key"])
        payload = {"model": cfg["tts_model"], "input": text, "voice": cfg["tts_voice"], "response_format": "wav"}
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with _AUDIO_REQUEST_LOCK:
            is_homelab = bool(cfg["audio_url"]) and base_url == cfg["audio_url"]
            if is_homelab:
                _ensure_homelab_model(requests, base_url, headers, payload["model"])
            r = requests.post(f"{base_url}/audio/speech", json=payload, headers=headers, timeout=(5, 120))
            r.raise_for_status()
            if is_homelab:
                global _HOMELAB_ACTIVE_MODEL
                _HOMELAB_ACTIVE_MODEL = payload["model"]
        return r.content
    except Exception as e:
        print(f"[tts] erro: {e}")
        return None


def deepgram_transcribe(wav_path: Path) -> str:
    """STT via Deepgram nova-3 (multi-idioma). Key: env DEEPGRAM_API_KEY ou deepgram.key."""
    try:
        import urllib.request
        key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if not key:
            kf = BASE / "deepgram.key"
            if kf.exists():
                key = kf.read_text().strip()
        if not key:
            return ""
        cfg = load_config()
        lang = cfg.get("deepgram_language", "multi")
        url = f"https://api.deepgram.com/v1/listen?model=nova-3&language={lang}&smart_format=true&punctuate=true"
        data = wav_path.read_bytes()
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Token {key}",
            "Content-Type": "audio/wav",
        })
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        alts = d.get("results", {}).get("channels", [{}])[0].get("alternatives", [])
        text = alts[0].get("transcript", "").strip() if alts else ""
        return text
    except Exception as e:
        print(f"[deepgram] erro: {e}")
        return ""


def transcribe(wav_path: Path) -> str:
    """Motor principal de STT (Unsloth API por defeito)."""
    cfg = load_config()
    api_cfg = _unsloth_cfg()
    engine = os.environ.get("DRISA_STT_ENGINE", cfg.get("stt_engine", "api")).strip().lower()
    text = ""
    if engine in ("api", "unsloth"):
        text = unsloth_transcribe(wav_path, api_cfg["stt_model"])
        if not text and api_cfg["fallback_stt_model"] != api_cfg["stt_model"]:
            print(f"[stt] modelo principal sem resultado; a tentar {api_cfg['fallback_stt_model']}")
            text = unsloth_transcribe(wav_path, api_cfg["fallback_stt_model"])
        if not text and cfg.get("fallback_local_stt", False):
            text = whisper_transcribe(wav_path)
    elif engine == "deepgram":
        text = deepgram_transcribe(wav_path)
        if not text and cfg.get("fallback_local_stt", False):
            text = whisper_transcribe(wav_path)
    else:
        text = whisper_transcribe(wav_path)
        if not text and cfg.get("fallback_local_stt", False):
            text = unsloth_transcribe(wav_path)
    return text


async def handle_client(ws):
    cfg = load_config()
    token = load_token()
    peer = ws.remote_address
    device_id, user = "unknown", "unknown"
    authed = False
    print(f"[gateway] ligação de {peer}")

    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue

        mtype = msg.get("type")

        if mtype == "hello":
            device_id = str(msg.get("device_id", "unknown"))[:64]
            user = str(msg.get("user", device_id))[:64]
            candidate = msg.get("token")
            if not isinstance(candidate, str) or not secrets.compare_digest(candidate, token):
                log_to_obsidian(device_id, user, "TENTATIVA COM TOKEN INVÁLIDO", "SECURITY")
                await ws.send(json.dumps({"type": "auth", "ok": False, "reason": "token"}))
                continue
            in_list = device_id in cfg["allowlist"]
            pol = cfg["policies"].get(device_id, cfg["unknown"]) if in_list else cfg["unknown"]
            authed = in_list
            log_to_obsidian(device_id, user,
                            f"ligado (allowlist={in_list})", "session")
            await ws.send(json.dumps({"type": "auth", "ok": in_list, "policy": pol}))
            continue

        if mtype in ("models_list", "models_load"):
            request_id = str(msg.get("request_id", ""))[:64]
            host = str(msg.get("host", "pc"))[:16].lower()
            category = str(msg.get("category", "llm"))[:16].lower()
            if not authed:
                await ws.send(json.dumps({"type": "model_operation", "ok": False, "request_id": request_id,
                                          "host": host, "category": category, "message": "Autentica a app antes de gerir modelos."}))
                continue
            try:
                if mtype == "models_list":
                    catalog = await asyncio.to_thread(model_catalog, host, category)
                    await ws.send(json.dumps({"type": "models_catalog", "request_id": request_id,
                                              "host": host, "category": category, **catalog}, ensure_ascii=False))
                else:
                    model_id = str(msg.get("model", ""))[:300]
                    await ws.send(json.dumps({"type": "model_operation", "ok": None, "request_id": request_id,
                                              "host": host, "category": category, "model": model_id,
                                              "message": "A carregar o modelo…"}, ensure_ascii=False))
                    message = await asyncio.to_thread(load_model_for_app, host, category, model_id)
                    await ws.send(json.dumps({"type": "model_operation", "ok": True, "request_id": request_id,
                                              "host": host, "category": category, "model": model_id,
                                              "message": message}, ensure_ascii=False))
            except Exception as e:
                await ws.send(json.dumps({"type": "model_operation", "ok": False, "request_id": request_id,
                                          "host": host, "category": category,
                                          "message": str(e)[:400]}, ensure_ascii=False))
            continue

        if mtype == "audio" and msg.get("audio_b64"):
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            try:
                audio = decode_audio_payload(msg["audio_b64"])
            except ValueError:
                await ws.send(json.dumps({"type": "audio_error", "message": "Áudio inválido ou demasiado grande."}, ensure_ascii=False))
                continue
            wav_path = RECORDINGS / f"{ts}_{_recording_device_slug(device_id)}_{secrets.token_hex(4)}.wav"
            await asyncio.to_thread(wav_path.write_bytes, audio)

            pol = cfg["policies"].get(device_id, cfg["unknown"]) if authed else cfg["unknown"]
            text = ""
            if pol.get("transcribe"):
                # STT, LLM and TTS calls are synchronous and can take over a minute.
                # Keep them off the event loop so websocket ping/pong stays responsive.
                text = await asyncio.to_thread(transcribe, wav_path)
                if text:
                    await asyncio.to_thread(log_to_obsidian, device_id, user, text)
                    await ws.send(json.dumps({"type": "transcript", "text": text, "file": wav_path.name}))

            if pol.get("reply") and text:
                await asyncio.to_thread(send_to_drisa, text, user)
                reply = await asyncio.to_thread(llm_reply, text)
                if reply:
                    await asyncio.to_thread(log_to_obsidian, device_id, user, reply, "drisa")
                    await ws.send(json.dumps({"type": "reply", "text": reply}))
                    audio = await asyncio.to_thread(tts_kokoro, reply)
                    if audio:
                        await ws.send(json.dumps({
                            "type": "tts", "audio_b64": base64.b64encode(audio).decode(),
                            "format": "wav_24000"
                        }))
            elif not authed:
                log_to_obsidian(device_id, user,
                                f"áudio gravado {wav_path.name} (sem resposta — desconhecido)")
        # type "ping" → pong
        if mtype == "ping":
            await ws.send(json.dumps({"type": "pong"}))

    print(f"[gateway] {peer} desligou ({device_id})")


async def main():
    cfg = load_config()
    token = load_token()
    port = cfg.get("port", 8765)
    # Tailscale Serve forwards to loopback; keep the gateway off LAN interfaces.
    print(f"[gateway] Drisa Voice Gateway a ouvir em 127.0.0.1:{port}")
    print(f"[gateway] vault: {VAULT}")
    async with websockets.serve(
        handle_client,
        "127.0.0.1",
        port,
        max_size=MAX_WEBSOCKET_MESSAGE_BYTES,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
