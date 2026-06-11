import asyncio
import logging
import multiprocessing
import os

from avito.bot import start_avito_bot


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)


def run_bot_process():
    """Запускает бота в отдельном процессе"""
    from tg_bot.main import start_bot
    asyncio.run(start_bot())


async def main():
    """Основной цикл работы программы"""
    tg_enabled = os.getenv("TG_BOT_TOKEN") and os.getenv("ENABLE_TG_BOT", "False") == "True"
    if tg_enabled:
        logger.info("Запуск приложения: Telegram в отдельном процессе, Avito в основном")
        bot_process = multiprocessing.Process(target=run_bot_process, daemon=True)
        bot_process.start()
        logger.info("Telegram-процесс запущен (pid=%s)", bot_process.pid)
    else:
        logger.info("Запуск приложения: Avito-only режим, Telegram отключён")

    await start_avito_bot()


if __name__ == '__main__':
    # Важно для multiprocessing
    multiprocessing.set_start_method('spawn')
    asyncio.run(main())
