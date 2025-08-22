# main.py
from flask import Flask, request
import requests
from dotenv import dotenv_values
import json
import logging
import re

from users import USERS, TEAMS
import db
import pyrus_client as pyrus

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

# ---------- Конфиг ----------
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = (env.get("DIFY_API_URL") or "").rstrip('/')

app = Flask(__name__)

# кеш conversation_id в памяти процесса
conversation_ids = {}

# ---------- Подтверждение ----------
CONFIRMATION_PHRASES = {
    "да", "да все верно", "да, все верно", "все верно", "всё верно",
    "подтверждаю", "подтверждаю все", "подтверждаю вариант",
    "все так", "всё так", "ок", "окей", "ага", "точно", "верно",
    "готов", "готова", "готово", "да, подтверждаю", "да, отправляй",
    "да, можно отправлять", "все правильно", "всё правильно",
    "абсолютно", "правильно", "так и есть", "да-да", "все супер",
    "всё супер", "супер", "хорошо", "отлично", "всё четко", "все четко",
    "четко", "ясно"
}
CONFIRM_STRIP_RE = re.compile(r"[^\w\sёЁ]+", re.UNICODE)

def normalize_confirmation(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("ё", "е")
    s = CONFIRM_STRIP_RE.sub("", s)      # убрали пунктуацию/эмодзи
    s = re.sub(r"\s+", " ", s).strip()   # сжали пробелы
    return s

def is_confirmation(user_text: str) -> bool:
    return normalize_confirmation(user_text) in CONFIRMATION_PHRASES

# ---------- Вспомогалки ----------
def find_team_id(chat_id: int) -> int | None:
    for team_id, team_data in TEAMS.items():
        if chat_id in team_data["members"]:
            return team_id
    return None

def clean_summary(answer_text: str) -> str:
    """
    Удаляем ВСЁ, что выше первой строки, содержащей 'sum' (без учёта регистра),
    и саму строку с 'sum' тоже — сохраняем только чистое саммари.
    """
    lines = (answer_text or "").splitlines()
    for i, line in enumerate(lines):
        if "sum" in line.lower():
            return "\n".join(lines[i+1:]).strip()
    return (answer_text or "").strip()

def get_conversation_id(chat_id: int) -> str | None:
    url = f"{DIFY_API_URL}/conversations"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}"}
    params = {"user": str(chat_id)}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[Dify] get_conversation_id for {chat_id}: {data}")
        items = data.get("data") or []
        if items:
            return items[0]["id"]
    except Exception as e:
        logger.error(f"[Dify] get_conversation_id error for {chat_id}: {e}")
    return None

def send_to_dify(payload: dict) -> requests.Response | None:
    try:
        url = f"{DIFY_API_URL}/chat-messages"
        headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        logger.info(f"[Dify] status={resp.status_code} body={resp.text[:2000]}")
        return resp
    except Exception as e:
        logger.error(f"[Dify] request error: {e}")
        return None

