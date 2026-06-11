from aiogram import Bot
from aiogram.enums.parse_mode import ParseMode
import logging

from tg_bot.config import ADMIN_IDS, ADMIN_GROUPS_IDS


logger = logging.getLogger(__name__)


async def send_to_all_admins(bot: Bot, text: str, to_groups: bool = False) -> None:
    """Отправка сообщения администраторам или в группы/топики"""

    if not to_groups:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error(f"Ошибка при отправке админу {admin_id}: {e}")
        return

    for chat_id, thread_id in ADMIN_GROUPS_IDS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=thread_id,
            )
        except Exception as e:
            logger.error(
                f"Ошибка при отправке в чат {chat_id}"
                + (f" (topic {thread_id})" if thread_id else "")
                + f": {e}"
            )

