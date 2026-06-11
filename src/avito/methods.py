import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List

import httpx


logger = logging.getLogger(__name__)


AVITO_CLIENT_ID = os.getenv("AVITO_CLIENT_ID", "")
AVITO_CLIENT_SECRET = os.getenv("AVITO_CLIENT_SECRET", "")
AVITO_HTTP_MAX_RETRIES = int(os.getenv("AVITO_HTTP_MAX_RETRIES", "3"))
AVITO_HTTP_BACKOFF_BASE = float(os.getenv("AVITO_HTTP_BACKOFF_BASE", "1"))
AVITO_HTTP_BACKOFF_MAX = float(os.getenv("AVITO_HTTP_BACKOFF_MAX", "30"))
AVITO_MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("AVITO_MIN_REQUEST_INTERVAL_SECONDS", "0.3"))

_client: httpx.AsyncClient | None = None
_token_info: dict[str, Any] = {}
_token_expires_at = 0.0
_token_lock = asyncio.Lock()
_request_lock = asyncio.Lock()
_last_request_at = 0.0


class AvitoHTTPError(RuntimeError):
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Ошибка {status_code}: {body}")


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient()
    return _client


async def _rate_limit() -> None:
    global _last_request_at
    async with _request_lock:
        now = time.monotonic()
        wait_for = AVITO_MIN_REQUEST_INTERVAL_SECONDS - (now - _last_request_at)
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        _last_request_at = time.monotonic()


def _parse_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), AVITO_HTTP_BACKOFF_MAX)
            except ValueError:
                pass
    delay = min(AVITO_HTTP_BACKOFF_BASE * (2 ** attempt), AVITO_HTTP_BACKOFF_MAX)
    return delay + random.uniform(0, 0.5)


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _request_label(method: str, url: str) -> str:
    return f"{method.upper()} {url.replace('https://api.avito.ru', '')}"


async def _request(
    method: str,
    url: str,
    *,
    auth: bool = True,
    timeout: float = 10,
    headers: dict[str, str] | None = None,
    **kwargs,
) -> httpx.Response:
    method = method.upper()
    request_headers = dict(headers or {})
    client = await _get_client()
    label = _request_label(method, url)

    for attempt in range(AVITO_HTTP_MAX_RETRIES + 1):
        if auth:
            access_token = (await get_token()).get("access_token")
            if not access_token:
                raise ValueError("Не удалось получить access_token")
            request_headers["Authorization"] = f"Bearer {access_token}"

        try:
            await _rate_limit()
            started_at = time.monotonic()
            logger.info(
                "Avito API request: %s attempt=%s/%s timeout=%.1f",
                label,
                attempt + 1,
                AVITO_HTTP_MAX_RETRIES + 1,
                timeout,
            )
            response = await client.request(
                method,
                url,
                headers=request_headers,
                timeout=timeout,
                **kwargs,
            )
            elapsed = time.monotonic() - started_at
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as err:
            if attempt >= AVITO_HTTP_MAX_RETRIES:
                logger.exception(
                    "Avito API request failed permanently: %s attempt=%s/%s error=%s",
                    label,
                    attempt + 1,
                    AVITO_HTTP_MAX_RETRIES + 1,
                    err,
                )
                raise
            delay = _retry_delay(attempt)
            logger.warning(
                "Avito API temporary error: %s attempt=%s/%s error=%s retry_in=%.1f",
                label,
                attempt + 1,
                AVITO_HTTP_MAX_RETRIES + 1,
                err,
                delay,
            )
            await asyncio.sleep(delay)
            continue

        if 200 <= response.status_code < 300:
            logger.info(
                "Avito API response: %s status=%s elapsed=%.2fs attempt=%s/%s",
                label,
                response.status_code,
                elapsed,
                attempt + 1,
                AVITO_HTTP_MAX_RETRIES + 1,
            )
            return response

        if response.status_code == 401 and auth:
            await invalidate_token()

        if not _is_retryable_status(response.status_code) or attempt >= AVITO_HTTP_MAX_RETRIES:
            body = _parse_body(response)
            logger.error(
                "Avito API error response: %s status=%s elapsed=%.2fs attempt=%s/%s body=%s",
                label,
                response.status_code,
                elapsed,
                attempt + 1,
                AVITO_HTTP_MAX_RETRIES + 1,
                body,
            )
            raise AvitoHTTPError(response.status_code, body)

        delay = _retry_delay(attempt, response)
        logger.warning(
            "Avito API retryable response: %s status=%s elapsed=%.2fs attempt=%s/%s retry_in=%.1f",
            label,
            response.status_code,
            elapsed,
            attempt + 1,
            AVITO_HTTP_MAX_RETRIES + 1,
            delay,
        )
        await asyncio.sleep(delay)

    raise RuntimeError("Не удалось выполнить запрос к Avito API")


