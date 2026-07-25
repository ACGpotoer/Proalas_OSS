"""从助手回复中提取可写入 commands.json 的指令列表。

预提示词约定：模型在正文后可输出 JSON 数组，元素为字符串，例如
  ["change 0D001 Main.Scheduler.Enable true", ...]
推荐放在 Markdown 围栏内： ```json ... ``` 或 ```proalas_commands ... ```
"""
from __future__ import annotations

import json
import re
from json import JSONDecoder
from typing import Any

_FENCE = re.compile(
    r"```\s*(?:json|proalas_commands)\s*([\s\S]*?)```",
    re.IGNORECASE,
)
_GENERIC_FENCE = re.compile(r"```\s*([\s\S]*?)```")


def _coerce_command_item(x: Any) -> str | None:
    if isinstance(x, str):
        s = x.strip()
        return s or None
    if isinstance(x, dict):
        for k in ("text", "cmd", "line", "command"):
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _normalize_command_list(data: Any) -> list[str] | None:
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for x in data:
        s = _coerce_command_item(x)
        if s:
            out.append(s)
    return out


def _try_load_json_array(blob: str) -> list[str] | None:
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return _normalize_command_list(data)


def _first_bracket_array(text: str) -> list[str] | None:
    """从首个 '[' 起尝试 raw_decode 一个 JSON 数组（应对无围栏的数组）。"""
    i = 0
    while True:
        i = text.find("[", i)
        if i < 0:
            return None
        dec = JSONDecoder()
        try:
            obj, _ = dec.raw_decode(text[i:])
        except json.JSONDecodeError:
            i += 1
            continue
        got = _normalize_command_list(obj)
        if got is not None:
            return got
        i += 1


def parse_commands_from_assistant_reply(reply: str) -> list[str] | None:
    """
    若解析到至少一条指令则返回列表；若无有效 JSON 数组或数组为空则返回 None。
    （与「空数组表示无操作」一致：不写入 pending。）
    """
    if not reply or not reply.strip():
        return None

    # 优先：带 json / proalas_commands 标签的围栏（取最后一个成功解析的，与预提示词「文末独占块」一致）
    last_labeled: list[str] | None = None
    for m in _FENCE.finditer(reply):
        got = _try_load_json_array(m.group(1))
        if got:
            last_labeled = got
    if last_labeled:
        return last_labeled

    # 其次：任意 ``` 围栏（同样取最后一个可解析为指令数组的）
    last_generic: list[str] | None = None
    for m in _GENERIC_FENCE.finditer(reply):
        got = _try_load_json_array(m.group(1))
        if got:
            last_generic = got
    if last_generic:
        return last_generic

    # 最后：正文中第一个可解析的 JSON 数组
    got = _first_bracket_array(reply)
    if got:
        return got

    return None
