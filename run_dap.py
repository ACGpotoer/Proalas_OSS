#!/usr/bin/env python3
"""
开源版 DAP 外壳（仅本进程）。需先启动 Alas WebUI（gui.py）。

默认: http://127.0.0.1:8080
上游 Alas: http://127.0.0.1:22267（与 config/deploy.yaml WebuiPort 一致）

用法:
  pip install -r dap_requirements.txt   # 需 Python >=3.8，勿用 toolkit 3.7
  python run_dap.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv_file(env_path: Path, *, override: bool = False) -> None:
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ[key] = val


def _apply_oss_defaults() -> None:
    os.environ.setdefault("PROALAS_OSS", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "oss-local-dev-only")
    os.environ.setdefault("ALAS_UPSTREAM", "http://127.0.0.1:22267")
    os.environ.setdefault("CONFIG_DIR", str(ROOT / "config"))
    os.environ.setdefault("DATABASE_PATH", str(ROOT / "dap_data" / "proalas.db"))
    os.environ.setdefault("COMMANDS_DIR", str(ROOT / "dap_commands"))
    os.environ.setdefault("USER_DATA_PATH", str(ROOT / "dap_data" / "UserData.json"))
    os.environ.setdefault("ANNOUNCEMENT_PATH", str(ROOT / "dap_data" / "更新公告.md"))
    prompt = ROOT / "dap_commands" / "预提示词.txt"
    if prompt.is_file():
        os.environ.setdefault("PRE_PROMPT_PATH", str(prompt))
    shot = ROOT / "img"
    if shot.is_dir():
        os.environ.setdefault("DEVICE_SCREENSHOT_ROOT", str(shot))
    # 开源版默认不连 mmc；私用完全体勿把 MMC_* 写进仓库 .env
    (ROOT / "dap_data").mkdir(parents=True, exist_ok=True)
    (ROOT / "dap_commands").mkdir(parents=True, exist_ok=True)


_load_dotenv_file(ROOT / ".env", override=False)
_load_dotenv_file(ROOT / ".env.dap", override=True)
_apply_oss_defaults()

if __name__ == "__main__":
    if sys.version_info < (3, 8):
        print("DAP 需要 Python >= 3.8，当前:", sys.version)
        print("请用系统 Python（如 py -3.10），不要用 toolkit/python.exe (3.7)")
        sys.exit(1)

    import uvicorn

    print("=" * 56)
    print("ProAlas OSS · DAP 外壳（双进程：请另开 gui.py）")
    print("=" * 56)
    print("  浏览器: http://127.0.0.1:8080/login")
    print("  管理员: http://127.0.0.1:8080/admin/login")
    print("  Alas 上游:", os.environ.get("ALAS_UPSTREAM"))
    print("  CONFIG_DIR:", os.environ.get("CONFIG_DIR"))
    print("  MMC:", os.environ.get("MMC_COMMAND_URL") or "(未配置，开源默认)")
    print("=" * 56)
    uvicorn.run(
        "proalas.asgi_combined:application",
        host="127.0.0.1",
        port=int(os.environ.get("DAP_PORT", "8080")),
        reload=False,
    )
