import os
import logging
from typing import Iterable

import psycopg
from psycopg.rows import dict_row

# 1) базовое логирование (если не настроено выше)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("db")

# 2) Пытаемся подхватить .env, если переменная не задана
if "DATABASE_URL" not in os.environ:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # загрузит .env из текущего каталога
        logger.info("[DB] .env loaded by db.py")
    except Exception as e:
        logger.warning(f"[DB] cannot load .env automatically: {e}")

DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://user:pass@host:5432/dbname

_pool = None
if DATABASE_URL:
    try:
        # Проверим, что можем коннектиться
        _pool = psycopg.Connection.connect(DATABASE_URL, autocommit=True)
        _pool.close()
        logger.info("[DB] PostgreSQL enabled")
    except Exception as e:
        logger.error(f"[DB] cannot connect: {e}")
        _pool = None
else:
    logger.info("[DB] DATABASE_URL not set — DB disabled")

def enabled() -> bool:
    return _pool is not None

def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DB disabled: set DATABASE_URL")
    return psycopg.connect(DATABASE_URL, autocommit=True)

def init_db():
    """Создать таблицы, если их нет."""
    if not enabled():
        raise RuntimeError("DB disabled: set DATABASE_URL")

    sql = """
    CREATE TABLE IF NOT EXISTS employees (
        tg_chat_id   BIGINT PRIMARY KEY,
        full_name    TEXT,
        team_id      INT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS summaries (
        id              BIGSERIAL PRIMARY KEY,
        tg_chat_id      BIGINT NOT NULL,
        conversation_id TEXT,
        summary_text    TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        FOREIGN KEY (tg_chat_id) REFERENCES employees(tg_chat_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_summaries_chat_time ON summaries (tg_chat_id, created_at DESC);
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("[DB] schema ensured")

def upsert_employee(tg_chat_id: int, full_name: str | None, team_id: int | None):
    if not enabled():
        return
    sql = """
    INSERT INTO employees (tg_chat_id, full_name, team_id)
    VALUES (%s, %s, %s)
    ON CONFLICT (tg_chat_id)
    DO UPDATE SET
      full_name = EXCLUDED.full_name,
      team_id   = EXCLUDED.team_id,
      updated_at = NOW();
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tg_chat_id, full_name, team_id))

def insert_summary(tg_chat_id: int, full_name: str | None, team_id: int | None,
                   conversation_id: str | None, summary_text: str) -> int:
    if not enabled():
        return -1
    upsert_employee(tg_chat_id, full_name, team_id)
    sql = """
    INSERT INTO summaries (tg_chat_id, conversation_id, summary_text)
    VALUES (%s, %s, %s)
    RETURNING id;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tg_chat_id, conversation_id, summary_text))
            new_id = cur.fetchone()[0]
    return new_id

def fetch_today_summaries(chat_ids: Iterable[int]) -> dict[int, str]:
    """
    Возвращает по одному последнему саммари на сотрудника за ТЕКУЩИЕ СУТКИ (UTC).
    dict[tg_chat_id] = summary_text
    """
    if not enabled():
        return {}

    chat_ids = list(chat_ids)
    if not chat_ids:
        return {}

    sql = """
    WITH today AS (
      SELECT s.*
      FROM summaries s
      WHERE s.created_at >= DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')
        AND s.created_at <  DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC') + INTERVAL '1 day'
        AND s.tg_chat_id = ANY(%s)
    ),
    last_per_user AS (
      SELECT DISTINCT ON (tg_chat_id)
             tg_chat_id, summary_text, created_at
      FROM today
      ORDER BY tg_chat_id, created_at DESC
    )
    SELECT tg_chat_id, summary_text FROM last_per_user;
    """
    result = {}
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (chat_ids,))
            for row in cur.fetchall():
                result[int(row["tg_chat_id"])] = row["summary_text"]
    return result