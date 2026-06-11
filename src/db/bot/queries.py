from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .models import User, Message, USER_WRITABLE_COLUMN_KEYS
from ..mysql import session_factory


async def get_or_create_user(chat_id: str, name: str) -> User:
    """Получает пользователя или создает нового"""
    async with session_factory() as session:
        try:
            fields = {'chat_id': chat_id, 'name': name[:100]}
            user = User(**fields)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
        except IntegrityError:
            await session.rollback()
            # Пользователь уже существует, просто возвращаем его
            return await session.get(User, chat_id)


async def get_user(chat_id: str) -> User | None:
    """Получает пользователя по chat_id"""
    async with session_factory() as session:
        return await session.get(User, chat_id)


async def get_all_users() -> list[User]:
    """Получает всех пользователей из БД"""
    async with session_factory() as session:
        stmt = select(User)
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_last_messages(chat_id: str, limit: int | None = 3) -> list[Message]:
    """Получает последние сообщения чата"""
    async with session_factory() as session:
        stmt = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc(), Message.message_id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()


async def create_client_message(chat_id: str, text: str) -> int | None:
    """Сохраняет входящее сообщение клиента до вызова LLM."""
    async with session_factory() as session:
        last_stmt = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc(), Message.message_id.desc())
            .limit(1)
        )
        last = (await session.execute(last_stmt)).scalar_one_or_none()
        if (
            last
            and last.type == "client_message"
            and (last.user_message or "").strip() == (text or "").strip()
            and not (last.assistant_message or "").strip()
        ):
            return last.message_id

        message = Message(
            chat_id=chat_id,
            user_message=text,
            assistant_message=None,
            type="client_message",
        )
        session.add(message)
        await session.flush()
        message_id = message.message_id
        await session.commit()
        return message_id


async def attach_bot_answer(
    message_id: int,
    assistant_message: str,
    message_type: str = "bot_response",
) -> None:
    """Добавляет ответ бота к уже сохранённому сообщению клиента."""
    async with session_factory() as session:
        message = await session.get(Message, message_id)
        if not message:
            return
        message.assistant_message = assistant_message
        message.type = message_type
        await session.commit()


async def create_manager_message(chat_id: str, text: str) -> None:
    """Сохраняет ручное исходящее сообщение менеджера."""
    async with session_factory() as session:
        message = Message(
            chat_id=chat_id,
            user_message=None,
            assistant_message=text,
            type="manager_message",
        )
        session.add(message)
        await session.commit()


async def update_user_data(chat_id: str, update_data: dict):
    """Обновляет данные пользователя"""
    async with session_factory() as session:
        user = await session.get(User, chat_id)
        if not user:
            return
        
        for field, value in update_data.items():
            if field not in USER_WRITABLE_COLUMN_KEYS:
                continue
            setattr(user, field, value)
        
        await session.commit()


async def set_answers_from_agent(chat_id: str, value: bool) -> bool:
    """Установка значения answers_from_agent для пользователя"""
    async with session_factory() as session:
        user = await session.get(User, chat_id)
        if not user:
            return False
        user.answers_from_agent = value
        if value:
            user.final_stage = False
        await session.commit()
        return True


async def get_saved_outgoing_texts(chat_id: str) -> list[str]:
    """Достаёт сохранённые исходящие тексты бота и менеджера."""
    async with session_factory() as session:
        stmt = select(Message.assistant_message).where(Message.chat_id == chat_id)
        res = await session.execute(stmt)
        return [row[0] for row in res.all()]


async def clear_user_agent_data(chat_id: str, name: str | None) -> bool:
    async with session_factory() as session:
        user = await session.get(User, chat_id)
        if not user:
            return False
        await session.execute(delete(Message).where(Message.chat_id == chat_id))
        user.name = name[:100] if name else None
        user.phone = None
        user.extra = None
        user.final_stage = False
        user.answers_from_agent = True
        await session.commit()
        return True


async def set_answers_from_agent_false(chat_id: str) -> bool:
    """
    Ставит answers_from_agent=False.
    Возвращает True если обновили (пользователь найден).
    """
    async with session_factory() as session:
        user = await session.get(User, chat_id)
        if not user:
            return False

        if user.answers_from_agent is False:
            return True  # уже False, считаем успехом

        user.answers_from_agent = False
        await session.commit()
        return True