async def invalidate_token() -> None:
    global _token_expires_at
    async with _token_lock:
        _token_info.clear()
        _token_expires_at = 0.0


# POST - получаем authorization token
async def get_token():
    global _token_expires_at
    now = time.monotonic()
    if _token_info.get("access_token") and now < _token_expires_at:
        return dict(_token_info)

    async with _token_lock:
        now = time.monotonic()
        if _token_info.get("access_token") and now < _token_expires_at:
            return dict(_token_info)

        if not AVITO_CLIENT_ID or not AVITO_CLIENT_SECRET:
            raise ValueError("Не заданы AVITO_CLIENT_ID или AVITO_CLIENT_SECRET")

        url = "https://api.avito.ru/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": AVITO_CLIENT_ID,
            "client_secret": AVITO_CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = await _request(
            "POST",
            url,
            auth=False,
            data=data,
            headers=headers,
            timeout=10,
        )
        result = response.json()

        if not result.get("access_token"):
            logger.error("Ошибка получения токена Avito: %s", result)
            return result

        expires_in = int(result.get("expires_in") or 3600)
        _token_info.clear()
        _token_info.update(result)
        _token_expires_at = time.monotonic() + max(expires_in - 60, 60)
        logger.info("Avito token refreshed: expires_in=%s", expires_in)

        return dict(_token_info)

# GET - получаем чаты
async def get_chats(user_id: int, item_ids: list = None, unread_only: bool = True):
    url = f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"

    params = {}
    if item_ids:
        params["item_ids"] = ",".join(str(item_id) for item_id in item_ids)
    if unread_only:
        params["unread_only"] = "true"

    logger.info(
        "Avito get chats: user_id=%s unread_only=%s item_ids_count=%s",
        user_id,
        unread_only,
        len(item_ids or []),
    )
    response = await _request("GET", url, params=params, timeout=10)
    result = response.json()
    logger.info(
        "Avito get chats result: user_id=%s chats_count=%s",
        user_id,
        len((result or {}).get("chats", []) or []),
    )

    #print("Чаты:", result)
    return result

# POST - отправка сообщения конкретному пользователю с неотвеченным сообщениями
async def send_message(user_id: int, chat_id: str, text: str):
    url = f"https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "message": {"text": text},
        "type": "text",
    }
    logger.info(
        "Avito send message: user_id=%s chat_id=%s text_len=%s",
        user_id,
        chat_id,
        len(text or ""),
    )
    resp = await _request("POST", url, json=payload, headers=headers, timeout=15)
    result = _parse_body(resp)
    logger.info("Avito send message result: chat_id=%s response=%s", chat_id, result)
    return result

# Получаем последнее сообщение от пользователя
async def find_last_message(chats, target_author_id):
    for chat in chats.get("chats", []):
        if chat.get("last_message", {}).get("author_id") == target_author_id:
            return chat["last_message"].get("content", {}).get("text")
    return None

