"""AI 对话配额（SQLite，按设备账号 / 自然日）。"""
from __future__ import annotations

from datetime import datetime

from flask import current_app

from proalas.db import get_db


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _limit() -> int:
    try:
        return int(current_app.config.get("AI_DAILY_QUESTION_LIMIT", 50))
    except RuntimeError:
        return 50


def _max_len() -> int:
    try:
        return int(current_app.config.get("AI_MAX_MESSAGE_LEN", 1000))
    except RuntimeError:
        return 1000


def ensure_ai_usage_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_daily_usage (
            device_id TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            question_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (device_id, usage_date)
        )
        """
    )


def get_usage(device_id: str) -> tuple[int, int]:
    """返回 (已用次数, 每日上限)。"""
    limit = _limit()
    with get_db() as conn:
        ensure_ai_usage_table(conn)
        row = conn.execute(
            "SELECT question_count FROM ai_daily_usage WHERE device_id = ? AND usage_date = ?",
            (device_id, _today()),
        ).fetchone()
    used = int(row["question_count"]) if row else 0
    return used, limit


def validate_message(content: str) -> str | None:
    if len(content) > _max_len():
        return f"单条消息不能超过 {_max_len()} 字（当前 {len(content)} 字）。"
    return None


def consume_question(device_id: str) -> str | None:
    """成功则 None；超限则返回错误文案。"""
    limit = _limit()
    with get_db() as conn:
        ensure_ai_usage_table(conn)
        row = conn.execute(
            "SELECT question_count FROM ai_daily_usage WHERE device_id = ? AND usage_date = ?",
            (device_id, _today()),
        ).fetchone()
        used = int(row["question_count"]) if row else 0
        if used >= limit:
            return f"今日 AI 提问已达上限（{limit} 次/天），请明天再试。"
        conn.execute(
            """
            INSERT INTO ai_daily_usage (device_id, usage_date, question_count)
            VALUES (?, ?, 1)
            ON CONFLICT(device_id, usage_date) DO UPDATE SET
                question_count = question_count + 1
            """,
            (device_id, _today()),
        )
    return None
