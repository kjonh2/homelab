import html
import re
import unicodedata


def prepare_spoken_text(value: str) -> str:
    """Keep only the final answer and normalize it for display and speech synthesis."""
    text = html.unescape(value or "")
    text = re.sub(r"```[^\n]*\n.*?```", " ", text, flags=re.DOTALL)
    for tag in ("think", "analysis", "reasoning"):
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}\s*>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(rf"<{tag}\b[^>]*>.*$", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(rf"</{tag}\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<\|[^>]+\|>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*(?:final answer|final|answer)\s*[:：-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^\s*(?:[-*#>]+)\s*", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[`*_~#]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_utterance_echo(utterance: str, response: str) -> bool:
    """Detect a model reply that only repeats a substantive user utterance."""

    def normalized_words(value: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", value or "").casefold()
        return re.findall(r"\w+", normalized)

    spoken_words = normalized_words(utterance)
    reply_words = normalized_words(response)
    if not spoken_words or spoken_words != reply_words:
        return False

    # Keep legitimate short acknowledgements such as "sim" or "olá" usable.
    return len(spoken_words) >= 4 or sum(map(len, spoken_words)) >= 24
