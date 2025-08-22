# pyrus_client.py
import os
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger("pyrus")

BASE_URL = os.getenv("PYRUS_BASE_URL")
TOKEN = os.getenv("PYRUS_ACCESS_TOKEN")
FORM_ID = int(os.getenv("PYRUS_FORM_ID", "0") or 0)

FIELD_TG = int(os.getenv("PYRUS_FIELD_TG_CHAT_ID", "0") or 0)
FIELD_NAME = int(os.getenv("PYRUS_FIELD_FULL_NAME", "0") or 0)
FIELD_TEAM = int(os.getenv("PYRUS_FIELD_TEAM_ID", "0") or 0)
FIELD_CONV = int(os.getenv("PYRUS_FIELD_CONVERSATION_ID", "0") or 0)
FIELD_LAST_SUM = int(os.getenv("PYRUS_FIELD_LAST_SUMMARY", "0") or 0)

def enabled() -> bool:
    ok = bool(BASE_URL and TOKEN and FORM_ID and FIELD_TG and FIELD_NAME and FIELD_TEAM and FIELD_CONV and FIELD_LAST_SUM)
    if not ok:
        logger.warning("[Pyrus] not fully configured — integration disabled")
    return ok

def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def create_task_for_employee(tg_chat_id: int, full_name: str | None, team_id: int | None,
                             conversation_id: str | None, last_summary: str | None) -> int:
    """
    Создаёт новую задачу по форме и возвращает её task_id.
    """
    if not enabled():
        raise RuntimeError("Pyrus not configured")

    fields = [
        {"id": FIELD_TG, "value": tg_chat_id},
        {"id": FIELD_NAME, "value": full_name or ""},
        {"id": FIELD_TEAM, "value": team_id if team_id is not None else ""},
        {"id": FIELD_CONV, "value": conversation_id or ""},
        {"id": FIELD_LAST_SUM, "value": last_summary or ""},
    ]
    payload = {
        "form_id": FORM_ID,
        "fields": fields
    }
    url = f"{BASE_URL}/tasks"
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"[Pyrus] create task error {resp.status_code} {resp.text}")

    body = resp.json()
    task_id = body.get("task", {}).get("id")
    if not task_id:
        raise RuntimeError(f"[Pyrus] unexpected create response: {body}")
    return int(task_id)

def update_task_fields(task_id: int, tg_chat_id: int, full_name: str | None,
                       team_id: int | None, conversation_id: str | None, last_summary: str | None):
    """
    Обновляет поля карточки через комментарий.
    """
    if not enabled():
        return
    fields = [
        {"id": FIELD_TG, "value": tg_chat_id},
        {"id": FIELD_NAME, "value": full_name or ""},
        {"id": FIELD_TEAM, "value": team_id if team_id is not None else ""},
        {"id": FIELD_CONV, "value": conversation_id or ""},
        {"id": FIELD_LAST_SUM, "value": last_summary or ""},
    ]
    url = f"{BASE_URL}/tasks/{task_id}/comments"
    payload = {"fields": fields, "text": None}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"[Pyrus] update fields error {resp.status_code} {resp.text}")

def add_summary_comment(task_id: int, summary_text: str):
    """
    Добавляет комментарий с датой и саммари. Дату ставим в UTC (ты в отчётах используешь UTC).
    """
    if not enabled():
        return
    today = datetime.now(timezone.utc).date().isoformat()
    text = f"{today}\n\n{summary_text}"
    url = f"{BASE_URL}/tasks/{task_id}/comments"
    payload = {"text": text}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"[Pyrus] add comment error {resp.status_code} {resp.text}")