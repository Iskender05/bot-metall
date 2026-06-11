import pandas as pd
import logging
from datetime import datetime
from io import BytesIO
from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, BotCommand
from aiogram.enums import ChatType

from tg_bot.config import ADMIN_IDS
from db.bot.queries import get_all_users, get_last_messages, set_answers_from_agent



# Создаем роутер для админ-панели
router = Router()
router.message.filter(lambda message: message.from_user.id in ADMIN_IDS and message.chat.type == ChatType.PRIVATE)

logger = logging.getLogger(__name__)


commands_list = [
    BotCommand(command='users', description='Все пользователи чата'),
    BotCommand(command='chats', description='Активные чаты'),
    BotCommand(command='blocked_chats', description='Заблокированные чаты'),
    BotCommand(command='messages', description='История сообщений пользователя. Вводить с аргументом <chat_id>'),
    BotCommand(command='block', description='Блокировка общения пользователя с ботом. Вводить с аргументом <chat_id>'),
    BotCommand(command='unblock', description='Разблокировка общения пользователя с ботом. Вводить с аргументом <chat_id>'),
]


@router.message(Command('users'))
async def cmd_users(message: types.Message):
    """Обработка команды /users - выгрузка пользователей в Excel"""
    try:
        users = await get_all_users()
        
        if not users:
            await message.answer('В базе нет пользователей')
            return
        
        # Подготовка данных
        data = [{
            'Chat ID': user.chat_id,
            'Имя в чате': user.name,
            'Телефон': user.phone,
            'Дополнительно': user.extra,
            'Бот завершил работу': getattr(user, 'final_stage', None),
            'Должен ли отвечать бот': getattr(user, 'answers_from_agent', None)
        } for user in users]
        
        df = pd.DataFrame(data)
        
        # Генерация имени файла
        now = datetime.now()
        filename = f'Пользователи {now.hour:02d}.{now.minute:02d}.{now.second:02d} {now.day:02d}-{now.month:02d}-{now.year}.xlsx'
        
        # Создание Excel в памяти
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Пользователи')
            worksheet = writer.sheets['Пользователи']
            
            # Подбор ширины колонок
            for column in worksheet.columns:
                max_len = max(len(str(cell.value)) for cell in column)
                worksheet.column_dimensions[column[0].column_letter].width = (max_len + 2) * 1.2
        
        # Отправка файла
        await message.answer_document(
            document=BufferedInputFile(output.getvalue(), filename=filename),
            caption=f'Список пользователей (всего: {len(users)})'
        )
        
    except Exception as e:
        logger.info(f'Ошибка при выгрузке пользователей: {e}')
        await message.answer('⚠️ Произошла ошибка при формировании отчета')


@router.message(Command('messages'))
async def cmd_messages(message: types.Message):
    """Обработка команды /messages - выгрузка истории сообщений пользователя в Excel"""
    try:
        # Парсим аргументы команды
        args = message.text.split()
        if len(args) < 2:
            await message.answer('❗ Укажите chat_id пользователя: /messages {chat_id}')
            return
        
        chat_id = args[1]
        
        # Получаем все сообщения пользователя
        messages = await get_last_messages(chat_id, None)
        
        if not messages:
            await message.answer(f'📭 В базе нет сообщений для пользователя {chat_id}')
            return
        
        # Подготовка данных
        data = []
        for msg in messages:
            if msg.type == 'manager_message':
                role = 'Менеджер'
                content = msg.assistant_message or ''
            elif msg.assistant_message and msg.user_message:
                role = 'Клиент / бот'
                content = f"Клиент: {msg.user_message}\nБот: {msg.assistant_message}"
            elif msg.user_message:
                role = 'Клиент'
                content = msg.user_message or ''
            else:
                role = 'Бот'
                content = msg.assistant_message or ''

            data.append({
                'Роль': role,
                'Сообщение': content,
                'Тип сообщения': msg.type or '',
                'Дата и время сообщения': msg.created_at.strftime('%d.%m.%Y %H:%M:%S') if msg.created_at else ''
            })
        
        df = pd.DataFrame(data)
        
        # Генерация имени файла
        now = datetime.now()
        filename = f'Пользователь {chat_id} {now.hour:02d}.{now.minute:02d}.{now.second:02d} {now.day:02d}-{now.month:02d}-{now.year}.xlsx'
        
        # Создание Excel в памяти
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Сообщения')
            worksheet = writer.sheets['Сообщения']
            
            # Подбор ширины колонок
            for column in worksheet.columns:
                max_len = max(len(str(cell.value)) for cell in column)
                worksheet.column_dimensions[column[0].column_letter].width = (max_len + 2) * 1.2
        
        # Отправка файла
        await message.answer_document(
            document=BufferedInputFile(output.getvalue(), filename=filename),
            caption=f'История сообщений пользователя {chat_id} (всего: {len(messages)})'
        )
        
    except Exception as e:
        logger.info(f'Ошибка при выгрузке сообщений: {e}')
        await message.answer('⚠️ Произошла ошибка при формировании отчета')


