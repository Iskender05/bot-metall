import os
from dotenv import load_dotenv


load_dotenv()

DEBUG = os.getenv("DEBUG", "False") == "True"
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
]


def parse_group_targets(raw: str) -> list[tuple[int, int | None]]:
    """Формат:
    - -1001234567890
    - -1001234567890:42
    """
    raw = (raw or "").replace(" ", "")
    if not raw:
        return []

    targets: list[tuple[int, int | None]] = []

    for item in raw.split(","):
        if not item:
            continue

        if ":" in item:
            chat_id, thread_id = item.split(":", 1)
            targets.append((int(chat_id), int(thread_id)))
        else:
            targets.append((int(item), None))

    return targets


ADMIN_GROUPS_IDS = parse_group_targets(os.getenv("ADMIN_GROUPS_IDS", ""))
