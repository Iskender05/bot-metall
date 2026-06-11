import asyncio
import logging
import os
import random

from avito import methods
from avito.formatting import format_qualified_lead
from avito.message_handler import handle_message
from avito.utils import unsaved_outgoing_messages
from db.bot.queries import (
    create_client_message,
    create_manager_message,
    get_or_create_user,
    get_last_messages,
    get_saved_outgoing_texts,
    get_user,
    set_answers_from_agent_false,
    update_user_data,
)
from avito.config import DEBUG, BOT_ID, ITEM_IDS, BLOCKED_USERS, ALLOWED_CHAT_IDS


logger = logging.getLogger(__name__)
AVITO_LOOP_INTERVAL_SECONDS = float(os.getenv("AVITO_LOOP_INTERVAL_SECONDS", "2"))
AVITO_CHAT_INTERVAL_SECONDS = float(os.getenv("AVITO_CHAT_INTERVAL_SECONDS", "0.7"))
AVITO_LOOP_ERROR_BACKOFF_SECONDS = float(os.getenv("AVITO_LOOP_ERROR_BACKOFF_SECONDS", "10"))
AVITO_LOOP_ERROR_BACKOFF_MAX_SECONDS = float(os.getenv("AVITO_LOOP_ERROR_BACKOFF_MAX_SECONDS", "120"))


async def create_lead(chat_id: str):
    try:
        await update_user_data(chat_id, {'final_stage': True, 'answers_from_agent': False})
        u = await get_user(chat_id)
        if u is None:
            logger.warning("Lead skipped: user not found for chat_id=%s", chat_id)
            return
        msgs = await get_last_messages(chat_id, None)

        if not os.getenv("TG_BOT_TOKEN"):
            logger.info("Lead saved for chat_id=%s. Telegram notification skipped.", chat_id)
            return

        from tg_bot.bot import get_bot
        from tg_bot.handlers.admin.utils import send_to_all_admins

        tg_bot = get_bot()
        await send_to_all_admins(
            tg_bot,
            format_qualified_lead(u, msgs[::-1]),
            to_groups=not DEBUG
        )
    except Exception as err:
        logger.exception(
            'Ошибка во время отправки заявки от нового пользователя с id %s: %s',
            chat_id, err
        )


async def _process_chat(chat: dict) -> None:
    if (
        chat['chat_id'] in BLOCKED_USERS
        or chat['last_message']['type'] == 'system'
    ):
        return

    chat_id = chat["chat_id"]
    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS:
        logger.debug("Skip chat %s: not in AVITO_ALLOWED_CHAT_IDS", chat_id)
        return

    item_id = chat.get('item_id')
    try:
        item_id_int = int(item_id) if item_id is not None else None
    except (TypeError, ValueError):
        item_id_int = None
    if ITEM_IDS and item_id_int not in ITEM_IDS:
        return

    name = chat["name"]

    user = await get_user(chat_id)
    if user is None:
        user = await get_or_create_user(chat_id, name)

    messages = await methods.fetch_chat_messages_v3(BOT_ID, chat_id)

    messages_out = methods.extract_my_outgoing_messages(messages)
    saved_outgoing = await get_saved_outgoing_texts(chat_id)
    manager_messages = unsaved_outgoing_messages(messages_out, saved_outgoing)
    if manager_messages:
        for manager_text in reversed(manager_messages):
            await create_manager_message(chat_id, manager_text)
        updated = await set_answers_from_agent_false(chat_id)
        if updated:
            logger.info("answers_from_agent -> False for chat %s", chat_id)
        return

    new_pack = methods.extract_new_user_text_until_last_my_reply(messages)
    if new_pack['has_non_text']:
        await create_client_message(chat_id, "Клиент отправил вложение или не текстовое сообщение")
        await create_lead(chat_id)
        return

    text = (new_pack['text'] or '').strip()
    if not text:
        logger.info("Skip chat %s: empty incoming text pack", chat_id)
        return

    message = {
        'chat_id': chat_id,
        'last_message': {'type': 'text', 'content': text}
    }

    is_lead, answer, disable_agent = await handle_message(message)
    if answer:
        await methods.send_message(BOT_ID, chat_id, answer)
    if disable_agent:
        updated = await set_answers_from_agent_false(chat_id)
        if updated:
            logger.info(f"answers_from_agent -> False for chat {chat_id}")
        return
    if is_lead:
        await create_lead(chat_id)


async def start_avito_bot():
    logger.info(
        "Avito polling запущен: DEBUG=%s interval=%.1fs chat_interval=%.1fs",
        DEBUG,
        AVITO_LOOP_INTERVAL_SECONDS,
        AVITO_CHAT_INTERVAL_SECONDS,
    )
    if DEBUG:
        logger.warning(
            "DEBUG=True: Avito polling отключен, работает только Telegram. "
            "Установите DEBUG=False в .env для Avito."
        )

    loop_error_backoff = AVITO_LOOP_ERROR_BACKOFF_SECONDS
    while True:
        await asyncio.sleep(AVITO_LOOP_INTERVAL_SECONDS)
        if DEBUG:
            continue

        try:
            chats = await methods.get_chats(
                user_id=BOT_ID,
                item_ids=ITEM_IDS,
                unread_only=True
            )
            parsed_chats = methods.parse_chats_summary(chats)
            processed_count = 0

            logger.info(
                "Avito polling итерация: unread_chats=%s parsed_chats=%s",
                len((chats or {}).get("chats", []) or []),
                len(parsed_chats),
            )

            for chat in parsed_chats:
                chat_id = chat.get("chat_id")

                try:
                    await _process_chat(chat)
                    processed_count += 1
                except Exception as err:
                    logger.exception(
                        "Ошибка обработки Avito-чата %s: %s",
                        chat_id,
                        err,
                    )
                if AVITO_CHAT_INTERVAL_SECONDS > 0:
                    await asyncio.sleep(AVITO_CHAT_INTERVAL_SECONDS)

            logger.info(
                "Avito polling итерация завершена: processed=%s",
                processed_count,
            )

            loop_error_backoff = AVITO_LOOP_ERROR_BACKOFF_SECONDS
        except Exception as err:
            delay = min(loop_error_backoff, AVITO_LOOP_ERROR_BACKOFF_MAX_SECONDS)
            delay += random.uniform(0, 1)
            logger.exception(
                "Ошибка итерации Avito polling: %s. Следующая попытка через %.1f сек",
                err,
                delay,
            )
            await asyncio.sleep(delay)
            loop_error_backoff = min(
                loop_error_backoff * 2,
                AVITO_LOOP_ERROR_BACKOFF_MAX_SECONDS,
            )
                

if __name__ == '__main__':
    asyncio.run(start_avito_bot())
