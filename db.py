import os
import logging
from typing import Iterable

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("db")

if not os.getenv("DATABASE_URL"):
    load_dotenv()
    logger.info("[DB] .env loaded by db.py")

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None
if DATABASE_URL:
    try:
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
        summary_date    DATE NOT NULL DEFAULT (timezone('UTC', now())::date),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        FOREIGN KEY (tg_chat_id) REFERENCES employees(tg_chat_id) ON DELETE CASCADE
    );

    CREATE UNIQUE INDEX IF NOT EXISTS uq_summaries_day ON summaries (tg_chat_id, summary_date);
    CREATE INDEX IF NOT EXISTS idx_summaries_chat_time ON summaries (tg_chat_id, created_at DESC);
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("[DB] schema ensured")

def migrate_day_unique():
    if not enabled():
        raise RuntimeError("DB disabled: set DATABASE_URL")

    sql = """
    ALTER TABLE summaries ADD COLUMN IF NOT EXISTS summary_date DATE;
    ALTER TABLE summaries ALTER COLUMN summary_date SET DEFAULT (timezone('UTC', now())::date);
    UPDATE summaries
       SET summary_date = (created_at AT TIME ZONE 'UTC')::date
     WHERE summary_date IS NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_summaries_day ON summaries (tg_chat_id, summary_date);
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("[DB] migration to day-unique done")

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
    INSERT INTO summaries (tg_chat_id, conversation_id, summary_text, summary_date)
    VALUES (%s, %s, %s, DEFAULT)
    ON CONFLICT (tg_chat_id, summary_date)
    DO UPDATE SET
      summary_text    = EXCLUDED.summary_text,
      conversation_id = EXCLUDED.conversation_id,
      created_at      = NOW()
    RETURNING id;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tg_chat_id, conversation_id, summary_text))
            new_id = cur.fetchone()[0]
    return new_id

def fetch_today_summaries(chat_ids: Iterable[int]) -> dict[int, str]:
    if not enabled():
        return {}

    chat_ids = list(chat_ids)
    if not chat_ids:
        return {}

    sql = """
    SELECT tg_chat_id, summary_text
      FROM summaries
     WHERE summary_date = (timezone('UTC', now())::date)
       AND tg_chat_id = ANY(%s);
    """
    result = {}
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (chat_ids,))
            for row in cur.fetchall():
                result[int(row["tg_chat_id"])] = row["summary_text"]
    return result