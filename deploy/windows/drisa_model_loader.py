"""Shared on-demand loader for the private VPS LFM3 API."""

import time


VPS_MODELS_URL = "https://vps-4e5174e4.tail2931da.ts.net:8445/models"


def _loaded_model_ids(payload: dict) -> set[str]:
    entries = payload.get("data", payload.get("models", []))
    if not isinstance(entries, list):
        raise RuntimeError("A VPS não devolveu um catálogo válido de modelos.")
    loaded = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("model") or item.get("name")
        status = item.get("status", item.get("state", ""))
        if isinstance(status, dict):
            status = status.get("value", status.get("state", ""))
        if model_id and (item.get("loaded") is True or str(status).lower() == "loaded"):
            loaded.add(str(model_id))
    return loaded


def ensure_vps_llm_model_loaded(model_id: str, key: str, *, models_url: str = VPS_MODELS_URL,
                                timeout: int = 240, poll_interval: float = 2.0) -> None:
    """Load and verify the requested VPS model before sending chat traffic."""
    import requests

    model_id = str(model_id or "").strip()
    key = str(key or "").strip()
    if not model_id:
        raise ValueError("O modelo LLM da VPS não foi selecionado.")
    if not key:
        raise RuntimeError("A chave privada da API LFM3 da VPS não está configurada.")

    headers = {"Authorization": f"Bearer {key}"}

    def loaded() -> bool:
        response = requests.get(models_url, headers=headers, timeout=(5, 15))
        response.raise_for_status()
        return model_id in _loaded_model_ids(response.json())

    if loaded():
        return

    response = requests.post(models_url + "/load", json={"model": model_id},
                             headers=headers, timeout=(5, 260))
    response.raise_for_status()
    result = response.json()
    if result.get("success") is False or result.get("error"):
        raise RuntimeError("A VPS recusou o carregamento do modelo LLM.")

    deadline = time.monotonic() + timeout
    while True:
        if loaded():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"O modelo LLM {model_id} não ficou pronto na VPS dentro do prazo.")
        time.sleep(min(poll_interval, remaining))
