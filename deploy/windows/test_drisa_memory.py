import unittest
from unittest.mock import Mock, patch

import drisa_memory


class DrisaMemorySummaryTests(unittest.TestCase):
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
            messages, "http://llm/v1", "", "model", 1000
        )

        self.assertTrue(changed)
        self.assertEqual(summary, "Resumo antigo")
        self.assertEqual(summarized_count, 6)
        self.assertEqual(compacted[-3:-1], messages[-3:-1])
        self.assertEqual(compacted[-1], messages[-1])


if __name__ == "__main__":
    unittest.main()
