import schedule
import requests
import time
import json
import logging
from dotenv import dotenv_values
from datetime import datetime
from users import USERS, TEAMS  # Импортируем USERS и TEAMS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

QUESTION_TEXT_DEFAULT = (
    "Доброе утро! ☀️\n\n"
    "Пожалуйста, ответьте на 3 вопроса:\n"
    "1. Что делали вчера?\n"
    "2. Что планируете сегодня?\n"
    "3. Есть ли блокеры?"
)

QUESTION_TEXT_MONDAY = (
    "Доброе утро! ☀️\n\n"
    "Пожалуйста, ответьте на 3 вопроса:\n"
    "1. Что делали в пятницу?\n"
    "2. Что планируете сегодня?\n"
    "3. Есть ли блокеры?"
)

def is_weekday():
    return datetime.today().weekday() < 5  # Пн=0 ... Вс=6

def send_questions():
    if not is_weekday():
        logger.info("Сегодня выходной, вопросы не рассылаем")
        return

    # Определяем текст вопроса в зависимости от дня недели
    today_weekday = datetime.today().weekday()
    if today_weekday == 0:  # Понедельник
        question_text = QUESTION_TEXT_MONDAY
    else:
        question_text = QUESTION_TEXT_DEFAULT

    logger.info("📤 Рассылка вопросов сотрудникам...")
    # Очищаем файл перед рассылкой
    with open("answers.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    for team_id, team_data in TEAMS.items():
        for chat_id, name in team_data["members"].items():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            try:
                response = requests.post(url, json={"chat_id": chat_id, "text": question_text})
                if response.ok:
                    logger.info(f"✅ Вопрос отправлен: {name} (chat_id={chat_id})")
                else:
                    logger.error(f"❌ Ошибка отправки вопроса {name} (chat_id={chat_id}): {response.status_code} {response.text}")
            except Exception as e:
                logger.error(f"❌ Исключение при отправке вопроса {name} (chat_id={chat_id}): {e}")

            time.sleep(1)  # Задержка 1 секунда между отправками

def load_answers():
    try:
        with open("answers.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def build_digest(answers, team_members):
    if not answers:
        return "⚠️ Пока нет ответов от сотрудников."

    lines = ["📝 Статусы на отчётное время:\n"]
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

def send_summary(team_id):
    if not is_weekday():
        logger.info(f"Сегодня выходной, отчёты команде {team_id} не отправляем")
        return

    logger.info(f"📤 Отправка отчётов руководителю команды {team_id}...")
    answers = load_answers()

    team_data = TEAMS[team_id]
    digest = build_digest(answers, team_data["members"])

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    managers = team_data.get("managers") or [team_data.get("manager")]
    for manager_id in managers:
        try:
            response = requests.post(url, json={"chat_id": manager_id, "text": digest})
            if response.ok:
                logger.info(f"✅ Отчёт отправлен менеджеру {manager_id} команды {team_id}")
            else:
                logger.error(f"❌ Ошибка отправки отчёта менеджеру {manager_id}: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"❌ Исключение при отправке отчёта менеджеру {manager_id}: {e}")

# Рассылка вопросов для обеих команд в 09:00
schedule.every().monday.at("09:00").do(send_questions)
schedule.every().tuesday.at("09:00").do(send_questions)
schedule.every().wednesday.at("09:00").do(send_questions)
schedule.every().thursday.at("09:00").do(send_questions)
schedule.every().friday.at("09:00").do(send_questions)

# Отчёт команде 1 в 09:30
schedule.every().monday.at("09:30").do(lambda: send_summary(1))
schedule.every().tuesday.at("09:30").do(lambda: send_summary(1))
schedule.every().wednesday.at("09:30").do(lambda: send_summary(1))
schedule.every().thursday.at("09:30").do(lambda: send_summary(1))
schedule.every().friday.at("09:30").do(lambda: send_summary(1))

# Отчёт команде 2 в 11:00
schedule.every().monday.at("11:00").do(lambda: send_summary(2))
schedule.every().tuesday.at("11:00").do(lambda: send_summary(2))
schedule.every().wednesday.at("11:00").do(lambda: send_summary(2))
schedule.every().thursday.at("11:00").do(lambda: send_summary(2))
schedule.every().friday.at("11:00").do(lambda: send_summary(2))

logger.info("🕒 Планировщик запущен. Ожидаем задач...")

while True:
    schedule.run_pending()
    time.sleep(30)