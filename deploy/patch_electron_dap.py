# -*- coding: utf-8 -*-
"""Patch Alas Electron app.asar: load DAP as top-level URL (no file:// iframe)."""
from __future__ import print_function

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASAR_CANDIDATES = [
    os.path.join(ROOT, "toolkit", "webapp", "resources", "app.asar"),
    os.path.join(ROOT, "toolkit", "WebApp", "resources", "app.asar"),
    os.path.join(ROOT, "toolkit", "Lib", "site-packages", "alas_webapp", "app.asar"),
]
UNPACK = os.path.join(ROOT, "toolkit", "webapp", "resources", "app_unpacked")
MAIN_CJS = os.path.join(UNPACK, "packages", "main", "dist", "index.cjs")

OLD_LOAD = (
    'function(){const e=new n.URL("../renderer/dist/index.html","file://"+__dirname).toString();b?.loadURL(e)}()'
)
NEW_LOAD = 'function(){b?.loadURL("http://127.0.0.1:"+a+"/login")}()'

# frameless loses controls when not using Vue shell
OLD_FRAME = "frame:!1,icon:"
NEW_FRAME = "frame:!0,icon:"


def _run(cmd):
    print("[patch_electron]", " ".join(cmd))
    # Windows: npx is npx.cmd — need shell or full path
    kwargs = {}
    if os.name == "nt":
        kwargs["shell"] = True
    subprocess.check_call(cmd, **kwargs)


def ensure_unpacked(asar_path):
    if os.path.isfile(MAIN_CJS) and OLD_LOAD not in open(MAIN_CJS, encoding="utf-8", errors="replace").read():
        # already patched or different build — still try patch markers
        pass
    if not os.path.isdir(UNPACK) or not os.path.isfile(MAIN_CJS):
        if os.path.isdir(UNPACK):
            shutil.rmtree(UNPACK, ignore_errors=True)
        _run(["npx", "--yes", "@electron/asar", "extract", asar_path, UNPACK])


def patch_main():
    text = open(MAIN_CJS, encoding="utf-8", errors="replace").read()
    changed = False
    if "http://127.0.0.1:"+ "a" in text.replace(" ", "") and "/login" in text and "renderer/dist/index.html" not in text:
        print("[patch_electron] main already loads DAP URL")
    elif OLD_LOAD in text:
        text = text.replace(OLD_LOAD, NEW_LOAD)
        changed = True
        print("[patch_electron] loadURL -> http://127.0.0.1:{WebuiPort}/login")
    else:
        # fallback: any file:// renderer loadURL
        import re

        text2, n = re.subn(
            r'function\(\)\{const e=new n\.URL\("\.\./renderer/dist/index\.html","file://"\+__dirname\)\.toString\(\);b\?\.loadURL\(e\)\}\(\)',
            NEW_LOAD,
            text,
            count=1,
        )
        if n:
            text = text2
            changed = True
            print("[patch_electron] loadURL patched via regex")
        elif "b?.loadURL(\"http://127.0.0.1:\"+a" in text or 'b?.loadURL("http://127.0.0.1:"+a' in text:
            print("[patch_electron] DAP loadURL already present")
        else:
            print("[patch_electron] ERROR: cannot find loadURL pattern")
            print(text[text.find("loadURL") - 80 : text.find("loadURL") + 120] if "loadURL" in text else text[:200])
            return False

    if OLD_FRAME in text:
        text = text.replace(OLD_FRAME, NEW_FRAME, 1)
        changed = True
        print("[patch_electron] BrowserWindow frame:true (native chrome)")

# ensure closing window kills python — must run AFTER BrowserWindow is created
    close_bad = 'b.on("close",(function(){try{m.kill((function(){}))}catch(e){}})),e.app.on("window-all-closed"'
    if close_bad in text:
        text = text.replace(
            'b.on("close",(function(){try{m.kill((function(){}))}catch(e){}})),',
            "",
            1,
        )
        changed = True
        print("[patch_electron] removed broken top-level b.on(close)")

    close_ok = 'b.on("close",(function(){try{m.kill((function(){}))}catch(e){}})),b.on("ready-to-show"'
    if "b.on(\"close\"" not in text.split("whenReady")[-1] if "whenReady" in text else True:
        # prefer inject after window create
        marker = 'b.on("ready-to-show"'
        inject = 'b.on("close",(function(){try{m.kill((function(){}))}catch(e){}})),'
        if marker in text and inject + marker not in text:
            # only if close not already right before ready-to-show
            if close_ok not in text:
                text = text.replace(marker, inject + marker, 1)
                changed = True
                print("[patch_electron] added window close after BrowserWindow create")
    elif close_ok in text:
        print("[patch_electron] close handler already after create")

    if changed:
        open(MAIN_CJS, "w", encoding="utf-8", newline="\n").write(text)
    return True


def pack_to(asar_path):
    bak = asar_path + ".pre_dap.bak"
    if os.path.isfile(asar_path) and not os.path.isfile(bak):
        shutil.copy2(asar_path, bak)
        print("[patch_electron] backup", bak)
    tmp = asar_path + ".new"
    if os.path.isfile(tmp):
        os.remove(tmp)
    _run(["npx", "--yes", "@electron/asar", "pack", UNPACK, tmp])
    os.replace(tmp, asar_path)
    print("[patch_electron] wrote", asar_path)


def asar_has_dap(asar_path):
    try:
        with open(asar_path, "rb") as f:
            data = f.read()
        has_url = b'127.0.0.1:"+a+"/login' in data
        # broken patch: b.on(close) before window created
        has_bad = (
            b'b.on("close",(function(){try{m.kill((function(){}))}catch(e){}})),e.app.on("window-all-closed"'
            in data
        )
        return has_url and not has_bad
    except OSError:
        return False


def main():
    force = os.environ.get("PROALAS_FORCE_ELECTRON_PATCH", "").strip() in (
        "1",
        "true",
        "yes",
    )
    primary = None
    for p in ASAR_CANDIDATES:
        if os.path.isfile(p):
            primary = p
            break
    if not primary:
        print("[patch_electron] no app.asar found")
        return 1

    need_pack = force
    for p in ASAR_CANDIDATES:
        if os.path.isfile(p) and not asar_has_dap(p):
            need_pack = True
            break

    if not need_pack:
        print("[patch_electron] all app.asar already DAP-patched, skip")
        return 0

    ensure_unpacked(primary)
    if not patch_main():
        return 1

    seen = set()
    for p in ASAR_CANDIDATES:
        if os.path.isfile(p) and os.path.normcase(p) not in seen:
            seen.add(os.path.normcase(p))
            pack_to(p)
    print("[patch_electron] OK — Electron will open DAP top-level")
    return 0


if __name__ == "__main__":
    sys.exit(main())
