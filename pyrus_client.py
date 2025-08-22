# pyrus_client.py
import os
import logging
import requests
from typing import Optional, List, Dict

logger = logging.getLogger("pyrus")
logger.setLevel(logging.INFO)

# Базовые настройки из .env
BASE_URL = (os.getenv("PYRUS_BASE_URL") or "").rstrip("/")   # напр.: https://pyrus.sovcombank.ru/api/v4
TOKEN    = os.getenv("PYRUS_ACCESS_TOKEN")                   # Bearer-токен
FORM_ID  = int(os.getenv("PYRUS_FORM_ID", "0") or 0)

# ID полей формы (получены через pyrus.py)
FIELD_TG_ID           = int(os.getenv("PYRUS_FIELD_TG_ID", "1"))
FIELD_FULL_NAME       = int(os.getenv("PYRUS_FIELD_FULL_NAME", "2"))
FIELD_TEAM_ID         = int(os.getenv("PYRUS_FIELD_TEAM_ID", "3"))
FIELD_CONVERSATION_ID = int(os.getenv("PYRUS_FIELD_CONV_ID", "4"))
FIELD_LAST_SUMMARY    = int(os.getenv("PYRUS_FIELD_LAST_SUMMARY", "5"))


def _headers() -> Dict[str, str]:
    """Собираем заголовки. Если токена нет — не добавляем Authorization вообще."""
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def enabled() -> bool:
    ok = bool(BASE_URL and TOKEN and FORM_ID)
    if not ok:
        logger.warning("[Pyrus] not fully configured — integration disabled")
    return ok


def configured(*args, **kwargs) -> bool:
    """Алиас для обратной совместимости с вызовами configured(True)."""
    return enabled()


def _log_resp(resp: requests.Response, label: str):
    try:
        body = resp.text[:2000]
    except Exception:
        body = "<no body>"
    logger.warning(f"[Pyrus] {label}: status={resp.status_code}, url={resp.url}, body={body}")


# ---------- Поиск задачи сотрудника ----------

def _search_task_primary(tg_chat_id: int) -> Optional[int]:
    """
    Вариант 1: GET /tasks?form_id=...&text=...
    """
    url = f"{BASE_URL}/tasks"
    params = {"form_id": FORM_ID, "text": str(tg_chat_id)}
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.ok:
        data = resp.json() if resp.content else {}
        tasks = (data.get("tasks") or []) if isinstance(data, dict) else []
        if tasks:
            tid = tasks[0].get("id")
            return int(tid) if tid is not None else None
        return None
    _log_resp(resp, "search_primary_failed")
    return None


