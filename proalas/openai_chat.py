"""调用 OpenAI 兼容的 /v1/chat/completions（密钥仅从环境变量读取）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


def _load_system_prompt(path: str | None, max_chars: int = 28000) -> str:
    if not path:
        return _default_system()
    p = Path(path)
    if not p.is_file():
        return _default_system()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return _default_system()
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n…（预提示词已截断）"
    return text


def _default_system() -> str:
    return (
        "你是 ProAlas 控制台里的配置助手。用户会描述想改的「碧蓝 / Alas」相关设置。"
        "用简短中文回复；若涉及具体配置键，可给出建议或 JSON 草案，但不要编造不存在的路径。"
        "若已生成可执行的指令列表，请在回复末尾用 Markdown 代码块输出 JSON 数组（语言标签写 json），"
        "元素为字符串。优先使用预提示词语义行，例如："
        "[\"主线一 ['true','9-4','normal','3a1n']\", \"自动抽卡 ['true',1000]\", "
        "\"停止运行 ['true','18:00','24:00',['everyday']]\"]，"
        "服务端会自动转译为 change/userdata 并入队；也可直接写 change/userdata 行。"
        "对照表见 commands/提示词及其路径对照键值.txt。"
    )


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    history: list[tuple[str, str]],
) -> str:
    """history: (role, content)，role 为 user 或 assistant，按时间正序。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for role, content in history:
        r = "user" if role == "user" else "assistant"
        msgs.append({"role": r, "content": content})
    body = {
        "model": model,
        "messages": msgs,
        "temperature": 0.35,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return "（接口未返回 choices）"
    msg = (choices[0].get("message") or {}).get("content") or ""
    return (msg or "（空回复）").strip()
