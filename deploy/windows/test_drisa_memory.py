import unittest
from unittest.mock import Mock, patch

import drisa_memory


class DrisaMemorySummaryTests(unittest.TestCase):
    @patch.object(drisa_memory.requests, "get")
    @patch.object(drisa_memory.requests, "post")
    def test_unsloth_template_fallback_counts_exact_model_tokens(self, post, get):
        apply_template = Mock()
        apply_template.raise_for_status.side_effect = drisa_memory.requests.HTTPError(
            response=Mock(status_code=404)
        )
        tokenized = Mock()
        tokenized.json.return_value = {"tokens": [1, 2, 3, 4]}
        post.side_effect = [apply_template, tokenized]
        props = Mock()
        props.json.return_value = {
            "chat_template": (
                "{% for message in messages %}<|{{ message['role'] }}|>"
                "{% generation %}{{ message['content'] }}{% endgeneration %}"
                "{% endfor %}{% if add_generation_prompt %}<|assistant|>{% endif %}"
            ),
            "default_generation_settings": {"n_ctx": 4096},
        }
        get.return_value = props
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Olá"},
        ]

        tokens, context = drisa_memory._render_and_count(
            "http://pc/v1", "local-key", "lfm3", messages
        )

        self.assertEqual((tokens, context), (4, 4096))
        get.assert_called_once_with(
            "http://pc/props", params={"model": "lfm3"},
            headers={"Content-Type": "application/json", "Authorization": "Bearer local-key"},
            timeout=10,
        )
        token_request = post.call_args_list[1]
        self.assertFalse(token_request.kwargs["json"]["add_special"])
        self.assertEqual(
            token_request.kwargs["json"]["content"],
            "<|system|>system<|user|>Olá<|assistant|>",
        )

    def test_summary_cursor_stops_before_turns_kept_in_context(self):
        archived_rows = [(11, "user"), (12, "assistant"), (13, "user"), (14, "assistant")]

        cursor = drisa_memory._summary_cursor(archived_rows, 2, current_cursor=10)

        self.assertEqual(cursor, 12)
        self.assertGreater(archived_rows[2][0], cursor)

    def test_summary_cursor_preserves_existing_cursor_when_nothing_new_was_summarized(self):
        self.assertEqual(drisa_memory._summary_cursor([], 0, current_cursor=23), 23)

    def test_summary_cursor_rejects_a_count_outside_the_archived_rows(self):
        with self.assertRaises(ValueError):
            drisa_memory._summary_cursor([(1, "user")], 2, current_cursor=0)

    @patch.object(drisa_memory, "_render_and_count")
    @patch.object(drisa_memory.requests, "post")
    def test_summarize_reports_only_archived_messages_in_summary(self, post, render):
        def token_count(_url, _key, _model, messages):
            # Count the accumulated recent turns, system prompt, and pending
            # user message so only the newest complete turn fits the 30% target.
            return (20 * max(0, len(messages) - 2), 1000)

        render.side_effect = token_count
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Resumo antigo"}}]}
        post.return_value = response
        messages = [{"role": "system", "content": "system"}]
        for turn in range(4):
            messages.extend([
                {"role": "user", "content": f"pergunta {turn}"},
                {"role": "assistant", "content": f"resposta {turn}"},
            ])
        messages.append({"role": "user", "content": "pergunta atual"})

        compacted, summary, changed, summarized_count = drisa_memory._summarize(
            messages, "http://llm/v1", "", "model", 1000, request_timeout=17
        )

        self.assertTrue(changed)
        self.assertEqual(summary, "Resumo antigo")
        self.assertEqual(summarized_count, 6)
        self.assertEqual(compacted[-3:-1], messages[-3:-1])
        self.assertEqual(compacted[-1], messages[-1])
        self.assertEqual(post.call_args.kwargs["timeout"], 17)

    @patch.object(drisa_memory, "_ensure_schema")
    @patch.object(drisa_memory, "_render_and_count", return_value=(10, 4096))
    @patch.object(drisa_memory, "_connect")
    @patch.object(drisa_memory, "_settings", return_value=({}, Mock()))
    @patch.object(drisa_memory.requests, "post", side_effect=drisa_memory.requests.Timeout)
    def test_llm_timeout_propagates_for_host_fallback(self, post, _settings, connect, _render, _schema):
        conn = Mock()
        def execute(query, *_args):
            cursor = Mock()
            if "SELECT summary_ciphertext" in query:
                cursor.fetchone.return_value = (b"", 0)
            elif "SELECT id, role" in query:
                cursor.fetchall.return_value = []
            return cursor
        conn.execute.side_effect = execute
        connect.return_value = conn

        with self.assertRaises(drisa_memory.requests.Timeout):
            drisa_memory.chat(
                "Olá", system_prompt="sistema", base_url="http://vps/v1", key="", model="lfm",
                max_tokens=64, temperature=0.2, request_timeout=45,
            )

        self.assertEqual(post.call_args.kwargs["timeout"], 45)
        self.assertIs(post.call_args.kwargs["json"]["enable_thinking"], False)
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    @patch.object(drisa_memory, "_ensure_schema")
    @patch.object(
        drisa_memory,
        "_render_and_count",
        side_effect=drisa_memory.requests.HTTPError(response=Mock(status_code=404)),
    )
    @patch.object(drisa_memory, "_connect")
    @patch.object(drisa_memory, "_settings", return_value=({}, Mock()))
    @patch.object(drisa_memory.requests, "post")
    def test_missing_context_inspection_route_uses_saved_summary_without_unmeasured_turns(self, post, _settings, connect, _render, _schema):
        conn = Mock()
        cipher = Mock()
        cipher.decrypt.side_effect = lambda value: {
            b"summary-cipher": "Preferência guardada.".encode(),
            b"user-cipher": "Pedido antigo.".encode(),
            b"assistant-cipher": "Resposta antiga.".encode(),
        }[value]
        _settings.return_value = ({}, cipher)
        def execute(query, *_args):
            cursor = Mock()
            if "SELECT summary_ciphertext" in query:
                cursor.fetchone.return_value = (b"summary-cipher", 0)
            elif "SELECT id, role" in query:
                cursor.fetchall.return_value = [
                    (1, "user", b"user-cipher"),
                    (2, "assistant", b"assistant-cipher"),
                ]
            return cursor
        conn.execute.side_effect = execute
        connect.return_value = conn
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Resposta local."}}]}
        post.return_value = response

        reply = drisa_memory.chat(
            "Olá", system_prompt="sistema", base_url="http://pc/v1", key="", model="lfm",
            max_tokens=64, temperature=0.2, request_timeout=90,
        )

        self.assertEqual(reply, "Resposta local.")
        self.assertEqual(post.call_args.kwargs["json"]["messages"], [
            {"role": "system", "content": "sistema"},
            {"role": "system", "name": "drisa_memory_summary", "content": "Preferência guardada."},
            {"role": "user", "content": "Olá"},
        ])
        self.assertIs(post.call_args.kwargs["json"]["enable_thinking"], False)


if __name__ == "__main__":
    unittest.main()
