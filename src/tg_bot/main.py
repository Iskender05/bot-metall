from aiogram import Dispatcher, types
from aiogram.filters import CommandStart
import asyncio
import logging

from .bot import get_bot
from .config import ADMIN_IDS
from .handlers.admin.commands import (
    commands_list as admin_commands, router as admin_router
)
from .handlers.messages.router import router as message_router

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = get_bot()
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    base_cmds = [
        types.BotCommand(command="clear_dialog", description="Сброс диалога"),
    ]
    user_cmds = list(base_cmds)
    if message.from_user.id in ADMIN_IDS:
        admin_with_agent = [*base_cmds, *admin_commands]
        await bot.set_my_commands(
            commands=admin_with_agent,
            scope=types.BotCommandScopeChat(chat_id=message.from_user.id),
        )
    else:
        await bot.set_my_commands(
            commands=user_cmds,
            scope=types.BotCommandScopeChat(chat_id=message.from_user.id),
        )

    await message.answer("Мир металла, здравствуйте! Напишите сообщение для проверки ассистента.")


dp.include_router(admin_router)
dp.include_router(message_router)


async def start_bot():
    """Запуск бота"""
    await dp.start_polling(bot, polling_timeout=500)


if __name__ == '__main__':
    asyncio.run(start_bot())
