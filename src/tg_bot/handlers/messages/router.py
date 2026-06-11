import logging

from aiogram import Router, types
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from avito.message_handler import handle_message
from db.bot.queries import clear_user_agent_data, get_or_create_user, get_user


router = Router()
router.message.filter(lambda message: message.chat.type == ChatType.PRIVATE)

logger = logging.getLogger(__name__)


class UserStates(StatesGroup):
    waiting_for_ai_response = State()


@router.message(Command("clear_dialog"))
async def cmd_clear_dialog(message: types.Message, state: FSMContext) -> None:
    chat_id = str(message.chat.id)
    username = message.from_user.username or ""
    await clear_user_agent_data(chat_id, username[:100] if username else None)
    await state.clear()
    await message.answer("Диалог очищен. Можно начать заново.")


@router.message(lambda message: not message.text or not message.text.startswith("/"))
async def handle_user_message(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_message_id = data.get("user_message_id")

    if user_message_id is None:
        await message.answer("Пожалуйста, ожидайте ответа...")
    else:
        try:
            await message.answer(
                "Пожалуйста, дождитесь ответа на данный вопрос...",
                reply_to_message_id=user_message_id,
            )
        except TelegramBadRequest:
            await message.answer("Пожалуйста, ожидайте ответа...")

    if await state.get_state() == UserStates.waiting_for_ai_response.state:
        return

    await state.set_state(UserStates.waiting_for_ai_response)
    await state.update_data(user_message_id=message.message_id)

    try:
        if not message.text:
            await message.answer("Пока могу обработать только текстовое сообщение.")
            return

        chat_id = str(message.chat.id)
        user = await get_user(chat_id)
        if user is None:
            username = message.from_user.username or ""
            user = await get_or_create_user(chat_id, username[:100] if username else "")

        is_lead, answer, _ = await handle_message({
            "chat_id": chat_id,
            "name": message.from_user.username,
            "last_message": {
                "type": "text",
                "content": message.text,
            },
        })

        if answer:
            await message.answer(answer, reply_to_message_id=user_message_id)
        elif (not user.answers_from_agent) or user.final_stage:
            logger.info(
                "Skip Telegram answer for chat %s: answers_from_agent=%s final_stage=%s",
                chat_id,
                user.answers_from_agent,
                user.final_stage,
            )

        if is_lead:
            logger.info("Lead-like Telegram dialog completed for chat %s", chat_id)

    except Exception as err:
        logger.exception("Ошибка обработки сообщения: %s", err)
        await message.answer("Произошла ошибка при обработке запроса")
    finally:
        await state.clear()
