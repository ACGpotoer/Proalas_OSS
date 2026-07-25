"""解析预提示词语义行：指令名 + Python/JSON 数组。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

_CHANGE_PREFIX = re.compile(r"^change\s+", re.I)
_MACRO_PREFIX = re.compile(r"^macro\s+", re.I)
_USERDATA_PREFIX = re.compile(r"^userdata\s+", re.I)


def parse_semantic_line(line: str) -> tuple[str, Any] | None:
    """
    例：停止运行 ['true','18:00','24:00',['everyday']]
    返回 (指令名, payload)。
    """
    s = line.strip()
    if not s:
        return None
    if _CHANGE_PREFIX.match(s) or _MACRO_PREFIX.match(s) or _USERDATA_PREFIX.match(s):
        return None
    idx = s.find("[")
    if idx <= 0:
        return None
    name = s[:idx].strip()
    tail = s[idx:].strip()
    if not name:
        return None
    try:
        payload = json.loads(tail.replace("'", '"'))
    except json.JSONDecodeError:
        try:
            payload = ast.literal_eval(tail)
        except (SyntaxError, ValueError):
            return None
    return name, payload


def format_userdata_line(device_id: str, field: str, value: Any) -> str:
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif value is None:
        v = "null"
    elif isinstance(value, (list, dict)):
        v = json.dumps(value, ensure_ascii=False)
    else:
        v = str(value)
    return f"userdata {device_id} {field} {v}"
