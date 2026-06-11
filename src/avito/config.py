import os

from dotenv import load_dotenv


load_dotenv()


def _int_set_from_env(name: str) -> set[int]:
    values = os.getenv(name, "")
    result: set[int] = set()
    for raw in values.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.add(int(raw))
        except ValueError:
            continue
    return result


def _str_list_from_env(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


DEBUG = os.getenv("DEBUG", "False") == "True"

BOT_ID = int(os.getenv("AVITO_BOT_ID") or os.getenv("BOT_ID") or "0")
ITEM_IDS = _int_set_from_env("AVITO_ITEM_IDS")
BLOCKED_USERS = _str_list_from_env("BLOCKED_USERS")
ALLOWED_CHAT_IDS = set(_str_list_from_env("AVITO_ALLOWED_CHAT_IDS"))
