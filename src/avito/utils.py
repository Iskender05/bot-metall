import re
from typing import Any, Iterable


def normalize_text(text: str) -> str:
    text = (text or "").strip()
    return re.sub(r"\s+", " ", text)


def extract_out_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        for key in ("message", "caption", "body"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return ""


def unsaved_outgoing_messages(
    outgoing_messages: list[dict],
    saved_outgoing_texts: Iterable[str],
) -> list[str]:
    saved = {
        normalize_text(text)
        for text in saved_outgoing_texts
        if isinstance(text, str) and normalize_text(text)
    }
    result: list[str] = []

    for message in outgoing_messages or []:
        message_type = message.get("type")
        if message_type != "text":
            result.append(f"Исходящее сообщение менеджера: {message_type or 'unknown'}")
            continue

        text = normalize_text(extract_out_text(message.get("value")))
        if text and text not in saved:
            saved.add(text)
            result.append(text)

    return result
