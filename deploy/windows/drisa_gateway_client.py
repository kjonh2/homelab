"""Private synchronous client for sending desktop turns through the Drisa gateway."""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from websockets.sync.client import connect


def _submit_turn(message: dict, *, timeout: float = 300) -> bytes:
    root = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa")).expanduser()
    token = (root / "gateway_token.txt").read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Token local da gateway Drisa vazio.")
    url = os.environ.get("DRISA_GATEWAY_LOCAL_URL", "ws://127.0.0.1:8765/")
    device_id = os.environ.get("DRISA_GATEWAY_DEVICE_ID", "kiko-pc")
    deadline = time.monotonic() + timeout
    with connect(url, open_timeout=8, close_timeout=3, max_size=8 * 1024 * 1024) as ws:
        ws.send(json.dumps({"type": "hello", "device_id": device_id, "user": "Kiko", "token": token}))
        auth = json.loads(ws.recv(timeout=10))
        if auth.get("type") != "auth" or not auth.get("ok"):
            raise RuntimeError("A gateway Drisa não autorizou o cliente local.")
        ws.send(json.dumps(message, ensure_ascii=False))
        while time.monotonic() < deadline:
            response = json.loads(ws.recv(timeout=max(1, deadline - time.monotonic())))
            if response.get("type") == "audio_error":
                raise RuntimeError(str(response.get("message") or "Falha na resposta da Drisa."))
            if response.get("type") == "tts":
                encoded = response.get("audio_b64")
                if not encoded:
                    raise RuntimeError("A gateway devolveu áudio vazio.")
                return base64.b64decode(encoded, validate=True)
    raise TimeoutError("A resposta da Drisa excedeu o tempo limite.")


def submit_text_turn(text: str, *, timeout: float = 300) -> bytes:
    """Submit desktop-transcribed speech for the shared memory-backed LLM turn."""
    return _submit_turn({"type": "text", "text": text}, timeout=timeout)


def publish_completed_turn(transcript: str, reply: str, *, timeout: float = 180) -> bytes:
    """Publish an already memory-backed desktop answer and receive its shared TTS."""
    return _submit_turn({"type": "publish", "text": transcript, "reply": reply}, timeout=timeout)
