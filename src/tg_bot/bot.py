from aiogram import Bot

from .config import TG_BOT_TOKEN


bot: Bot | None = None

def get_bot() -> Bot:
    global bot
    if bot is None:
        if not TG_BOT_TOKEN:
            raise RuntimeError("TG_BOT_TOKEN не задан")
        bot = Bot(token=TG_BOT_TOKEN)
    return bot
