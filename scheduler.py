# scheduler.py

import schedule
import requests
import time
import json
import logging
from dotenv import dotenv_values
from datetime import datetime, timezone
from users import USERS, TEAMS

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")

QUESTION_TEXT_WEEKDAY = (
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

# Пн=0 … Вс=6
def today_wd() -> int:
    return datetime.now(timezone.utc).weekday()

def is_weekday() -> bool:
    return today_wd() < 5

def _question_text_today() -> str:
    return QUESTION_TEXT_MONDAY if today_wd() == 0 else QUESTION_TEXT_WEEKDAY

def _team_skip_today(team_id: int) -> bool:
    """
    Возвращает True, если сегодня для этой команды надо пропустить и вопросы, и отчёт.
    Команда #2 пропускается по вт (1) и чт (3).
    """
    if team_id == 2 and today_wd() in (1, 3):
        return True
    return False

def send_questions():
    if not is_weekday():
        logger.info("Сегодня выходной — рассылку вопросов пропускаем")
        return

    logger.info("📤 Рассылка вопросов сотрудникам…")

    # Очищаем бэкап-файл (отчёт будет пустой, если никто не ответил)
    try:
        with open("answers.json", "w", encoding="utf-8") as f:
            json.dump({}, f)
    except Exception as e:
        logger.warning(f"[FILE] answers.json clean warn: {e}")

    text = _question_text_today()

    for team_id, team_data in TEAMS.items():
        if _team_skip_today(team_id):
            logger.info(f"⏭ Команда {team_id}: сегодня вопросы не отправляем (день пропуска).")
            continue

        for chat_id, name in team_data["members"].items():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            try:
                resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
                if resp.ok:
                    logger.info(f"✅ Отправлен вопрос: {name} (team={team_id}, chat_id={chat_id})")
                else:
                    logger.error(f"❌ Ошибка отправки {name} ({chat_id}): {resp.status_code} {resp.text}")
            except Exception as e:
                logger.error(f"❌ Исключение при отправке {name} ({chat_id}): {e}")
            time.sleep(1)  # чтобы не спамить API

def _load_answers_backup() -> dict:
    try:
        with open("answers.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"[FILE] answers.json read warn: {e}")
        return {}

def build_digest(team_members: dict[int, str]) -> tuple[str, int, int]:
    answers = _load_answers_backup()
    total = len(team_members)
    responded = 0
    lines = ["📝 Статусы на отчётное время:\n"]

    for cid, name in team_members.items():
        entry = answers.get(str(cid))
        if entry:
            lines.append(f"— {name}:\n{entry.get('summary', '')}\n")
            responded += 1
        else:
            lines.append(f"— {name}:\n- (прочерк)\n")

    lines.append(f"Отчитались: {responded}/{total}")
    return "\n".join(lines), responded, total

def send_summary(team_id: int):
    if not is_weekday():
        logger.info(f"Сегодня выходной — отчёт команде {team_id} не отправляем")
        return
    if _team_skip_today(team_id):
        logger.info(f"⏭ Команда {team_id}: сегодня отчёт не отправляем (день пропуска).")
        return

    logger.info(f"📤 Формирование отчёта для команды {team_id}…")
    team_data = TEAMS[team_id]
    members = team_data["members"]

    digest, responded, total = build_digest(members)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    managers = team_data.get("managers") or [team_data.get("manager")]
    for manager_id in managers:
        try:
            resp = requests.post(url, json={"chat_id": manager_id, "text": digest}, timeout=20)
            if resp.ok:
                logger.info(f"✅ Отчёт отправлен менеджеру {manager_id} (команда {team_id}). Итог: {responded}/{total}")
            else:
                logger.error(f"❌ Ошибка отправки менеджеру {manager_id}: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"❌ Исключение при отправке менеджеру {manager_id}: {e}")

# --- Расписание (UTC) ---
schedule.every().monday.at("09:00").do(send_questions)
schedule.every().tuesday.at("09:00").do(send_questions)
schedule.every().wednesday.at("09:00").do(send_questions)
schedule.every().thursday.at("09:00").do(send_questions)
schedule.every().friday.at("09:00").do(send_questions)

schedule.every().monday.at("09:30").do(lambda: send_summary(1))
schedule.every().tuesday.at("09:30").do(lambda: send_summary(1))
schedule.every().wednesday.at("09:30").do(lambda: send_summary(1))
schedule.every().thursday.at("09:30").do(lambda: send_summary(1))
schedule.every().friday.at("09:30").do(lambda: send_summary(1))

schedule.every().monday.at("11:00").do(lambda: send_summary(2))
schedule.every().tuesday.at("11:00").do(lambda: send_summary(2))     # будет пропущен логикой
schedule.every().wednesday.at("11:00").do(lambda: send_summary(2))
schedule.every().thursday.at("11:00").do(lambda: send_summary(2))    # будет пропущен логикой
schedule.every().friday.at("11:00").do(lambda: send_summary(2))

logger.info("🕒 Планировщик запущен. Ожидаем задачи…")
while True:
    schedule.run_pending()
    time.sleep(30)