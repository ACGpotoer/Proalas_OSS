"""Per-device command/chat files under COMMANDS_DIR/<device_id>/.

- chat.jsonl: one JSON object per line {role, content, ts?}
- commands.json: pending / meta snapshot for future AI command parsing
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from proalas.command_validate import split_normalized_special_change

_SAFE_DEVICE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")

_DEFAULT_COMMANDS = {
    "pending": [],
    "pending_immediate": [],
    "pending_scheduled": [],
    "history": [],
    "meta": {},
    "special_commands": {"pending": {}, "history": []},
}


def assert_safe_device_id(device_id: str) -> None:
    if not device_id or not _SAFE_DEVICE_ID.match(device_id):
        raise ValueError("invalid device_id")


def device_command_dir(commands_dir: str, device_id: str) -> Path:
    assert_safe_device_id(device_id)
    root = Path(commands_dir).expanduser().resolve()
    # device_id 已禁止含路径分隔符，无需再 resolve(user)，减少 Windows 上多余 syscall
    user = root / device_id
    return user


def ensure_user_command_files(commands_dir: str, device_id: str) -> Path:
    d = device_command_dir(commands_dir, device_id)
    d.mkdir(parents=True, exist_ok=True)
    cmd_path = d / "commands.json"
    if not cmd_path.is_file():
        cmd_path.write_text(
            json.dumps(_DEFAULT_COMMANDS, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return d


def append_chat_jsonl(commands_dir: str, device_id: str, role: str, content: str) -> None:
    d = ensure_user_command_files(commands_dir, device_id)
    path = d / "chat.jsonl"
    rec = {
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _tail_line_strings(path: Path, max_lines: int, max_bytes: int | None = None) -> list[str]:
    """Read at most the last max_lines complete lines without scanning the whole file."""
    budget = max_bytes if max_bytes is not None else max(512 * 1024, max_lines * 48 * 1024)
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    if size <= budget:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:] if len(lines) > max_lines else lines
    to_read = min(size, budget)
    with path.open("rb") as f:
        f.seek(size - to_read)
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if lines:
        lines = lines[1:]  # 首行可能因 seek 截断，丢弃
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return lines


def _parse_chat_line(line: str) -> SimpleNamespace | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    role = obj.get("role")
    content = obj.get("content")
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    return SimpleNamespace(role=role, content=content)


def read_chat_messages(commands_dir: str, device_id: str, limit: int = 20) -> list[SimpleNamespace]:
    try:
        d = device_command_dir(commands_dir, device_id)
    except ValueError:
        return []
    path = d / "chat.jsonl"
    if not path.is_file():
        return []
    raw_lines = _tail_line_strings(path, limit)
    out: list[SimpleNamespace] = []
    for line in raw_lines:
        m = _parse_chat_line(line)
        if m:
            out.append(m)
    return out


def read_chat_history_pairs(commands_dir: str, device_id: str, limit: int = 16) -> list[tuple[str, str]]:
    msgs = read_chat_messages(commands_dir, device_id, limit=limit)
    return [(m.role, m.content) for m in msgs]


def load_commands_json(commands_dir: str, device_id: str) -> dict:
    try:
        d = device_command_dir(commands_dir, device_id)
    except ValueError:
        return dict(_DEFAULT_COMMANDS)
    path = d / "commands.json"
    if not path.is_file():
        ensure_user_command_files(commands_dir, device_id)
        return dict(_DEFAULT_COMMANDS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_COMMANDS)
    if not isinstance(data, dict):
        return dict(_DEFAULT_COMMANDS)
    out = dict(_DEFAULT_COMMANDS)
    out.update(data)
    imm = out.get("pending_immediate")
    if not isinstance(imm, list):
        imm = []
    legacy = out.get("pending")
    if isinstance(legacy, list) and legacy and not imm:
        imm = legacy
    out["pending_immediate"] = imm
    out["pending"] = imm
    if not isinstance(out.get("pending_scheduled"), list):
        out["pending_scheduled"] = []
    sc = out.get("special_commands")
    if not isinstance(sc, dict):
        out["special_commands"] = {"pending": {}, "history": []}
    else:
        if not isinstance(sc.get("pending"), dict):
            sc["pending"] = {}
        h = sc.get("history")
        if isinstance(h, dict):
            sc["history"] = []
        elif not isinstance(h, list):
            sc["history"] = []
        out["special_commands"] = sc
    return out


def save_commands_json(commands_dir: str, device_id: str, data: dict) -> None:
    d = ensure_user_command_files(commands_dir, device_id)
    path = d / "commands.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_pending_item(x) -> dict | None:
    if isinstance(x, str) and x.strip():
        return {"text": x.strip(), "created_at": None}
    if isinstance(x, dict) and isinstance(x.get("text"), str) and x["text"].strip():
        return {
            "text": x["text"].strip(),
            "created_at": x.get("created_at"),
        }
    return None


def append_routed_commands(
    commands_dir: str,
    device_id: str,
    *,
    immediate_alas: list[str] | None = None,
    immediate_userdata: list[str] | None = None,
    pending_scheduled: list[dict] | None = None,
    rejected: list[tuple[str, str]] | None = None,
    max_pending: int = 500,
    max_history: int = 80,
) -> dict:
    """写入 pending_immediate（Alas change + userdata 行）与 pending_scheduled（定时任务）。"""
    ts = datetime.now(timezone.utc).isoformat()
    immediate_alas = immediate_alas or []
    immediate_userdata = immediate_userdata or []
    pending_scheduled = pending_scheduled or []
    rejected = rejected or []

    data = load_commands_json(commands_dir, device_id)
    imm: list[dict] = []
    for x in data.get("pending_immediate") or data.get("pending") or []:
        n = _normalize_pending_item(x)
        if n:
            imm.append(n)

    new_lines = [t for t in immediate_alas + immediate_userdata if t]
    imm.extend([{"text": t, "created_at": ts} for t in new_lines])
    if len(imm) > max_pending:
        imm = imm[-max_pending:]

    sched = data.get("pending_scheduled")
    if not isinstance(sched, list):
        sched = []
    for job in pending_scheduled:
        if not isinstance(job, dict):
            continue
        kind = job.get("kind")
        dev = job.get("device_id")
        new_sched: list[dict] = []
        replaced = False
        for old in sched:
            if (
                isinstance(old, dict)
                and old.get("kind") == kind
                and old.get("device_id") == dev
            ):
                if not replaced:
                    st = old.get("state") if isinstance(old.get("state"), dict) else {}
                    new_sched.append({**job, "state": st})
                    replaced = True
            else:
                new_sched.append(old)
        if not replaced:
            new_sched.append(job)
        sched = new_sched
    data["pending_scheduled"] = sched

    history = data.get("history")
    if not isinstance(history, list):
        history = []
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}

    hist_entry: dict = {
        "ts": ts,
        "source": "assistant_chat",
        "immediate_count": len(new_lines),
        "scheduled_count": len(pending_scheduled),
        "preview": [x[:200] for x in new_lines[:5]],
        "scheduled_preview": [
            f"{j.get('kind')}:{j.get('device_id')}" for j in pending_scheduled[:5]
        ],
    }
    if rejected:
        hist_entry["rejected_count"] = len(rejected)
        hist_entry["rejected_preview"] = [
            {"cmd": c[:200], "reason": r[:300]} for c, r in rejected[:8]
        ]
    history.append(hist_entry)
    if len(history) > max_history:
        history = history[-max_history:]

    parse_meta = {
        "ts": ts,
        "appended_immediate": len(new_lines),
        "appended_scheduled": len(pending_scheduled),
        "rejected_count": len(rejected),
        "rejected": [{"cmd": c[:300], "reason": r[:400]} for c, r in rejected[:15]],
        "ok": True,
        "error": None,
    }
    meta = {**meta, "last_parse": parse_meta}

    out = {
        **data,
        "pending_immediate": imm,
        "pending": imm,
        "pending_scheduled": sched,
        "history": history,
        "meta": meta,
        "special_commands": data.get("special_commands")
        if isinstance(data.get("special_commands"), dict)
        else {"pending": {}, "history": []},
    }
    save_commands_json(commands_dir, device_id, out)
    return parse_meta


def append_pending_commands(
    commands_dir: str,
    device_id: str,
    command_texts: list[str],
    *,
    special_command_texts: list[str] | None = None,
    max_pending: int = 500,
    max_history: int = 80,
    max_special_history: int = 80,
    rejected: list[tuple[str, str]] | None = None,
) -> dict:
    """兼容旧接口：全部视为即时 Alas pending。"""
    return append_routed_commands(
        commands_dir,
        device_id,
        immediate_alas=command_texts,
        rejected=rejected,
        max_pending=max_pending,
        max_history=max_history,
    )


def migrate_sqlite_chat_if_needed(conn, commands_dir: str, device_id: str) -> None:
    """If chat.jsonl is empty but SQLite has rows, copy to jsonl and clear SQLite."""
    try:
        d = device_command_dir(commands_dir, device_id)
    except ValueError:
        return
    chat_path = d / "chat.jsonl"
    if chat_path.is_file() and chat_path.stat().st_size > 0:
        return
    rows = conn.execute(
        "SELECT role, content FROM chat_message WHERE device_id = ? ORDER BY id",
        (device_id,),
    ).fetchall()
    if not rows:
        return
    d.mkdir(parents=True, exist_ok=True)
    ensure_user_command_files(commands_dir, device_id)
    with chat_path.open("w", encoding="utf-8") as f:
        for row in rows:
            rec = {
                "role": row["role"],
                "content": row["content"],
                "ts": None,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    conn.execute("DELETE FROM chat_message WHERE device_id = ?", (device_id,))


def delete_user_command_store(commands_dir: str, device_id: str) -> None:
    try:
        d = device_command_dir(commands_dir, device_id)
    except ValueError:
        return
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
