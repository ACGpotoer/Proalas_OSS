# -*- coding: utf-8 -*-
"""启动前检查：gui.py 是否含 DAP 入口；deploy AutoUpdate/WebuiPort。"""
from __future__ import print_function

import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "gui.py")
GUI_BACKUP = os.path.join(ROOT, "deploy", "gui.py.stock.bak")
MARKER = "ProAlas OSS: DAP shell"


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace")


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def ensure_gui():
    text = _read(GUI)
    if MARKER in text and "run_dap_shell" in text:
        print("[ensure_dap] gui.py OK")
        return True
    # Prefer canonical copy if present
    canon = os.path.join(ROOT, "deploy", "gui_proalas_oss.py")
    if os.path.isfile(canon):
        if not os.path.isfile(GUI_BACKUP):
            shutil.copy2(GUI, GUI_BACKUP)
        shutil.copy2(canon, GUI)
        print("[ensure_dap] restored gui.py from deploy/gui_proalas_oss.py")
        return True
    print("[ensure_dap] ERROR: gui.py missing DAP hook and no deploy/gui_proalas_oss.py")
    return False


def ensure_deploy_yaml():
    path = os.path.join(ROOT, "config", "deploy.yaml")
    if not os.path.isfile(path):
        print("[ensure_dap] no deploy.yaml")
        return
    text = _read(path)
    orig = text
    text = re.sub(r"(AutoUpdate:\s*)true", r"\1false", text, count=1, flags=re.I)
    # WebuiPort -> 8080 (DAP). Keep comment lines.
    text = re.sub(
        r"(WebuiPort:\s*)\d+",
        r"\g<1>8080",
        text,
        count=1,
    )
    if text != orig:
        _write(path, text)
        print("[ensure_dap] deploy.yaml: AutoUpdate=false, WebuiPort=8080")
    else:
        print("[ensure_dap] deploy.yaml OK")


def main():
    os.chdir(ROOT)
    ok = ensure_gui()
    ensure_deploy_yaml()
    dap_shell = os.path.join(ROOT, "module", "webui", "dap_shell.py")
    proalas = os.path.join(ROOT, "proalas", "asgi_combined.py")
    if not os.path.isfile(dap_shell):
        print("[ensure_dap] MISSING module/webui/dap_shell.py")
        ok = False
    if not os.path.isfile(proalas):
        print("[ensure_dap] MISSING proalas/ (DAP package)")
        ok = False
    # Electron must load DAP top-level (not file:// iframe)
    patch = os.path.join(ROOT, "deploy", "patch_electron_dap.py")
    if os.path.isfile(patch):
        try:
            import subprocess

            r = subprocess.call([sys.executable, patch])
            if r != 0:
                print("[ensure_dap] patch_electron_dap failed (close Alas.exe and retry)")
                ok = False
        except Exception as e:
            print("[ensure_dap] patch_electron error:", e)
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