def _search_task_fallback(tg_chat_id: int) -> Optional[int]:
    """
    Вариант 2: POST /tasks/search  (в некоторых доменах — единственно доступный)
    """
    url = f"{BASE_URL}/tasks/search"
    payload = {
        "form_id": FORM_ID,
        "text": str(tg_chat_id),
        # при необходимости можно добавить доп. фильтры (date_from, date_to, statuses и т.д.)
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        data = resp.json() if resp.content else {}
        tasks = (data.get("tasks") or []) if isinstance(data, dict) else []
        if tasks:
            tid = tasks[0].get("id")
            return int(tid) if tid is not None else None
        return None
    _log_resp(resp, "search_fallback_failed")
    return None


def find_employee_task(tg_chat_id: int) -> Optional[int]:
    """
    Пытаемся найти персональную задачу сотрудника по Telegram Chat ID.
    """
    try:
        tid = _search_task_primary(tg_chat_id)
        if tid:
            return tid
        return _search_task_fallback(tg_chat_id)
    except Exception as e:
        logger.error(f"[Pyrus] search exception: {e}")
        return None


# ---------- Создание задачи ----------

def _create_task_primary(fields: List[Dict]) -> int:
    """
    Вариант 1: POST /tasks
    """
    url = f"{BASE_URL}/tasks"
    payload = {"form_id": FORM_ID, "fields": fields}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        data = resp.json() if resp.content else {}
        tid = (data.get("task") or {}).get("id") or data.get("id")
        if not tid:
            _log_resp(resp, "create_primary_no_id")
            raise RuntimeError("No task id in response")
        return int(tid)
    _log_resp(resp, "create_primary_failed")
    raise RuntimeError(f"Create task failed: {resp.status_code}")


def _create_task_fallback(fields: List[Dict]) -> int:
    """
    Вариант 2: POST /tasks/create
    """
    url = f"{BASE_URL}/tasks/create"
    payload = {"form_id": FORM_ID, "fields": fields}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        data = resp.json() if resp.content else {}
        tid = (data.get("task") or {}).get("id") or data.get("id")
        if not tid:
            _log_resp(resp, "create_fallback_no_id")
            raise RuntimeError("No task id in response (fallback)")
        return int(tid)
    _log_resp(resp, "create_fallback_failed")
    raise RuntimeError(f"Create task (fallback) failed: {resp.status_code}")


def create_task_for_employee(
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    last_summary: str | None,
) -> int:
    """
    Создаёт задачу для сотрудника, заполняя поля формы.
    Возвращает task_id.
    """
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    fields: List[Dict] = [
        {"id": FIELD_TG_ID,            "value": int(tg_chat_id)},
        {"id": FIELD_FULL_NAME,        "value": (full_name or "")},
        {"id": FIELD_TEAM_ID,          "value": int(team_id or 0)},
        {"id": FIELD_CONVERSATION_ID,  "value": (conversation_id or "")},
        {"id": FIELD_LAST_SUMMARY,     "value": (last_summary or "")},
    ]

    try:
        return _create_task_primary(fields)
    except Exception as e1:
        logger.warning(f"[Pyrus] create primary path failed: {e1}")
        return _create_task_fallback(fields)


# ---------- Обновление полей / комментарии ----------

def _update_fields_primary(task_id: int, fields: List[Dict]):
    """
    Вариант 1: POST /tasks/{id}/update
    """
    url = f"{BASE_URL}/tasks/{task_id}/update"
    payload = {"fields": fields}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        return
    _log_resp(resp, "update_primary_failed")
    raise RuntimeError(f"Update fields failed: {resp.status_code}")


def _update_fields_fallback(task_id: int, fields: List[Dict]):
    """
    Вариант 2: POST /tasks/{id}
    """
    url = f"{BASE_URL}/tasks/{task_id}"
    payload = {"fields": fields}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        return
    _log_resp(resp, "update_fallback_failed")
    raise RuntimeError(f"Update fields (fallback) failed: {resp.status_code}")


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

    fields: List[Dict] = [
        {"id": FIELD_TG_ID,            "value": int(tg_chat_id)},
        {"id": FIELD_FULL_NAME,        "value": (full_name or "")},
        {"id": FIELD_TEAM_ID,          "value": int(team_id or 0)},
        {"id": FIELD_CONVERSATION_ID,  "value": (conversation_id or "")},
        {"id": FIELD_LAST_SUMMARY,     "value": (last_summary or "")},
    ]
    try:
        _update_fields_primary(task_id, fields)
    except Exception as e1:
        logger.warning(f"[Pyrus] update primary failed: {e1}")
        _update_fields_fallback(task_id, fields)


def _comment_primary(task_id: int, text: str):
    """
    Вариант 1: POST /tasks/{id}/comments
    """
    url = f"{BASE_URL}/tasks/{task_id}/comments"
    payload = {"text": text}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        return
    _log_resp(resp, "comment_primary_failed")
    raise RuntimeError(f"Add comment failed: {resp.status_code}")


def _comment_fallback(task_id: int, text: str):
    """
    Вариант 2: POST /tasks/{id}/update с полем comment
    """
    url = f"{BASE_URL}/tasks/{task_id}/update"
    payload = {"comment": {"text": text}}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if resp.ok:
        return
    _log_resp(resp, "comment_fallback_failed")
    raise RuntimeError(f"Add comment (fallback) failed: {resp.status_code}")


def add_summary_comment(task_id: int, summary_text: str):
    if not enabled():
        raise RuntimeError("Pyrus not configured")
    try:
        _comment_primary(task_id, summary_text)
    except Exception as e1:
        logger.warning(f"[Pyrus] comment primary failed: {e1}")
        _comment_fallback(task_id, summary_text)


# ---------- Удобная обёртка «всё в одном» ----------

def upsert_summary_comment(
    tg_chat_id: int,
    full_name: str | None,
    team_id: int | None,
    conversation_id: str | None,
    summary_text: str,
) -> int:
    """
    Находит (или создаёт) персональную задачу сотрудника,
    обновляет поля формы (включая «Последнее саммари») и
    добавляет комментарий с текущим саммари.
    Возвращает task_id.
    """
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    # 1) найти задачу
    task_id = find_employee_task(tg_chat_id)

    # 2) если не нашли — создать
    if not task_id:
        task_id = create_task_for_employee(
            tg_chat_id=tg_chat_id,
            full_name=full_name,
            team_id=team_id,
            conversation_id=conversation_id,
            last_summary=summary_text,
        )
        logger.info(f"[Pyrus] task created: {task_id} for chat_id={tg_chat_id}")
    else:
        # 3) если нашли — обновить поля
        update_task_fields(
            task_id=task_id,
            tg_chat_id=tg_chat_id,
            full_name=full_name,
            team_id=team_id,
            conversation_id=conversation_id,
            last_summary=summary_text,
        )

    # 4) добавить комментарий
    add_summary_comment(task_id, summary_text)
    return task_id