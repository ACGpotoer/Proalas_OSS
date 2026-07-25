"""更新公告：读取 Markdown 并转为简单 HTML。"""
from __future__ import annotations

import html
import re
from pathlib import Path


def _announcement_path() -> Path:
    try:
        from flask import current_app

        p = current_app.config.get("ANNOUNCEMENT_PATH") or ""
        if p:
            return Path(p).expanduser()
        return Path(current_app.root_path).resolve().parent / "更新公告.md"
    except RuntimeError:
        return Path(__file__).resolve().parent.parent / "更新公告.md"


def parse_version(text: str) -> str:
    m = re.search(r"更新版本\s*([\d.]+)", text)
    return m.group(1) if m else "0"


def markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_ul = False
    for line in lines:
        s = line.rstrip()
        if not s:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            continue
        if s.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif re.match(r"^\d+\.\s", s) or s.startswith("--->"):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            body = re.sub(r"^\d+\.\s*", "", s)
            body = body.replace("--->", "").strip()
            out.append(f"<li>{html.escape(body)}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<p>{html.escape(s)}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def load_announcement() -> dict[str, str]:
    path = _announcement_path()
    if not path.is_file():
        return {"version": "0", "title": "更新公告", "html": "<p>暂无公告。</p>"}
    text = path.read_text(encoding="utf-8")
    version = parse_version(text)
    title_m = re.search(r"^#\s+(.+)$", text, re.M)
    title = title_m.group(1).strip() if title_m else "更新公告"
    return {
        "version": version,
        "title": title,
        "html": markdown_to_html(text),
    }
