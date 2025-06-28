import schedule
import requests
import time
import json
from dotenv import dotenv_values
from datetime import datetime

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

# Команды с сотрудниками
TEAMS = {
    1: {
        "members": {
            731869173: "Татьяна Воронкова",
            946740162: "Александр Зайцев",
            368455189: "Наталья Голощапова",
            949507228: "Марьяна Дмитриевская",
            220691670: "Алексей Хван"
        },
        "manager": 949507228  # ID руководителя команды 1
    },
    2: {
        "members": {
            1010954244: "Константин Базаркин",
            398995895: "Антон Баронин",
            1038645944: "Андрей Часов",
            253240597: "Дмитрий Малютин"
        },
        "manager": 949507228  # Пока тот же руководитель для теста
    }
}

QUESTION_TEXT = (
    "Доброе утро! ☀️\n\n"
    "Пожалуйста, ответьте на 3 вопроса:\n"
    "1. Что делали вчера?\n"
    "2. Что планируете сегодня?\n"
    "3. Есть ли риски или блокеры?"
)

def is_weekday():
    # 0 - понедельник, ..., 6 - воскресенье
    return datetime.today().weekday() < 5

def send_questions():
    if not is_weekday():
        print("Сегодня выходной, вопросы не рассылаем")
        return

    print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] Рассылка вопросов сотрудникам...")
    # Перед рассылкой очищаем файл с ответами
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

    lines = ["📝 Статусы на 12:00:\n"]
    for chat_id, data in answers.items():
        # Отображать только если сотрудник в команде
        if chat_id in team_members:
            name = team_members[chat_id]
            summary = data.get("summary", "")
            lines.append(f"— {name}:\n{summary}\n")
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

# Планируем рассылку в 10:00 и отчёты в 12:00
schedule.every().monday.at("10:00").do(send_questions)
schedule.every().tuesday.at("10:00").do(send_questions)
schedule.every().wednesday.at("10:00").do(send_questions)
schedule.every().thursday.at("10:00").do(send_questions)
schedule.every().friday.at("10:00").do(send_questions)

schedule.every().monday.at("12:00").do(send_summary)
schedule.every().tuesday.at("12:00").do(send_summary)
schedule.every().wednesday.at("12:00").do(send_summary)
schedule.every().thursday.at("12:00").do(send_summary)
schedule.every().friday.at("12:00").do(send_summary)

print("🕒 Планировщик запущен. Ожидаем задач...")

while True:
    schedule.run_pending()
    time.sleep(30)