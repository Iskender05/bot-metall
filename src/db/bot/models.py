from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Annotated

from ..mysql import Base


str_100   = Annotated[str  | None,  mapped_column(String(100), nullable=True)]
str_text  = Annotated[str  | None,  mapped_column(Text(),      nullable=True)]

class User(Base):
    __tablename__ = 'users'

    chat_id:  Mapped[str] = mapped_column(String(50), primary_key=True)
    name:     Mapped[str_100]
    phone:              Mapped[str_100]
    extra:              Mapped[str_100]

    final_stage:        Mapped[bool] = mapped_column(default=False)
    answers_from_agent: Mapped[bool] = mapped_column(default=True)

    messages:   Mapped[list['Message']] = relationship()


USER_WRITABLE_COLUMN_KEYS = frozenset(User.__table__.columns.keys())


class Message(Base):
    __tablename__ = 'messages'

    message_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id:    Mapped[str] = mapped_column(ForeignKey('users.chat_id', ondelete='CASCADE'))

    user_message:       Mapped[str_text]
    assistant_message:  Mapped[str_text]
    type: Mapped[str] = mapped_column(String(30))
