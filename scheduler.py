# === scheduler.py ===

import os
import json
import schedule
import time
from datetime import datetime, date, timedelta
import pytz
from dotenv import dotenv_values
from users import TEAMS
import requests

# Временная зона
MSK = pytz.timezone("Europe/Moscow")

# Загрузка переменных окружения
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

QUESTION_SETS = {
    "daily_start": [
        "Доброе утро! ☀️\n\nПожалуйста, ответьте на 3 вопроса:",
        "Что делал в пятницу?",
        "Что планируешь сегодня?",
        "Есть ли блокеры?",
    ],
    "daily_regular": [
        "Доброе утро! ☀️\n\nПожалуйста, ответьте на 3 вопроса:",
        "Что ты сделал вчера?",
        "Что планируешь сегодня?",
        "Есть ли блокеры?",
    ],
    "weekly": [
        "Привет! ☀️\n\nПожалуйста, ответьте на 3 вопроса:",
        "Что ты делал на этой неделе?",
        "Что планируешь делать на следующей?",
        "Есть ли блокеры?",
    ],
}

# ---------- Работа с answers.json ----------
def load_answers() -> dict:
    try:
        with open("answers.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_answers(data: dict):
    with open("answers.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_team_members(team_id: int):
    answers = load_answers()
    team = TEAMS.get(team_id, {})
    members = set(map(str, team.get("members", {}).keys()))
    for uid in list(answers.keys()):
        if uid in members:
            del answers[uid]
    save_answers(answers)

# ---------- Работа с датами ----------
def get_week_range_str(today: date) -> str:
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return f"{monday.strftime('%d.%m.%Y')} - {friday.strftime('%d.%m.%Y')}"

# ---------- Формирование отчёта ----------
def build_text_report(team_id: int) -> str:
    answers = load_answers()
    team = TEAMS.get(team_id)
    if not team:
        return "[!] Команда не найдена."

    if team_id in (3, 4):
        report_date = get_week_range_str(date.today())
    else:
        report_date = datetime.now(MSK).strftime("%Y-%m-%d")

    report_lines = [f"\U0001F4DD Отчёт по команде «{team['team_name']}» за {report_date}"]
    responded = 0
    total = len(team.get("members", {}))

    for user_id, full_name in team.get("members", {}).items():
        entry = answers.get(str(user_id))
        summary = entry.get("summary") if entry else "-"
        if summary != "-":
            responded += 1
        report_lines.append(f"\n👤 {full_name.strip()}\n{summary}")

    report_lines.append(f"\n📊 Отчитались: {responded}/{total}")
    return "\n".join(report_lines)

# ---------- Отправка сообщений ----------
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
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": header + part},
                timeout=20,
            )
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ Ошибка при отправке части {i+1} → {chat_id}: {e}")

def send_questions(team_id: int, key: str):
    team = TEAMS.get(team_id)
    if not team:
        return
    clear_team_members(team_id)
    text = "\n".join(QUESTION_SETS[key])
    print(f"📨 Команда {team_id}: рассылаем вопросы ({key})...")
    for user_id in team.get("members", {}):
        try:
            send_long_text(user_id, text)
        except Exception as e:
            print(f"⚠️ Ошибка при отправке → {user_id}: {e}")

def send_report(team_id: int):
    team = TEAMS.get(team_id)
    if not team:
        return
    text = build_text_report(team_id)
    for manager_id in team.get("managers", []):
        try:
            send_long_text(manager_id, text)
        except Exception as e:
            print(f"⚠️ Ошибка при отправке отчёта → {manager_id}: {e}")

# ---------- Расписание ----------
# Команда 1 (Daily)
schedule.every().monday.at("09:00").do(send_questions, team_id=1, key="daily_start")
schedule.every().tuesday.at("17:30").do(send_questions, team_id=1, key="daily_regular")
schedule.every().wednesday.at("09:00").do(send_questions, team_id=1, key="daily_regular")
schedule.every().thursday.at("09:00").do(send_questions, team_id=1, key="daily_regular")
schedule.every().friday.at("09:00").do(send_questions, team_id=1, key="daily_regular")

schedule.every().monday.at("09:30").do(send_report, team_id=1)
schedule.every().tuesday.at("17:32").do(send_report, team_id=1)
schedule.every().wednesday.at("09:30").do(send_report, team_id=1)
schedule.every().thursday.at("09:30").do(send_report, team_id=1)
schedule.every().friday.at("09:30").do(send_report, team_id=1)

# Команда 2 (Daily)
schedule.every().monday.at("09:00").do(send_questions, team_id=2, key="daily_start")
schedule.every().tuesday.at("09:00").do(send_questions, team_id=2, key="daily_regular")
schedule.every().wednesday.at("09:00").do(send_questions, team_id=2, key="daily_regular")
schedule.every().thursday.at("09:00").do(send_questions, team_id=2, key="daily_regular")
schedule.every().friday.at("09:00").do(send_questions, team_id=2, key="daily_regular")

schedule.every().monday.at("11:00").do(send_report, team_id=2)
schedule.every().tuesday.at("11:00").do(send_report, team_id=2)
schedule.every().wednesday.at("11:00").do(send_report, team_id=2)
schedule.every().thursday.at("11:00").do(send_report, team_id=2)
schedule.every().friday.at("11:00").do(send_report, team_id=2)

# Команда 3 (Weekly)
schedule.every().tuesday.at("17:30").do(send_questions, team_id=3, key="weekly")
schedule.every().tuesday.at("17:32").do(send_report, team_id=3)

# Команда 4 (Weekly)
schedule.every().thursday.at("09:00").do(send_questions, team_id=4, key="weekly")
schedule.every().thursday.at("16:00").do(send_report, team_id=4)

# ---------- Запуск ----------
print("🕒 Планировщик запущен. Ожидание задач...")
while True:
    schedule.run_pending()
    time.sleep(30)