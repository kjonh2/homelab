---
name: drisa-context-management
description: Manage Drisa's persistent conversation memory and real LFM context budget. Use when recalling prior conversation, preparing an LFM prompt, checking context usage, or compacting conversation history.
---

# Drisa context and memory

- The shared conversation ID is `kiko-main`; laptop and Iku Android must use the same conversation.
- PostgreSQL is the persistence source. Read and write it through `drisa_memory.py`; never bypass its Fernet encryption or print the DSN/key.
- Persist transcript and spoken reply text only. Do not persist audio, passwords, tokens, private keys, recovery codes, or raw authorization headers.
- For the active LFM host/model, get `n_ctx` from `/props?model=<model>`, render the exact messages with `/apply-template`, and count the rendered prompt with `/tokenize`. Include the reserved completion budget in all percentages. Never estimate the tokenizer from characters or assume a fixed context size.
- At 50% of `n_ctx`, compact older turns. Preserve the newest complete turns, merge older history into a short Portuguese summary, and aim for about 30% total usage after compaction. Keep the full encrypted archive in PostgreSQL. Do not pad a new conversation just to reach 20%; 20–50% is a working range, not a target for an empty prompt.
- Summary content should retain durable preferences, project facts, decisions, and pending requests. Remove credentials and stale transient details. Keep the summary concise and factual.
- If PostgreSQL or the tokenizer is unavailable, keep the spoken interaction working with a short one-shot prompt; never send unbounded history. Log error types and token counts only, never conversation text.
- Keep LFM generation on the selected LLM endpoint. Send only the cleaned final spoken answer to Kokoro.
