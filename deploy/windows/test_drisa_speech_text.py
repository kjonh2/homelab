import unittest

from drisa_speech_text import is_utterance_echo, prepare_spoken_text


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

    def test_detects_substantive_echo_even_with_different_punctuation(self):
        self.assertTrue(
            is_utterance_echo(
                "Qual é o estado dos meus serviços agora?",
                "Qual é o estado dos meus serviços agora.",
            )
        )

    def test_keeps_short_acknowledgements_and_real_answers(self):
        self.assertFalse(is_utterance_echo("Sim", "Sim"))
        self.assertFalse(
            is_utterance_echo("Qual é o estado dos meus serviços?", "Estão todos ligados.")
        )


if __name__ == "__main__":
    unittest.main()
