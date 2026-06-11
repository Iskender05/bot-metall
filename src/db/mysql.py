from datetime import datetime
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE


URI = f'mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}'

engine = create_async_engine(
    url=URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

session_factory = async_sessionmaker(engine)


async def get_db():
    """Получение соединения с базой данных"""
    async with session_factory() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            raise e


class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(server_default=text('CURRENT_TIMESTAMP'))