# ---------- Хендлер ----------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    logger.info(f"✅ Webhook data: {data}")

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]
        user_name = USERS.get(chat_id, "Неизвестный")

        # conversation_id для Dify
        conv_id = conversation_ids.get(chat_id)
        if not conv_id:
            conv_id = get_conversation_id(chat_id)
            if conv_id:
                conversation_ids[chat_id] = conv_id
            else:
                logger.info(f"[Dify] no conversation for {chat_id}, will create a new one")

        payload = {
            "inputs": {},
            "query": user_message,
            "response_mode": "blocking",
            "user": str(chat_id)
        }
        if conv_id:
            payload["conversation_id"] = conv_id

        response = send_to_dify(payload)

        # если Dify вернул 404 — пробуем без conversation_id (создаст новую)
        if response is not None and response.status_code == 404:
            logger.info(f"[Dify] conversation {conv_id} not exists. retry without conv_id")
            payload.pop("conversation_id", None)
            response = send_to_dify(payload)
            try:
                if response is not None and response.ok:
                    new_conv = response.json().get("conversation_id")
                    if new_conv:
                        conversation_ids[chat_id] = new_conv
                        logger.info(f"[Dify] new conversation_id={new_conv} for {chat_id}")
            except Exception:
                pass

        # формируем ответ пользователю и при необходимости — сохраняем "финал"
        if response is not None and response.ok:
            body = response.json()
            answer_text = body.get("answer", "") or ""

            if is_confirmation(user_message) and ("sum" in answer_text.lower()):
                summary = clean_summary(answer_text)

                # --- БД (финальная запись, одна на день) ---
                if db.enabled():
                    try:
                        team_id = find_team_id(chat_id)
                        db.upsert_employee(chat_id, user_name, team_id)
                        db.insert_summary(
                            tg_chat_id=chat_id,
                            full_name=user_name,
                            team_id=team_id,
                            conversation_id=body.get("conversation_id") or conversation_ids.get(chat_id),
                            summary_text=summary
                        )
                        logger.info(f"[DB] final summary saved for {chat_id}")
                    except Exception as e:
                        logger.error(f"[DB] save summary error: {e}")

                # --- Pyrus (создать один раз, дальше обновлять; БЕЗ поиска) ---
                try:
                    if pyrus.enabled():
                        team_id = find_team_id(chat_id)

                        # берём task_id из нашей БД
                        task_id = db.get_pyrus_task_id(chat_id) if db.enabled() else None

                        # если нет — создадим и запишем
                        if not task_id:
                            task_id = pyrus.create_task_for_employee(
                                tg_chat_id=chat_id,
                                full_name=user_name,
                                team_id=team_id,
                                conversation_id=body.get("conversation_id") or conversation_ids.get(chat_id),
                                last_summary=summary
                            )
                            logger.info(f"[Pyrus] task created: {task_id} for chat_id={chat_id}")
                            if db.enabled():
                                db.upsert_pyrus_task_id(chat_id, task_id)
                        else:
                            # если есть — просто обновим поля
                            pyrus.update_task_fields(
                                task_id=task_id,
                                tg_chat_id=chat_id,
                                full_name=user_name,
                                team_id=team_id,
                                conversation_id=body.get("conversation_id") or conversation_ids.get(chat_id),
                                last_summary=summary
                            )

                        # комментарий с саммари на текущий день (ежедневный лог)
                        pyrus.add_summary_comment(task_id, summary)
                        logger.info(f"[Pyrus] synced task_id={task_id} for chat_id={chat_id}")
                except Exception as e:
                    logger.error(f"[Pyrus] push error: {e}")

                # --- JSON-бэкап (опционально) ---
                try:
                    try:
                        with open("answers.json", "r", encoding="utf-8") as f:
                            answers = json.load(f)
                    except FileNotFoundError:
                        answers = {}
                    answers[str(chat_id)] = {"name": user_name, "summary": summary}
                    with open("answers.json", "w", encoding="utf-8") as f:
                        json.dump(answers, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"[FILE] answers.json write error: {e}")

                reply = "✅ Спасибо! Отчёт сохранён и будет отправлен руководителю."
            else:
                # не финал — просто отдаём ответ Dify пользователю
                reply = answer_text
        else:
            reply = f"⚠️ Ошибка при обращении к Dify: {response.status_code if response else 'нет ответа'}"

        # отправка в Telegram
        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            tg_resp = requests.post(send_url, json={"chat_id": chat_id, "text": reply}, timeout=20)
            logger.info(f"[TG] status={tg_resp.status_code} resp={tg_resp.text[:500]}")
            tg_resp.raise_for_status()
        except Exception as e:
            logger.error(f"[TG] send error: {e}")

    return "ok"

@app.route("/test", methods=["POST"])
def test_route():
    logger.info("📨 /test called")
    _ = request.get_json(silent=True)
    return "OK"

if __name__ == "__main__":
    logger.info("Flask dev server starting…")
    app.run(host="0.0.0.0", port=5001)