# main.py — Telegram bot (VK Teams logic port)

from flask import Flask, request
import requests
from dotenv import dotenv_values
import json
import logging
import re
from datetime import date

from users import USERS, TEAMS

# ---------- logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

# ---------- env ----------
env = dotenv_values(".env")
TELEGRAM_TOKEN = env["TELEGRAM_TOKEN"]
DIFY_API_URL = env["DIFY_API_URL"].rstrip("/")
DIFY_API_KEY_DAILY = env["DIFY_API_KEY_DAILY"]
DIFY_API_KEY_WEEKLY = env["DIFY_API_KEY_WEEKLY"]

app = Flask(__name__)

conversation_ids: dict[int, str] = {}
last_date: dict[int, str] = {}

# ---------- confirmations ----------
CONFIRMATION_PHRASES = {
    "да", "да все верно", "да, все верно", "все верно", "всё верно",
    "подтверждаю", "подтверждаю все", "подтверждаю вариант",
    "все так", "всё так", "ок", "окей", "ага", "точно", "верно",
    "готов", "готова", "готово", "да, подтверждаю", "да, отправляй",
    "да, можно отправлять", "все правильно", "всё правильно",
    "абсолютно", "правильно", "так и есть", "да-да",
    "все супер", "всё супер", "супер", "хорошо", "отлично",
    "всё четко", "все четко", "четко", "ясно",
}
CONFIRM_STRIP_RE = re.compile(r"[^\w\sёЁ]+", re.UNICODE)

def normalize_confirmation(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = CONFIRM_STRIP_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()

def is_confirmation(text: str) -> bool:
    return normalize_confirmation(text) in CONFIRMATION_PHRASES

# ---------- helpers ----------
def find_team_id(chat_id: int) -> int | None:
    for team_id, team in TEAMS.items():
        if chat_id in team["members"]:
            return team_id
    return None

def get_dify_headers(team_id: int) -> dict:
    api_key = DIFY_API_KEY_WEEKLY if team_id in (3, 4) else DIFY_API_KEY_DAILY
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

def dify_get_conversation_id(chat_id: int, headers: dict) -> str | None:
    try:
        r = requests.get(
            f"{DIFY_API_URL}/conversations",
            headers=headers,
            params={"user": str(chat_id)},
            timeout=20,
        )
        if r.ok:
            items = r.json().get("data") or []
            if items:
                return items[0]["id"]
    except Exception as e:
        logger.error(f"[Dify] get_conversation_id error: {e}")
    return None

def dify_send_message(chat_id: int, text: str, headers: dict, conversation_id: str | None = None):
    payload = {
        "query": text,
        "inputs": {},
        "response_mode": "blocking",
        "user": str(chat_id),
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = requests.post(
        f"{DIFY_API_URL}/chat-messages",
        headers=headers,
        json=payload,
        timeout=60,
    )
    logger.info(f"[Dify] status={resp.status_code} body={resp.text[:1000]}")
    return resp

def send_long_text(chat_id: int, text: str, chunk_size: int = 1000):
    chunks = []
    while text:
        part = text[:chunk_size]
        last_nl = part.rfind("\n")
        if last_nl > 0 and len(text) > chunk_size:
            part = text[:last_nl]
        chunks.append(part.strip())
        text = text[len(part):].lstrip()

    for i, part in enumerate(chunks):
        header = f"(Часть {i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": header + part},
            timeout=20,
        )

# ---------- webhook ----------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    logger.info("Webhook:\n%s", json.dumps(data, ensure_ascii=False, indent=2))

    if "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    user_name = USERS.get(chat_id, "Неизвестный")

    team_id = find_team_id(chat_id)
    if not team_id:
        logger.warning(f"User {chat_id} not in TEAMS")
        return "ok"

    today = date.today().isoformat()
    if last_date.get(chat_id) != today:
        conversation_ids.pop(chat_id, None)
        last_date[chat_id] = today

    headers = get_dify_headers(team_id)
    conv_id = conversation_ids.get(chat_id)

    if not conv_id:
        conv_id = dify_get_conversation_id(chat_id, headers)
        if conv_id:
            conversation_ids[chat_id] = conv_id

    resp = dify_send_message(chat_id, user_text, headers, conv_id)

    if resp.status_code == 400:
        resp = dify_send_message(chat_id, user_text, headers)

    if resp.ok:
        body = resp.json()
        answer = body.get("answer", "") or ""
        new_conv = body.get("conversation_id")
        if new_conv:
            conversation_ids[chat_id] = new_conv

        if is_confirmation(user_text) and "sum" in answer.lower():
            try:
                with open("answers.json", "r", encoding="utf-8") as f:
                    answers = json.load(f)
            except Exception:
                answers = {}

            answers[str(chat_id)] = {
                "name": user_name,
                "summary": answer,
                "date": today,
                "team_id": team_id,
            }

            with open("answers.json", "w", encoding="utf-8") as f:
                json.dump(answers, f, ensure_ascii=False, indent=2)

            reply = "✅ Спасибо! Отчёт сохранён."
        else:
            reply = answer
    else:
        reply = "⚠️ Ошибка при обращении к Dify"

    send_long_text(chat_id, reply)
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)