@router.message(Command('block'))
async def cmd_block(message: types.Message):
    """Обработка команды /block - блокировка пользователя"""
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer('❗ Укажите chat_id пользователя: /block {chat_id}')
            return
        
        chat_id = args[1]

        # Устанавливаем answers_from_agent в False
        success = await set_answers_from_agent(chat_id, False)
        
        if success:
            await message.answer(f'✅ Пользователь {chat_id} заблокирован (бот не будет отвечать)')
        else:
            await message.answer('❌ Пользователь не найден')
            
    except Exception as e:
        logger.error(f'Ошибка при блокировке пользователя: {e}')
        await message.answer('⚠️ Произошла ошибка при блокировке пользователя')


@router.message(Command('unblock'))
async def cmd_unblock(message: types.Message):
    """Обработка команды /unblock - разблокировка пользователя"""
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer('❗ Укажите chat_id пользователя: /unblock {chat_id}')
            return
        
        chat_id = args[1]

        # Устанавливаем answers_from_agent в True
        success = await set_answers_from_agent(chat_id, True)
        
        if success:
            await message.answer(f'✅ Пользователь {chat_id} разблокирован (бот будет отвечать)')
        else:
            await message.answer('❌ Пользователь не найден')
            
    except Exception as e:
        logger.error(f'Ошибка при разблокировке пользователя: {e}')
        await message.answer('⚠️ Произошла ошибка при разблокировке пользователя')


@router.message(Command('chats'))
async def cmd_chats(message: types.Message):
    """Обработка команды /chats - список активных чатов"""
    try:
        users = await get_all_users()
        active_users = [user for user in users if user.answers_from_agent and not user.final_stage]
        
        if not active_users:
            await message.answer('📭 Нет активных чатов')
            return
        
        # Формируем список чатов
        chats_text = ''
        for user in active_users:
            chat_line = f'[{user.name}](https://www.avito.ru/profile/messenger/channel/{user.chat_id}): {user.chat_id}\n'
            
            # Проверяем, не превысит ли добавление новой строки лимит
            if len(chats_text) + len(chat_line) > 4096:
                # Отправляем текущее сообщение и начинаем новое
                await message.answer(chats_text, parse_mode='Markdown')
                chats_text = chat_line
            else:
                chats_text += chat_line
        
        # Отправляем оставшуюся часть
        if chats_text:
            await message.answer(chats_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f'Ошибка при получении списка чатов: {e}')
        await message.answer('⚠️ Произошла ошибка при получении списка чатов')


@router.message(Command('blocked_chats'))
async def cmd_blocked_chats(message: types.Message):
    """Обработка команды /blocked_chats - список заблокированных чатов"""
    try:
        users = await get_all_users()
        blocked_users = [user for user in users if (not user.answers_from_agent) or user.final_stage]
        
        if not blocked_users:
            await message.answer('🔒 Нет заблокированных чатов')
            return
        
        # Формируем список чатов
        chats_text = ''
        for user in blocked_users:
            chat_line = f'[{user.name}](https://www.avito.ru/profile/messenger/channel/{user.chat_id}): {user.chat_id}\n'
            
            # Проверяем, не превысит ли добавление новой строки лимит
            if len(chats_text) + len(chat_line) > 4096:
                # Отправляем текущее сообщение и начинаем новое
                await message.answer(chats_text, parse_mode='Markdown')
                chats_text = chat_line
            else:
                chats_text += chat_line
        
        # Отправляем оставшуюся часть
        if chats_text:
            await message.answer(chats_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f'Ошибка при получении списка заблокированных чатов: {e}')
        await message.answer('⚠️ Произошла ошибка при получении списка заблокированных чатов')


