# pyrus_client.py
import os
import time
import logging
import requests
from typing import Optional

# ---------- логирование ----------
logger = logging.getLogger("pyrus")
logger.setLevel(logging.INFO)

# ---------- .env ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("[Pyrus] .env loaded by pyrus_client.py")
except Exception:
    pass

# ---------- конфиг ----------
BASE_URL = (os.getenv("PYRUS_BASE_URL") or "").rstrip("/")   # https://pyrus.sovcombank.ru/api/v4
FORM_ID  = int(os.getenv("PYRUS_FORM_ID", "0") or 0)

# авто-аутентификация
PYRUS_LOGIN        = os.getenv("PYRUS_LOGIN")         # e-mail
PYRUS_SECURITY_KEY = os.getenv("PYRUS_SECURITY_KEY")  # секретный API ключ (длинная строка)
# Не используй секретный ключ как Bearer-токен!
# PYRUS_ACCESS_TOKEN можно оставить пустым — клиент сам его получит
ACCESS_TOKEN = os.getenv("PYRUS_ACCESS_TOKEN", "").strip()

# ID полей
FIELD_TG_ID           = int(os.getenv("PYRUS_FIELD_TG_ID", "1"))
FIELD_FULL_NAME       = int(os.getenv("PYRUS_FIELD_FULL_NAME", "2"))
FIELD_TEAM_ID         = int(os.getenv("PYRUS_FIELD_TEAM_ID", "3"))
FIELD_CONVERSATION_ID = int(os.getenv("PYRUS_FIELD_CONV_ID", "4"))
FIELD_LAST_SUMMARY    = int(os.getenv("PYRUS_FIELD_LAST_SUMMARY", "5"))

# ---------- токен (кэш в памяти процесса) ----------
_token = ACCESS_TOKEN
_token_exp_ts = 0  # заставим получить новый при первом запросе

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
    # BASE_URL вида https://host/api/v4 -> берём тот же корень
    if "/api/" in BASE_URL:
        return f"{BASE_URL.rsplit('/api', 1)[0]}/api/v4/auth"
    return f"{BASE_URL}/auth"

def _obtain_token() -> None:
    """Запросить новый access_token по логину и security_key."""
    global _token, _token_exp_ts
    if not (PYRUS_LOGIN and PYRUS_SECURITY_KEY):
        logger.warning("[Pyrus] no login/security_key — cannot obtain token")
        return
    url = _auth_url()
    resp = requests.post(url, json={"login": PYRUS_LOGIN, "security_key": PYRUS_SECURITY_KEY}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    _token = data.get("access_token", "")
    # Перезапросим через ~1 час (в JWT есть exp, но для простоты так).
    _token_exp_ts = int(time.time()) + 3600
    logger.info("[Pyrus] fresh token obtained")

def _ensure_token():
    if not _token or time.time() >= _token_exp_ts:
        _obtain_token()

def _request(method: str, url: str, retry_on_401: bool = True, **kwargs) -> requests.Response:
    """requests + автообновление токена (один ретрай при 401)."""
    _ensure_token()
    headers = {**_headers(), **(kwargs.pop("headers", {}) or {})}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if resp.status_code == 401 and retry_on_401 and PYRUS_LOGIN and PYRUS_SECURITY_KEY:
        logger.warning("[Pyrus] 401 invalid_token — refreshing and retrying once")
        _obtain_token()
        headers = {**_headers(), **(kwargs.get("headers") or {})}
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp

def _log_resp(resp: requests.Response, label: str):
    try:
        body = resp.text[:2000]
    except Exception:
        body = "<no body>"
    logger.warning(f"[Pyrus] {label}: status={resp.status_code}, url={resp.request.url}, body={body}")

# ---------- создание задачи ----------
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

# ---------- обновление полей и комментарии ----------
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
    resp = _request("POST", url, json={"fields": fields})
    if not resp.ok:
        _log_resp(resp, "update_failed")
        raise RuntimeError(f"Update fields failed: {resp.status_code}")

def add_summary_comment(task_id: int, summary_text: str):
    if not enabled():
        raise RuntimeError("Pyrus not configured")
    url = f"{BASE_URL}/tasks/{task_id}/comments"
    resp = _request("POST", url, json={"text": summary_text})
    if not resp.ok:
        _log_resp(resp, "comment_failed")
        raise RuntimeError(f"Add comment failed: {resp.status_code}")

def upsert_summary_comment(
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    summary_text: str,
    ensure_task_cb=None,
) -> int:
    """Создать задачу (если нет), обновить поля, добавить комментарий. Вернёт task_id."""
    if not enabled():
        raise RuntimeError("Pyrus not configured")
    task_id = ensure_task_cb() if ensure_task_cb else None
    if not task_id:
        task_id = create_task_for_employee(tg_chat_id, full_name, team_id, conversation_id, summary_text)
    update_task_fields(task_id, tg_chat_id, full_name, team_id, conversation_id, summary_text)
    add_summary_comment(task_id, summary_text)
    return task_id