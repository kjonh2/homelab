"""Encrypted PostgreSQL conversation memory and exact LFM context budgeting."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from cryptography.fernet import Fernet

logger = logging.getLogger("drisa.memory")
CONTEXT_TARGET = 0.30
CONTEXT_TRIGGER = 0.50
DEFAULT_CONVERSATION_ID = "kiko-main"


def _paths() -> tuple[Path, Path]:
    root = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa"))
    return root / "drisa_memory_config.json", root / "drisa_memory_fernet.key"


def _settings() -> tuple[dict[str, Any], Fernet]:
    config_path, key_path = _paths()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cipher = Fernet(key_path.read_bytes().strip())
    return config, cipher


def _connect(config):
    import psycopg
    return psycopg.connect(config["dsn"], connect_timeout=3, autocommit=False)


def _ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drisa_conversations (
          conversation_id TEXT PRIMARY KEY,
          summary_ciphertext BYTEA NOT NULL DEFAULT ''::bytea,
          summarized_through BIGINT NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drisa_messages (
          id BIGSERIAL PRIMARY KEY,
          conversation_id TEXT NOT NULL REFERENCES drisa_conversations(conversation_id),
          turn_id UUID NOT NULL,
          role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
          content_ciphertext BYTEA NOT NULL,
          token_count INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (conversation_id, turn_id, role)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS drisa_messages_recent ON drisa_messages(conversation_id, id DESC)")


def _api_headers(key):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _render_and_count(base_url, key, model, messages):
    headers = _api_headers(key)
    # OpenAI-compatible chat routes live below /v1, but llama.cpp's
    # tokenizer/template/context inspection routes are mounted at the server root.
    control_url = base_url[:-3] if base_url.endswith("/v1") else base_url
    rendered = requests.post(control_url + "/apply-template", json={"model": model, "messages": messages}, headers=headers, timeout=15)
    rendered.raise_for_status()
    prompt = rendered.json()["prompt"]
    tokenized = requests.post(control_url + "/tokenize", json={"model": model, "content": prompt, "add_special": True}, headers=headers, timeout=15)
    tokenized.raise_for_status()
    body = tokenized.json()
    token_count = len(body.get("tokens", []))
    props = requests.get(control_url + "/props", params={"model": model}, headers=headers, timeout=10)
    props.raise_for_status()
    props_body = props.json()
    context_size = int(props_body.get("n_ctx") or props_body.get("default_generation_settings", {}).get("n_ctx", 0))
    if not token_count or not context_size:
        raise ValueError("LFM não devolveu contagem de tokens ou limite de contexto")
    return token_count, context_size


def _summarize(messages, base_url, key, model, n_ctx):
    """Summarize old conversation in token-bounded chunks; preserve recent turns."""
    system = messages[0]
    summary = next((m["content"] for m in messages[1:] if m.get("name") == "drisa_memory_summary"), "")
    turns = [m for m in messages[1:-1] if m.get("name") != "drisa_memory_summary"]
    pending_user = messages[-1]
    keep = []
    # Preserve newest complete turns, aiming at 30% including the next user message and reply reserve.
    for i in range(len(turns) - 2, -1, -2):
        pair = turns[i:i + 2]
        # Count accumulated recent turns and the pending user message together.
        # Counting each pair separately can keep every turn and exceed the target.
        candidate = pair + keep
        trial = [system] + ([{"role": "system", "name": "drisa_memory_summary", "content": summary}] if summary else []) + candidate + [pending_user]
        try:
            count, _ = _render_and_count(base_url, key, model, trial)
        except Exception:
            break
        if count + 256 <= int(n_ctx * CONTEXT_TARGET):
            keep = candidate
        else:
            break
    old = turns[:len(turns) - len(keep)] if keep else turns
    if not old:
        return messages, summary, False, 0
    # Incremental chunks stay under half of the model context including summary instruction/output.
    compacted = summary
    chunks, chunk = [], []
    for message in old:
        candidate = chunk + [message]
        probe = [system, {"role": "system", "content": "Resume fielmente em português de Portugal. Preserva preferências duradouras, factos do projeto, decisões e pedidos pendentes. Exclui credenciais, chaves, códigos e detalhes transitórios. Máximo 250 tokens."}, *candidate]
        try:
            count, _ = _render_and_count(base_url, key, model, probe)
        except Exception:
            count = int(n_ctx)
        if chunk and count + 256 > int(n_ctx * CONTEXT_TRIGGER):
            chunks.append(chunk)
            chunk = [message]
        else:
            chunk = candidate
    if chunk:
        chunks.append(chunk)
    for part in chunks:
        prompt_messages = [system]
        if compacted:
            prompt_messages.append({"role": "system", "content": "Resumo anterior (atualiza sem perder factos duradouros): " + compacted})
        prompt_messages.append({"role": "system", "content": "Resume fielmente em português de Portugal. Preserva preferências duradouras, factos do projeto, decisões e pedidos pendentes. Exclui credenciais, chaves, códigos e detalhes transitórios. Máximo 250 tokens."})
        prompt_messages.extend(part)
        response = requests.post(base_url + "/chat/completions", json={"model": model, "messages": prompt_messages, "max_tokens": 280, "temperature": 0.2, "reasoning": {"effort": "none"}}, headers=_api_headers(key), timeout=90)
        response.raise_for_status()
        compacted = response.json()["choices"][0]["message"]["content"].strip()
    out = [system]
    if compacted:
        out.append({"role": "system", "name": "drisa_memory_summary", "content": compacted})
    out.extend(keep)
    out.append(pending_user)
    return out, compacted, True, len(old)


def _summary_cursor(rows, summarized_count: int, current_cursor: int) -> int:
    """Return the last persisted message included in the new summary."""
    if summarized_count < 0 or summarized_count > len(rows):
        raise ValueError("Resumo excede as mensagens persistidas")
    return rows[summarized_count - 1][0] if summarized_count else current_cursor


def chat(user_text: str, *, system_prompt: str, base_url: str, key: str, model: str,
         max_tokens: int, temperature: float, conversation_id: str = DEFAULT_CONVERSATION_ID,
         spoken_cleaner=lambda value: value) -> str | None:
    """Generate a reply with shared encrypted PG history. Returns None if PG is unavailable."""
    from uuid import uuid4
    try:
        config, cipher = _settings()
        conn = _connect(config)
    except Exception as exc:
        logger.warning("PostgreSQL conversation memory unavailable (%s)", type(exc).__name__)
        return None
    try:
        _ensure_schema(conn)
        conn.execute("INSERT INTO drisa_conversations(conversation_id) VALUES (%s) ON CONFLICT DO NOTHING", (conversation_id,))
        # Serialize both laptop and Android turns for this shared conversation.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (conversation_id,))
        row = conn.execute("SELECT summary_ciphertext, summarized_through FROM drisa_conversations WHERE conversation_id=%s", (conversation_id,)).fetchone()
        summarized_through = row[1] if row else 0
        summary = cipher.decrypt(bytes(row[0])).decode("utf-8") if row and row[0] else ""
        rows = conn.execute("SELECT id, role, content_ciphertext FROM drisa_messages WHERE conversation_id=%s AND id>%s ORDER BY id", (conversation_id, row[1] if row else 0)).fetchall()
        history = [{"role": "system", "content": system_prompt}]
        if summary:
            history.append({"role": "system", "name": "drisa_memory_summary", "content": summary})
        history.extend({"role": role, "content": cipher.decrypt(bytes(content)).decode("utf-8")} for _, role, content in rows)
        messages = history + [{"role": "user", "content": user_text}]
        n_ctx = 4096
        try:
            tokens, n_ctx = _render_and_count(base_url, key, model, messages)
            if tokens + max_tokens >= n_ctx * CONTEXT_TRIGGER:
                messages, summary, changed, summarized_count = _summarize(messages, base_url, key, model, n_ctx)
                tokens, _ = _render_and_count(base_url, key, model, messages)
                logger.info("context compacted: %s/%s tokens (%.1f%%)", tokens + max_tokens, n_ctx, 100 * (tokens + max_tokens) / n_ctx)
                if changed:
                    # Only advance across the archived prefix included in the summary.
                    # Newer complete turns retained in the prompt must be loaded again
                    # on the next request instead of silently disappearing from context.
                    last_id = _summary_cursor(rows, summarized_count, summarized_through)
                    conn.execute("UPDATE drisa_conversations SET summary_ciphertext=%s, summarized_through=%s, updated_at=now() WHERE conversation_id=%s", (cipher.encrypt(summary.encode()), last_id, conversation_id))
        except Exception as exc:
            # With a live DB, fail closed on inability to measure: never send unbounded history.
            logger.warning("context measurement/compaction failed (%s); using current short history", type(exc).__name__)
            messages = [history[0], *history[-4:], {"role": "user", "content": user_text}]
        logger.info("context usage before generation: %s/%s tokens including %s completion reserve", tokens if 'tokens' in locals() else -1, n_ctx, max_tokens)
        response = requests.post(base_url + "/chat/completions", json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}, headers=_api_headers(key), timeout=90)
        response.raise_for_status()
        reply = spoken_cleaner(response.json()["choices"][0]["message"]["content"])
        if reply:
            turn_id = uuid4()
            conn.execute("INSERT INTO drisa_messages(conversation_id,turn_id,role,content_ciphertext,token_count) VALUES (%s,%s,'user',%s,%s),(%s,%s,'assistant',%s,%s)", (
                conversation_id, turn_id, cipher.encrypt(user_text.encode()), 0,
                conversation_id, turn_id, cipher.encrypt(reply.encode()), 0,
            ))
        conn.commit()
        return reply
    except Exception as exc:
        conn.rollback()
        logger.warning("PostgreSQL conversation memory unavailable (%s)", type(exc).__name__)
        return None
    finally:
        conn.close()

