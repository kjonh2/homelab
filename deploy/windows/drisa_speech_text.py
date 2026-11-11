import html
import re


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
