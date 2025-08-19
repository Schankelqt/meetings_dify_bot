import schedule
import requests
import time
import json
import logging
from dotenv import dotenv_values
from datetime import datetime, timezone
from users import USERS, TEAMS
import db

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
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

def is_weekday() -> bool:
    # Пн=0 … Вс=6
    return datetime.now(timezone.utc).weekday() < 5

def _question_text_today() -> str:
    # Пн — про пятницу, в остальные дни — про вчера
    return QUESTION_TEXT_MONDAY if datetime.now(timezone.utc).weekday() == 0 else QUESTION_TEXT_WEEKDAY

def send_questions():
    if not is_weekday():
        logger.info("Сегодня выходной — рассылку вопросов пропускаем")
        return

    logger.info("📤 Рассылка вопросов сотрудникам…")

    # Очищаем бэкап-файл (не влияет на БД)
    try:
        with open("answers.json", "w", encoding="utf-8") as f:
            json.dump({}, f)
    except Exception as e:
        logger.warning(f"[FILE] answers.json clean warn: {e}")

    text = _question_text_today()

    for team_id, team_data in TEAMS.items():
        for chat_id, name in team_data["members"].items():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            try:
                resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
                if resp.ok:
                    logger.info(f"✅ Отправлен вопрос: {name} (chat_id={chat_id})")
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

def build_digest_from_db(team_members: dict[int, str]) -> tuple[str, int, int]:
    """
    Диgest по БД за сегодня (UTC). Берём по одному последнему саммари на сотрудника.
    Возвращает (текст, responded, total)
    """
    total = len(team_members)
    responded = 0
    lines = ["📝 Статусы на отчётное время:\n"]

    if not db.enabled():
        # fallback — файл
        answers = _load_answers_backup()
        for cid, name in team_members.items():
            entry = answers.get(str(cid))
            if entry:
                lines.append(f"— {name}:\n{entry.get('summary','')}\n")
                responded += 1
            else:
                lines.append(f"— {name}:\n- (прочерк)\n")
        return "\n".join(lines + [f"Отчитались: {responded}/{total}"]), responded, total

    # БД-ветка
    try:
        summaries = db.fetch_today_summaries(list(team_members.keys()))
        # summaries: dict[chat_id] = summary_text
        for cid, name in team_members.items():
            if cid in summaries:
                lines.append(f"— {name}:\n{summaries[cid]}\n")
                responded += 1
            else:
                lines.append(f"— {name}:\n- (прочерк)\n")
    except Exception as e:
        logger.error(f"[DB] fetch summaries error: {e}")
        # на всякий случай — fallback на файл
        answers = _load_answers_backup()
        for cid, name in team_members.items():
            entry = answers.get(str(cid))
            if entry:
                lines.append(f"— {name}:\n{entry.get('summary','')}\n")
                responded += 1
            else:
                lines.append(f"— {name}:\n- (прочерк)\n")

    lines.append(f"Отчитались: {responded}/{total}")
    return "\n".join(lines), responded, total

def send_summary(team_id: int):
    if not is_weekday():
        logger.info(f"Сегодня выходной — отчёт команде {team_id} не отправляем")
        return

    logger.info(f"📤 Формирование отчёта для команды {team_id}…")
    team_data = TEAMS[team_id]
    members = team_data["members"]

    digest, responded, total = build_digest_from_db(members)

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

# --- Расписание (оставляю как у тебя; время — по серверному UTC) ---
schedule.every().monday.at("09:00").do(send_questions)
schedule.every().tuesday.at("14:10").do(send_questions)
schedule.every().wednesday.at("09:00").do(send_questions)
schedule.every().thursday.at("09:00").do(send_questions)
schedule.every().friday.at("09:00").do(send_questions)

schedule.every().monday.at("09:30").do(lambda: send_summary(1))
schedule.every().tuesday.at("14:14").do(lambda: send_summary(1))
schedule.every().wednesday.at("09:30").do(lambda: send_summary(1))
schedule.every().thursday.at("09:30").do(lambda: send_summary(1))
schedule.every().friday.at("09:30").do(lambda: send_summary(1))

schedule.every().monday.at("11:00").do(lambda: send_summary(2))
schedule.every().tuesday.at("14:16").do(lambda: send_summary(2))
schedule.every().wednesday.at("11:00").do(lambda: send_summary(2))
schedule.every().thursday.at("11:00").do(lambda: send_summary(2))
schedule.every().friday.at("11:00").do(lambda: send_summary(2))

logger.info("🕒 Планировщик запущен. Ожидаем задачи…")
while True:
    schedule.run_pending()
    time.sleep(30)