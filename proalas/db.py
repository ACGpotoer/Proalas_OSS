import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g


def _db_path() -> str:
    return current_app.config["DATABASE_PATH"]


@contextmanager
def get_db():
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_g():
    if "db" not in g:
        g.db = sqlite3.connect(_db_path())
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate_schema(conn) -> None:
    """轻量迁移：为已有库补列。"""
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(device_account)").fetchall()
    }
    if "password_locked" not in cols:
        conn.execute(
            "ALTER TABLE device_account ADD COLUMN password_locked INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            """
            UPDATE device_account
            SET password_locked = 1
            WHERE COALESCE(password_plain, '') != ''
            """
        )


def init_db(app):
    with app.app_context():
        with get_db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS device_account (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL UNIQUE,
                    password_plain TEXT NOT NULL DEFAULT '',
                    password_locked INTEGER NOT NULL DEFAULT 0,
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS admin_user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_plain TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_message (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            migrate_schema(conn)
            ensure_default_admin_conn(conn, app)


def ensure_default_admin_conn(conn, app):
    row = conn.execute("SELECT id FROM admin_user LIMIT 1").fetchone()
    if row:
        return
    conn.execute(
        "INSERT INTO admin_user (username, password_plain) VALUES (?, ?)",
        (app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"]),
    )
