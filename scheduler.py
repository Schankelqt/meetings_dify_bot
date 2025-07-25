import schedule
import requests
import time
import json
from dotenv import dotenv_values
from datetime import datetime
from users import USERS, TEAMS  # Импортируем USERS и TEAMS

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

QUESTION_TEXT = (
    "Доброе утро! ☀️\n\n"
    "Пожалуйста, ответьте на 3 вопроса:\n"
    "1. Что делали вчера?\n"
    "2. Что планируете сегодня?\n"
    "3. Есть ли блокеры?"
)

def is_weekday():
    return datetime.today().weekday() < 5  # Пн=0 ... Вс=6

def send_questions():
    if not is_weekday():
        print("Сегодня выходной, вопросы не рассылаем")
        return

    print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] Рассылка вопросов сотрудникам...")
    with open("answers.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    for team_id, team_data in TEAMS.items():
        for chat_id, name in team_data["members"].items():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": QUESTION_TEXT})
            print(f"✅ Вопрос отправлен: {name}")

def load_answers():
    try:
        with open("answers.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def build_digest(answers, team_members):
    if not answers:
        return "⚠️ Пока нет ответов от сотрудников."

    lines = ["📝 Статусы на 12:30:\n"]
    total = len(team_members)
    responded = 0

    for chat_id, name in team_members.items():
        if str(chat_id) in answers:
            summary = answers[str(chat_id)].get("summary", "")
            lines.append(f"— {name}:\n{summary}\n")
            responded += 1
        else:
            lines.append(f"— {name}:\n- (прочерк)\n")

    lines.append(f"Отчитались: {responded}/{total}")

    return "\n".join(lines)

def send_summary():
    if not is_weekday():
        print("Сегодня выходной, отчёты не отправляем")
        return

    print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] Отправка отчётов руководителям...")
    answers = load_answers()

    for team_id, team_data in TEAMS.items():
        digest = build_digest(answers, team_data["members"])
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": team_data["manager"], "text": digest})
        print(f"✅ Отчёт отправлен руководителю команды {team_id}")

schedule.every().monday.at("10:00").do(send_questions)
schedule.every().tuesday.at("10:00").do(send_questions)
schedule.every().wednesday.at("10:00").do(send_questions)
schedule.every().thursday.at("10:00").do(send_questions)
schedule.every().friday.at("12:30").do(send_questions)

schedule.every().monday.at("12:00").do(send_summary)
schedule.every().tuesday.at("12:00").do(send_summary)
schedule.every().wednesday.at("12:00").do(send_summary)
schedule.every().thursday.at("12:00").do(send_summary)
schedule.every().friday.at("12:40").do(send_summary)

print("🕒 Планировщик запущен. Ожидаем задач...")

while True:
    schedule.run_pending()
    time.sleep(30)