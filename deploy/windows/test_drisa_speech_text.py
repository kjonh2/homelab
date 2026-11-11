import unittest

from drisa_speech_text import prepare_spoken_text


class PrepareSpokenTextTests(unittest.TestCase):
    def test_removes_thinking_before_final_answer(self):
        self.assertEqual(
            prepare_spoken_text("<think>raciocínio privado</think> Final: Olá, Kiko."),
            "Olá, Kiko.",
        )

    def test_removes_unclosed_reasoning_block(self):
        self.assertEqual(
            prepare_spoken_text("Resposta. <analysis>texto interno sem fecho"),
            "Resposta.",
        )

    def test_formats_markdown_for_speech(self):
        self.assertEqual(
            prepare_spoken_text("**Olá** [Kiko](https://example.com)!"),
            "Olá Kiko!",
        )


if __name__ == "__main__":
    unittest.main()
