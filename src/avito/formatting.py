from db.bot.models import Message, User


def _format_message(message: Message) -> str:
    parts: list[str] = []
    created = message.created_at.strftime("%d.%m.%Y %H:%M:%S") if message.created_at else ""

    if message.type == "manager_message":
        text = message.assistant_message or ""
        parts.append(f"Менеджер [{created}]:\n{text}")
        return "\n".join(parts)

    if message.user_message:
        parts.append(f"Клиент [{created}]:\n{message.user_message}")
    if message.assistant_message:
        parts.append(f"Бот [{created}]:\n{message.assistant_message}")
    return "\n\n".join(parts)


def format_qualified_lead(user: User, messages: list[Message]) -> str:
    status = "бот остановлен" if (not user.answers_from_agent) or user.final_stage else "бот активен"
    text = (
        "ЗАЯВКА МИР МЕТАЛЛА\n"
        f"Чат ID: {user.chat_id}\n"
        f"Имя в чате: {user.name or '-'}\n"
        f"Статус: {status}\n"
        f"Ссылка на чат: https://www.avito.ru/profile/messenger/channel/{user.chat_id}\n\n"
        "История чата:\n\n"
    )

    text += "\n\n".join(_format_message(message) for message in messages)
    return text[:4090] + ("..." if len(text) > 4090 else "")
