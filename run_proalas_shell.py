#!/usr/bin/env python3
"""
双进程外壳：Alas WebUI (gui.py) + DAP (run_dap.py)。

- Alas：优先用本仓库 toolkit/python.exe（3.7，与 Alas 依赖匹配）
- DAP：必须用 Python >=3.8（默认探测 e:/py310 或 PATH 上的 python）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAP_PORT = int(os.environ.get("DAP_PORT", "8080"))
ALAS_PORT = int(os.environ.get("ALAS_WEBUI_PORT", "22267"))


def _find_alas_python() -> str:
    toolkit = ROOT / "toolkit" / "python.exe"
    if toolkit.is_file():
        return str(toolkit)
    return sys.executable


def _find_dap_python() -> str:
    env = os.environ.get("DAP_PYTHON", "").strip()
    if env and Path(env).is_file():
        return env
    candidates = [
        Path(r"e:\py310\python.exe"),
        Path(r"C:\Python310\python.exe"),
        Path(r"C:\Python311\python.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ("py", "python"):
        which = shutil.which(name)
        if not which:
            continue
        try:
            out = subprocess.check_output(
                [which, "-c", "import sys; print(sys.version_info[:2])"],
                text=True,
                timeout=10,
            ).strip()
            # py launcher may need -3.10
            if name == "py":
                try:
                    subprocess.check_call(
                        [which, "-3.10", "-c", "import sys; assert sys.version_info >= (3, 8)"],
                        timeout=10,
                    )
                    return which + "||-3.10"  # marker
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
            major_minor = out.strip("() ").replace(" ", "")
            # "(3, 10)" style
            parts = [p.strip() for p in out.strip("()").split(",")]
            if len(parts) >= 2 and int(parts[0]) >= 3 and int(parts[1]) >= 8:
                return which
        except Exception:
            continue
    print("未找到 Python >=3.8，请安装后设置环境变量 DAP_PYTHON=路径\\python.exe")
    sys.exit(1)


def _popen(cmd: list[str], *, title: str) -> subprocess.Popen:
    print(f"[start] {title}:", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )


def _ensure_device_config() -> None:
    cfg = ROOT / "config"
    has = any(
        p.suffix == ".json" and not p.name.startswith("template")
        for p in cfg.glob("*.json")
    )
    if has:
        return
    src = cfg / "template.json"
    dst = cfg / "alas.json"
    if src.is_file():
        shutil.copy2(src, dst)
        print(f"[init] 已从 template.json 生成 {dst.name}（首次登录设备号 alas，密码可空）")


def main() -> None:
    os.chdir(ROOT)
    _ensure_device_config()

    alas_py = _find_alas_python()
    dap_raw = _find_dap_python()
    if "||-3.10" in dap_raw:
        dap_cmd = [dap_raw.split("||")[0], "-3.10", str(ROOT / "run_dap.py")]
    else:
        dap_cmd = [dap_raw, str(ROOT / "run_dap.py")]

    env = os.environ.copy()
    env.setdefault("PROALAS_OSS", "1")
    env.setdefault("ALAS_UPSTREAM", f"http://127.0.0.1:{ALAS_PORT}")

    alas_proc = _popen(
        [alas_py, str(ROOT / "gui.py"), "-p", str(ALAS_PORT)],
        title="Alas WebUI",
    )
    print(f"等待 Alas WebUI :{ALAS_PORT} …")
    time.sleep(4)

    dap_proc = subprocess.Popen(
        dap_cmd,
        cwd=str(ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )
    print(f"[start] DAP:", " ".join(dap_cmd))
    time.sleep(2)
    url = f"http://127.0.0.1:{DAP_PORT}/login"
    print("打开:", url)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("两个控制台窗口分别跑 Alas / DAP；关掉窗口即停止对应进程。")
    print("本启动器可直接关闭，不影响子进程。")
    # 不 wait：避免启动器挂起；子进程已独立控制台
    _ = (alas_proc, dap_proc)


if __name__ == "__main__":
    main()
