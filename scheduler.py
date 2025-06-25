import schedule
import requests
import time
import json
from dotenv import dotenv_values
from datetime import datetime

# 🔐 Загружаем переменные окружения
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

# 📍 Чат-ID сотрудников
USERS = {
    775766895: "Кирилл Востриков"
}

# 📍 Чат-ID руководителя
MANAGER_ID = 775766895

# 🕘 Текст вопроса
QUESTION_TEXT = (
    "Доброе утро! ☀️\n\n"
    "Пожалуйста, ответьте на 3 вопроса:\n"
    "1. Что делали вчера?\n"
    "2. Что планируете сегодня?\n"
    "3. Есть ли риски или блокеры?"
)

# ✅ Рассылка вопросов и очистка answers.json
def send_questions():
    print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] Рассылка вопросов сотрудникам...")

    # Очистка файла
    with open("answers.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    for chat_id, name in USERS.items():
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": chat_id, "text": QUESTION_TEXT})
        print(f"✅ Вопрос отправлен: {name}")

# 📥 Загрузка ответов
def load_answers():
    try:
        with open("answers.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# 📊 Сбор и форматирование отчёта
def build_digest(answers):
    if not answers:
        return "⚠️ Пока нет ответов от сотрудников."

    lines = ["📝 Статусы на 9:30:\n"]
    for chat_id, data in answers.items():
        lines.append(f"— {data['name']}:\n{data['summary']}\n")
    return "\n".join(lines)

# 📤 Отправка отчёта руководителю
def send_summary():
    print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] Отправка отчёта руководителю...")
    answers = load_answers()
    digest = build_digest(answers)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": MANAGER_ID, "text": digest})
    print("✅ Отчёт отправлен")

# ⏰ Планирование
schedule.every().day.at("17:30").do(send_questions)
schedule.every().day.at("17:32").do(send_summary)

print("🕒 Единый планировщик запущен. Ожидаем задачи...")

while True:
    schedule.run_pending()
    time.sleep(30)