# Парсим all chats
def parse_chats_summary(chats_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Возвращает список словарей:
    {
      "chat_id": str,
      "name": str,
      "last_message": { "type": str, "content": Any },
      "item_id": str
    }
    """
    chats = (chats_result or {}).get("chats", [])
    out: List[Dict[str, Any]] = []

    for ch in chats:
        chat_id = ch.get("id")

        # выбираем собеседника
        users = ch.get("users", []) or []
        other = next((u for u in users if not u.get("is_me")), None)
        if other is None and users:
            other = users[0]
        name = (other or {}).get("name", "Unknown")

        # обрабатываем последнее сообщение
        last_message = ch.get("last_message") or {}
        msg_type = last_message.get("type", "unknown")
        content = last_message.get("content") or {}

        if msg_type == "text":
            value = content.get("text", "")
        elif msg_type == "image":
            sizes = (((content.get("image") or {}).get("sizes")) or {})
            def size_key(k: str) -> int:
                try:
                    return int(k.split("x")[0])
                except Exception:
                    return 0
            value = ""
            if sizes:
                best_key = sorted(sizes.keys(), key=size_key, reverse=True)[0]
                value = sizes.get(best_key, "")
        else:
            value = content
        
        context = ch.get('context', {})
        item_id = None
        if context.get('type', '') == 'item':
            item_id = context.get('value', {}).get('id', None)

        out.append({
            "chat_id": chat_id,
            "name": name,
            "last_message": {"type": msg_type, "content": value},
            'item_id': item_id
        })

    # Красивый вывод
    #print("\nСписок всех пользователей:\n")
    #for u in out:
        #print(
        #    f"Чат ID: {u['chat_id']}\n"
        #    f"Имя: {u['name']}\n"
        #    f"Последнее сообщение ({u['last_message']['type']}): {u['last_message']['content']}\n"
        #    f"{'-'*50}\n"
        #)

    return out

# Парсинг одного чата
def parse_single_chat(chats_result: Dict[str, Any], chat_id: str) -> Dict[str, Any]:
    """
    Ищет конкретный чат по chat_id в выводе get_chats(...)
    Возвращает словарь:
    {
      "chat_id": str,
      "name": str,
      "last_message": { "type": str, "content": Any }
    }
    """
    chats = (chats_result or {}).get("chats", [])
    chat = next((c for c in chats if str(c.get("id")) == str(chat_id)), None)

    if not chat:
        print(f"\n❌ Чат с ID {chat_id} не найден.\n")
        return {}

    users = chat.get("users", []) or []
    other = next((u for u in users if not u.get("is_me")), None)
    if other is None and users:
        other = users[0]
    name = (other or {}).get("name", "Unknown")

    last_message = chat.get("last_message") or {}
    msg_type = last_message.get("type", "unknown")
    content = last_message.get("content") or {}

    if msg_type == "text":
        value = content.get("text", "")
    elif msg_type == "image":
        sizes = (((content.get("image") or {}).get("sizes")) or {})
        def size_key(k: str) -> int:
            try:
                return int(k.split("x")[0])
            except Exception:
                return 0
        value = ""
        if sizes:
            best_key = sorted(sizes.keys(), key=size_key, reverse=True)[0]
            value = sizes.get(best_key, "")
    else:
        value = content

    result = {
        "chat_id": chat_id,
        "name": name,
        "last_message": {"type": msg_type, "content": value}
    }

    # Красивый вывод
    #print("\nИнформация по выбранному пользователю:\n")
    #print(
    #    f"Чат ID: {result['chat_id']}\n"
    #    f"Имя: {result['name']}\n"
    #    f"Последнее сообщение ({result['last_message']['type']}): {result['last_message']['content']}\n"
    #    f"{'-'*50}\n"
    #)

    return result


async def fetch_chat_messages_v3(
    user_id: int,
    chat_id: str,
    *,
    page_size: int = 100,
    max_pages: int = 50,
) -> List[Dict[str, Any]]:
    """
    Сырой загрузчик: забирает сообщения чата из v3/messages с пагинацией
    и возвращает единый список messages как их отдаёт Avito.
    """
    url = f"https://api.avito.ru/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/"
    headers = {
        "Accept": "application/json",
    }

    limit = max(1, min(int(page_size), 100))
    offset = 0

    all_messages: List[Dict[str, Any]] = []

    logger.info(
        "Avito fetch chat messages: user_id=%s chat_id=%s page_size=%s max_pages=%s",
        user_id,
        chat_id,
        limit,
        max_pages,
    )
    for page in range(max_pages):
        params = {"limit": limit, "offset": offset}
        resp = await _request("GET", url, headers=headers, params=params, timeout=50)

        data = resp.json() or {}
        messages = data.get("messages", [])
        logger.info(
            "Avito fetch chat messages page: chat_id=%s page=%s offset=%s messages_count=%s",
            chat_id,
            page + 1,
            offset,
            len(messages),
        )
        if not messages:
            break

        all_messages.extend(messages)

        offset += limit
        if len(messages) < limit:
            break

    logger.info(
        "Avito fetch chat messages result: chat_id=%s total_messages=%s",
        chat_id,
        len(all_messages),
    )
    return all_messages


def extract_my_outgoing_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Возвращает ВСЕ сообщения, отправленные моим профилем (direction='out'), исключая system."""
    result: List[Dict[str, Any]] = []

    for m in messages or []:
        if m.get("direction") != "out":
            continue

        msg_type = m.get("type") or "unknown"
        if msg_type == "system":
            continue

        result.append({
            "type": msg_type,
            "value": m.get("content") or {},
        })

    return result


def extract_new_user_text_until_last_my_reply(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    - склеивает только text через '\\n'
    - has_non_text=True, если встречено incoming сообщение типа НЕ text/deleted/system
    """
    collected_texts_newest_first: List[str] = []
    has_non_text: bool = False
    found_my_last_reply: bool = False

    # ВАЖНО: предполагаем, что messages идут от новых к старым (как обычно в Avito v3 по offset/limit).
    for m in messages or []:
        direction = m.get("direction")
        msg_type = m.get("type") or "unknown"

        # Встретили первый out (самый новый out) => это и есть "мой последний ответ"
        if direction == "out":
            found_my_last_reply = True
            break

        if direction != "in":
            continue

        if msg_type in ("system", "deleted"):
            continue

        if msg_type == "text":
            text = ((m.get("content") or {}).get("text")) or ""
            if text.strip():
                collected_texts_newest_first.append(text)
        else:
            has_non_text = True

    return {
        "text": "\n".join(list(reversed(collected_texts_newest_first))),
        "has_non_text": has_non_text,
        "found_my_last_reply": found_my_last_reply,
    }


