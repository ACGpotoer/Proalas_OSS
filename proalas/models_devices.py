"""Device accounts: sync from Alas config JSON names; passwords per readme (plaintext)."""
import json
import os
from pathlib import Path


def list_config_device_ids(config_dir: str) -> list[str]:
    p = Path(config_dir)
    if not p.is_dir():
        return []
    out = []
    for f in sorted(p.glob("*.json")):
        name = f.stem
        if name.startswith("template"):
            continue
        out.append(name)
    return out


def sync_devices_from_config(conn, config_dir: str):
    for device_id in list_config_device_ids(config_dir):
        conn.execute(
            """
            INSERT OR IGNORE INTO device_account (device_id, password_plain, password_locked)
            VALUES (?, '', 0)
            """,
            (device_id,),
        )


def get_device(conn, device_id: str):
    return conn.execute(
        "SELECT * FROM device_account WHERE device_id = ?", (device_id,)
    ).fetchone()


def list_devices(conn):
    return conn.execute(
        "SELECT * FROM device_account ORDER BY device_id"
    ).fetchall()


def verify_login(conn, device_id: str, password: str) -> bool:
    row = get_device(conn, device_id)
    if not row:
        return False
    stored = row["password_plain"] or ""
    return stored == (password or "")


def password_needs_setup(row) -> bool:
    if not row:
        return False
    locked = int(row["password_locked"] or 0)
    stored = row["password_plain"] or ""
    return not locked and stored == ""


def password_is_locked(row) -> bool:
    if not row:
        return False
    return bool(int(row["password_locked"] or 0))


def set_password_once(conn, device_id: str, password_plain: str) -> tuple[bool, str]:
    row = get_device(conn, device_id)
    if not row:
        return False, "设备不存在"
    if password_is_locked(row):
        return False, "密码已设置，不可修改；遗忘请联系管理员重置"
    pwd = (password_plain or "").strip()
    if len(pwd) < 4:
        return False, "密码至少 4 位"
    conn.execute(
        """
        UPDATE device_account
        SET password_plain = ?, password_locked = 1
        WHERE device_id = ?
        """,
        (pwd, device_id),
    )
    return True, "ok"


def admin_reset_password(conn, device_id: str, password_plain: str = "") -> None:
    pwd = password_plain or ""
    locked = 1 if pwd else 0
    conn.execute(
        """
        UPDATE device_account
        SET password_plain = ?, password_locked = ?
        WHERE device_id = ?
        """,
        (pwd, locked, device_id),
    )


def set_password(conn, device_id: str, password_plain: str):
    """兼容旧调用；新逻辑请用 set_password_once / admin_reset_password。"""
    conn.execute(
        "UPDATE device_account SET password_plain = ? WHERE device_id = ?",
        (password_plain or "", device_id),
    )


def admin_upsert_device(conn, device_id: str, password_plain: str = "", note: str = ""):
    pwd = password_plain or ""
    locked = 1 if pwd else 0
    conn.execute(
        """
        INSERT INTO device_account (device_id, password_plain, password_locked, note)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            password_plain = excluded.password_plain,
            password_locked = CASE
                WHEN excluded.password_plain = '' THEN 0
                ELSE 1
            END,
            note = excluded.note
        """,
        (device_id, pwd, locked, note or ""),
    )


def admin_delete_device(conn, device_id: str):
    conn.execute("DELETE FROM device_account WHERE device_id = ?", (device_id,))
    conn.execute("DELETE FROM chat_message WHERE device_id = ?", (device_id,))


def load_user_data(user_data_path: str) -> dict:
    try:
        if os.path.isfile(user_data_path):
            with open(user_data_path, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}
