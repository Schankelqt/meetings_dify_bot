# pyrus_client.py
import os
import logging
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv

logger = logging.getLogger("pyrus")

# загружаем .env (чтобы работало под systemd так же, как в консоли)
load_dotenv()

BASE_URL = (os.getenv("PYRUS_BASE_URL") or "").rstrip("/")
TOKEN = os.getenv("PYRUS_ACCESS_TOKEN") or ""
FORM_ID_RAW = os.getenv("PYRUS_FORM_ID") or ""

try:
    FORM_ID = int(FORM_ID_RAW) if FORM_ID_RAW else 0
except ValueError:
    logger.error(f"[Pyrus] PYRUS_FORM_ID has invalid value: {FORM_ID_RAW!r}")
    FORM_ID = 0

SESSION = requests.Session()
if TOKEN:
    SESSION.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})

def configured(verbose: bool = False) -> bool:
    ok = True
    if not BASE_URL:
        ok = False
        if verbose: logger.error("[Pyrus] PYRUS_BASE_URL is empty")
    if not TOKEN:
        ok = False
        if verbose: logger.error("[Pyrus] PYRUS_ACCESS_TOKEN is empty")
    if not FORM_ID:
        ok = False
        if verbose: logger.error("[Pyrus] PYRUS_FORM_ID is empty or invalid")
    return ok

def _url(path: str) -> str:
    return f"{BASE_URL}{path}"

def get_form_fields() -> List[Dict[str, Any]]:
    """Вернёт список полей формы (для отладки/получения id)."""
    if not configured(True):
        raise RuntimeError("Pyrus not configured")
    resp = SESSION.get(_url(f"/forms/{FORM_ID}"), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("fields", []) or []

def _find_or_create_employee_task(tg_chat_id: int, full_name: Optional[str]) -> int:
    """
    Ищем «персональную» задачу сотрудника по Telegram Chat ID.
    Если не нашли — создаём новую задачу формы.
    Возвращает task_id.
    """
    if not configured(True):
        raise RuntimeError("Pyrus not configured")

    # Пытаемся найти по поиску — запросом по тексту chat_id
    q = str(tg_chat_id)
    try:
        sr = SESSION.get(_url(f"/tasks/search"), params={"text": q, "form_id": FORM_ID}, timeout=30)
        sr.raise_for_status()
        items = sr.json().get("tasks", []) or []
        if items:
            return int(items[0]["task_id"])
    except Exception as e:
        logger.warning(f"[Pyrus] search error: {e}")

    # Создаём новую задачу в форме. В названии кладём ФИО и chat_id.
    title = f"{full_name or 'Сотрудник'} — {tg_chat_id}"
    payload = {
        "form_id": FORM_ID,
        "subject": title,
        # можно проставить поле "Telegram Chat ID" если оно существует — попробуем найти
        "fields": []
    }

    try:
        # Попробуем найти id поля "Telegram Chat ID" и заполнить его
        fields = get_form_fields()
        chat_field_id = next((f["id"] for f in fields if (f.get("name") or "").strip().lower() == "telegram chat id"), None)
        if chat_field_id:
            payload["fields"].append({"id": chat_field_id, "value": tg_chat_id})
    except Exception as e:
        logger.warning(f"[Pyrus] cannot prefill fields on create: {e}")

    cr = SESSION.post(_url("/tasks/create"), json=payload, timeout=30)
    cr.raise_for_status()
    task = cr.json()
    task_id = int(task["task_id"])
    return task_id

def upsert_summary_comment(tg_chat_id: int,
                           full_name: Optional[str],
                           team_id: Optional[int],
                           conversation_id: Optional[str],
                           summary_text: str) -> int:
    """
    Находит/создаёт задачу сотрудника и добавляет комментарий с саммари.
    Параллельно пытается обновить поля формы (если найдены соответствующие поля).
    Возвращает task_id.
    """
    if not configured(True):
        logger.warning("[Pyrus] not fully configured — integration disabled")
        return -1

    task_id = _find_or_create_employee_task(tg_chat_id, full_name)

    # Попробуем собрать обновление полей (если такие поля есть в форме)
    fields_update = []
    try:
        fields = get_form_fields()
        by_name = { (f.get("name") or "").strip().lower(): f["id"] for f in fields }

        if "telegram chat id" in by_name:
            fields_update.append({"id": by_name["telegram chat id"], "value": tg_chat_id})
        if "фио сотрудника" in by_name and full_name:
            fields_update.append({"id": by_name["фио сотрудника"], "value": full_name})
        if "team_id" in by_name and team_id is not None:
            fields_update.append({"id": by_name["team_id"], "value": team_id})
        if "conversation_id" in by_name and conversation_id:
            fields_update.append({"id": by_name["conversation_id"], "value": conversation_id})
        if "последнее саммари" in by_name and summary_text:
            fields_update.append({"id": by_name["последнее саммари"], "value": summary_text})
    except Exception as e:
        logger.warning(f"[Pyrus] cannot build fields update: {e}")

    comment_text = (
        f"*Ежедневное саммари*\n\n"
        f"{summary_text}"
    )

    payload = {
        "task_id": task_id,
        "text": comment_text,
        "fields": fields_update or None
    }

    rr = SESSION.post(_url("/tasks/comment"), json=payload, timeout=30)
    rr.raise_for_status()
    logger.info(f"[Pyrus] summary posted to task {task_id}")
    return task_id