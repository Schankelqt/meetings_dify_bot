# pyrus_client.py
import os
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger("pyrus")
logger.setLevel(logging.INFO)

BASE_URL = (os.getenv("PYRUS_BASE_URL") or "").rstrip("/")  # напр.: https://pyrus.sovcombank.ru/api/v4
FORM_ID  = int(os.getenv("PYRUS_FORM_ID", "0") or 0)

# Если вы хотите жёстко прокинуть токен через .env — оставьте переменную,
# но клиент теперь умеет сам получать токен по логину/секрету при необходимости.
ACCESS_TOKEN = os.getenv("PYRUS_ACCESS_TOKEN") or ""

# Данные для автоматической авторизации
PYRUS_LOGIN        = os.getenv("PYRUS_LOGIN")         # vostrikovkk@sovcombank.ru
PYRUS_SECURITY_KEY = os.getenv("PYRUS_SECURITY_KEY")  # длинный ключ

# ID полей формы
FIELD_TG_ID            = int(os.getenv("PYRUS_FIELD_TG_ID", "1"))
FIELD_FULL_NAME        = int(os.getenv("PYRUS_FIELD_FULL_NAME", "2"))
FIELD_TEAM_ID          = int(os.getenv("PYRUS_FIELD_TEAM_ID", "3"))
FIELD_CONVERSATION_ID  = int(os.getenv("PYRUS_FIELD_CONV_ID", "4"))
FIELD_LAST_SUMMARY     = int(os.getenv("PYRUS_FIELD_LAST_SUMMARY", "5"))

# простенький кэш токена в рантайме
_token = ACCESS_TOKEN.strip()
_token_exp_ts = 0  # неизвестно, считаем протухшим -> получим при первом запросе

def enabled() -> bool:
    ok = bool(BASE_URL and FORM_ID and (PYRUS_LOGIN and PYRUS_SECURITY_KEY or _token))
    if not ok:
        logger.warning("[Pyrus] not fully configured — integration disabled")
    return ok

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token}" if _token else "",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _auth_url() -> str:
    # у вас корпоративный домен: API = https://<host>/api/v4
    # auth у них тоже под /api/v4/auth
    return f"{BASE_URL.rsplit('/api', 1)[0]}/api/v4/auth" if "/api/" in BASE_URL else f"{BASE_URL}/auth"

def _obtain_token() -> None:
    """Запросить новый access_token по логину и security_key."""
    global _token, _token_exp_ts
    if not (PYRUS_LOGIN and PYRUS_SECURITY_KEY):
        # нет учётки — остаёмся с тем, что есть
        return
    url = _auth_url()
    resp = requests.post(url, json={"login": PYRUS_LOGIN, "security_key": PYRUS_SECURITY_KEY}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    _token = data.get("access_token", "")
    # срок жизни из JWT можно распарсить, но проще выставить «перезапросить через час»
    _token_exp_ts = int(time.time()) + 3600
    logger.info("[Pyrus] fresh token obtained")

def _ensure_token():
    if not _token or time.time() >= _token_exp_ts:
        _obtain_token()

def _request(method: str, url: str, retry_on_401: bool = True, **kwargs) -> requests.Response:
    """Обёртка над requests с авто‑получением и авто‑обновлением токена."""
    _ensure_token()
    # заголовки формируем динамически, чтобы подхватить свежий токен
    headers = kwargs.pop("headers", {})
    headers = {**_headers(), **headers}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if resp.status_code == 401 and retry_on_401 and PYRUS_LOGIN and PYRUS_SECURITY_KEY:
        logger.warning("[Pyrus] 401 invalid_token — refreshing and retrying once")
        _obtain_token()
        headers = {**_headers(), **(kwargs.get("headers") or {})}
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp

def _log_resp(resp: requests.Response, label: str):
    body = ""
    try:
        body = resp.text[:2000]
    except Exception:
        body = "<no body>"
    logger.warning(f"[Pyrus] {label}: status={resp.status_code}, url={resp.request.url}, body={body}")

# -------- Создание задачи (единственный поддерживаемый у вас путь — /tasks) --------

def _create_task(fields: list[dict]) -> int:
    url = f"{BASE_URL}/tasks"
    payload = {"form_id": FORM_ID, "fields": fields}
    resp = _request("POST", url, json=payload)
    if resp.ok:
        data = resp.json()
        tid = data.get("task", {}).get("id") or data.get("id")
        if not tid:
            _log_resp(resp, "create_no_id")
            raise RuntimeError("No task id in response")
        return int(tid)
    _log_resp(resp, "create_failed")
    raise RuntimeError(f"Create task failed: {resp.status_code}")

def create_task_for_employee(
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    last_summary: str | None,
) -> int:
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    fields = [
        {"id": FIELD_TG_ID, "value": int(tg_chat_id)},
        {"id": FIELD_FULL_NAME, "value": (full_name or "")},
        {"id": FIELD_TEAM_ID, "value": int(team_id or 0)},
        {"id": FIELD_CONVERSATION_ID, "value": (conversation_id or "")},
        {"id": FIELD_LAST_SUMMARY, "value": (last_summary or "")},
    ]
    return _create_task(fields)

# -------- Обновление полей / комментарии --------

def update_task_fields(
    task_id: int,
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    last_summary: str | None,
):
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    url = f"{BASE_URL}/tasks/{task_id}/update"
    fields = [
        {"id": FIELD_TG_ID, "value": int(tg_chat_id)},
        {"id": FIELD_FULL_NAME, "value": (full_name or "")},
        {"id": FIELD_TEAM_ID, "value": int(team_id or 0)},
        {"id": FIELD_CONVERSATION_ID, "value": (conversation_id or "")},
        {"id": FIELD_LAST_SUMMARY, "value": (last_summary or "")},
    ]
    payload = {"fields": fields}
    resp = _request("POST", url, json=payload)
    if not resp.ok:
        _log_resp(resp, "update_failed")
        raise RuntimeError(f"Update fields failed: {resp.status_code}")

def add_summary_comment(task_id: int, summary_text: str):
    if not enabled():
        raise RuntimeError("Pyrus not configured")
    url = f"{BASE_URL}/tasks/{task_id}/comments"
    payload = {"text": summary_text}
    resp = _request("POST", url, json=payload)
    if not resp.ok:
        _log_resp(resp, "comment_failed")
        raise RuntimeError(f"Add comment failed: {resp.status_code}")

def upsert_summary_comment(
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    summary_text: str,
    ensure_task_cb=None,   # опционально: функция, которая вернёт task_id (например, достать из БД)
) -> int:
    """
    Вспомогательная: создать задачу (если надо), обновить поля, добавить комментарий.
    Вернёт task_id.
    """
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    task_id = None
    if ensure_task_cb:
        task_id = ensure_task_cb()
    if not task_id:
        task_id = create_task_for_employee(tg_chat_id, full_name, team_id, conversation_id, summary_text)

    update_task_fields(task_id, tg_chat_id, full_name, team_id, conversation_id, summary_text)
    add_summary_comment(task_id, summary_text)
    return task_id