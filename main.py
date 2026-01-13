# main.py
from flask import Flask, request
import requests
from dotenv import dotenv_values
import json
import logging
import re

from users import USERS, TEAMS

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

# ---------- Конфиг ----------
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = (env.get("DIFY_API_URL") or "").rstrip('/')

app = Flask(__name__)

conversation_ids = {}

# ---------- Подтверждение ----------
CONFIRMATION_PHRASES = {
    "да", "да все верно", "да, все верно", "все верно", "всё верно",
    "подтверждаю", "все так", "ок", "окей", "ага", "готов",
    "да, отправляй", "всё правильно", "супер", "отлично"
}
CONFIRM_STRIP_RE = re.compile(r"[^\w\sёЁ]+", re.UNICODE)

def normalize_confirmation(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = CONFIRM_STRIP_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()

def is_confirmation(text: str) -> bool:
    return normalize_confirmation(text) in CONFIRMATION_PHRASES

# ---------- Вспомогалки ----------
def get_conversation_id(chat_id: int):
    try:
        r = requests.get(
            f"{DIFY_API_URL}/conversations",
            headers={"Authorization": f"Bearer {DIFY_API_KEY}"},
            params={"user": str(chat_id)},
            timeout=20,
        )
        if r.ok:
            data = r.json().get("data") or []
            if data:
                return data[0]["id"]
    except Exception as e:
        logger.error(e)
    return None

def send_to_dify(payload: dict):
    return requests.post(
        f"{DIFY_API_URL}/chat-messages",
        headers={
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

def clean_summary(text: str) -> str:
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if "sum" in line.lower():
            return "\n".join(lines[i + 1 :]).strip()
    return text.strip()

# ---------- Webhook ----------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}

    if "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")
    user_name = USERS.get(chat_id, "Неизвестный")

    conv_id = conversation_ids.get(chat_id) or get_conversation_id(chat_id)
    if conv_id:
        conversation_ids[chat_id] = conv_id

    payload = {
        "query": text,
        "response_mode": "blocking",
        "user": str(chat_id),
    }
    if conv_id:
        payload["conversation_id"] = conv_id

    response = send_to_dify(payload)

    if not response.ok:
        reply = "⚠️ Ошибка Dify"
    else:
        body = response.json()
        answer = body.get("answer", "")

        if is_confirmation(text) and "sum" in answer.lower():
            summary = clean_summary(answer)

            try:
                with open("answers.json", "r", encoding="utf-8") as f:
                    answers = json.load(f)
            except FileNotFoundError:
                answers = {}

            answers[str(chat_id)] = {
                "name": user_name,
                "summary": summary,
            }

            with open("answers.json", "w", encoding="utf-8") as f:
                json.dump(answers, f, ensure_ascii=False, indent=2)

            reply = "✅ Отчёт принят"
        else:
            reply = answer

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": reply},
        timeout=20,
    )

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)