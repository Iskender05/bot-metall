import os
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.llm_client import llm
from agent.mir_metalla_system_prompt import SYSTEM_PROMPT
from db.bot.models import Message


HISTORY_LIMIT = int(os.getenv("DIALOG_HISTORY_LIMIT", "30"))
MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "700"))


def _clean_reply(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text or "")
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__|\*|_|~~)", "", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", " ", text)
    text = text.strip()

    if len(text) <= MAX_REPLY_CHARS:
        return text

    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    shortened = " ".join(sentences[:2]).strip()
    return shortened[:MAX_REPLY_CHARS].strip()


def _message_history(messages: list[Message]) -> list:
    history = []
    ordered = list(reversed(messages[-HISTORY_LIMIT:]))

    for message in ordered:
        if message.type == "manager_message":
            text = (message.assistant_message or "").strip()
            if text:
                history.append(SystemMessage(content=f"Менеджер написал клиенту: {text}"))
            continue

        user_text = (message.user_message or "").strip()
        assistant_text = (message.assistant_message or "").strip()

        if user_text:
            history.append(HumanMessage(content=user_text))
        if assistant_text:
            history.append(AIMessage(content=assistant_text))

    return history


async def generate_reply(messages: list[Message]) -> str:
    prompt_messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *_message_history(messages),
    ]
    response = await llm.ainvoke(prompt_messages)
    return _clean_reply(str(response.content or ""))


def looks_like_lead_finished(answer: str) -> bool:
    normalized = (answer or "").casefold()
    return (
        "передам менеджеру" in normalized
        or "менеджер свяжется" in normalized
        or "свяжется в удобное" in normalized
    )
