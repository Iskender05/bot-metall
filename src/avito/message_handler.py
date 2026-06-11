import asyncio
import logging
import os
import random
from typing import Any

from agent.dialog_agent import generate_reply, looks_like_lead_finished
from db.bot.queries import (
    attach_bot_answer,
    create_client_message,
    get_last_messages,
    get_user,
)


logger = logging.getLogger(__name__)

LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_BACKOFF_BASE_SECONDS = float(os.getenv("LLM_BACKOFF_BASE_SECONDS", "2"))
LLM_BACKOFF_MAX_SECONDS = float(os.getenv("LLM_BACKOFF_MAX_SECONDS", "30"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
DIALOG_HISTORY_LIMIT = int(os.getenv("DIALOG_HISTORY_LIMIT", "30"))


async def _generate_with_retries(chat_id: str, history) -> str:
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(
                generate_reply(history),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except Exception as err:
            if attempt >= LLM_MAX_RETRIES:
                raise
            delay = min(
                LLM_BACKOFF_BASE_SECONDS * (2 ** attempt),
                LLM_BACKOFF_MAX_SECONDS,
            )
            delay += random.uniform(0, 1)
            logger.warning(
                "Ошибка LLM для chat_id=%s: %s. Повтор через %.1f сек",
                chat_id,
                err,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("Не удалось получить ответ LLM")


async def handle_message(
    message: dict[str, Any],
    agent_type: Any = None,
    sticky_message: str | None = None,
) -> tuple[bool, str | None, bool]:
    chat_id = message["chat_id"]
    message_type = message["last_message"]["type"]
    text = (message["last_message"].get("content") or "").strip()

    if message_type != "text" or not text:
        return False, None, False

    user = await get_user(chat_id)
    if user is None:
        logger.warning("User not found in DB for chat_id=%s. Skipping.", chat_id)
        return False, None, False

    message_id = await create_client_message(chat_id, text)

    if (not user.answers_from_agent) or user.final_stage:
        logger.info(
            "Saved incoming text and skipped answer for chat_id=%s: "
            "answers_from_agent=%s final_stage=%s",
            chat_id,
            user.answers_from_agent,
            user.final_stage,
        )
        return False, None, False

    history = await get_last_messages(chat_id, limit=DIALOG_HISTORY_LIMIT)
    answer = await _generate_with_retries(chat_id, history)
    if not answer:
        logger.warning("LLM returned empty answer for chat_id=%s", chat_id)
        return False, None, False

    is_lead = looks_like_lead_finished(answer)
    await attach_bot_answer(
        message_id,
        answer,
        "final_message" if is_lead else "bot_response",
    )

    return is_lead, answer, False
