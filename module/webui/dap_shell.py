# Dual-process DAP shell helpers (runs under Alas toolkit Python 3.7).
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERNAL_ALAS_PORT = int(os.environ.get("ALAS_INTERNAL_PORT", "22267"))
DAP_PORT_DEFAULT = int(os.environ.get("DAP_PORT", "8080"))


def find_dap_python() -> str:
    env = (os.environ.get("DAP_PYTHON") or "").strip()
    if env and Path(env).is_file():
        return env
    for c in (
        Path(r"e:\py310\python.exe"),
        Path(r"C:\Python310\python.exe"),
        Path(r"C:\Python311\python.exe"),
    ):
        if c.is_file():
            return str(c)
    which = shutil.which("python") or shutil.which("py")
    if which:
        try:
            out = subprocess.check_output(
                [which, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                text=True,
                timeout=10,
            ).strip()
            major, minor = [int(x) for x in out.split(".")[:2]]
            if (major, minor) >= (3, 8):
                return which
        except Exception:
            pass
    raise RuntimeError(
        "DAP needs Python >= 3.8. Set DAP_PYTHON to a python.exe path "
        "(toolkit 3.7 cannot run the DAP shell)."
    )


def ensure_device_config() -> None:
    cfg = ROOT / "config"
    if not cfg.is_dir():
        return
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


def start_alas_webui(host: str, port: int) -> subprocess.Popen:
    """Start stock Alas PyWebIO on an internal port (same interpreter as gui.py)."""
    # Re-enter gui without DAP / electron to avoid recursion.
    env = os.environ.copy()
    env["PROALAS_USE_DAP"] = "0"
    cmd = [
        sys.executable,
        str(ROOT / "gui.py"),
        "--host",
        host or "127.0.0.1",
        "-p",
        str(port),
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def start_dap(port: int, alas_upstream_port: int) -> subprocess.Popen:
    dap_py = find_dap_python()
    env = os.environ.copy()
    env["PROALAS_OSS"] = "1"
    env["PROALAS_USE_DAP"] = "0"  # run_dap only
    env["DAP_PORT"] = str(port)
    env["ALAS_UPSTREAM"] = "http://127.0.0.1:%d" % alas_upstream_port
    env.setdefault("CONFIG_DIR", str(ROOT / "config"))
    env.setdefault("DATABASE_PATH", str(ROOT / "dap_data" / "proalas.db"))
    return subprocess.Popen(
        [dap_py, str(ROOT / "run_dap.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def wait_http(port: int, timeout: float = 60.0) -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket()
        s.settimeout(1.0)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except Exception:
            time.sleep(0.4)
        finally:
            try:
                s.close()
            except Exception:
                pass
    return False


def run_dap_shell(host: str, electron_port: int) -> None:
    """
    Electron iframes http://127.0.0.1:{electron_port}.
    We bind DAP there and keep stock Alas on INTERNAL_ALAS_PORT.
    """
    ensure_device_config()
    (ROOT / "dap_data").mkdir(parents=True, exist_ok=True)

    alas_port = INTERNAL_ALAS_PORT
    if alas_port == electron_port:
        alas_port = 22267 if electron_port != 22267 else 22266

    sys.stderr.write(
        "[ProAlas] DAP shell: Alas WebUI :%d + DAP :%d\n" % (alas_port, electron_port)
    )
    sys.stderr.flush()

    alas_proc = start_alas_webui("127.0.0.1", alas_port)
    dap_proc = start_dap(electron_port, alas_port)

    if not wait_http(alas_port, 90):
        sys.stderr.write("[ProAlas] Alas WebUI failed to listen on %d\n" % alas_port)
    if not wait_http(electron_port, 90):
        sys.stderr.write("[ProAlas] DAP failed to listen on %d\n" % electron_port)
        # Still emit ready so Electron shows something / error page
    # Electron PyShell waits for this exact phrase on stderr
    sys.stderr.write("Application startup complete\n")
    sys.stderr.flush()

    try:
        while True:
            if alas_proc.poll() is not None:
                sys.stderr.write("[ProAlas] Alas WebUI exited code=%s\n" % alas_proc.returncode)
                break
            if dap_proc.poll() is not None:
                sys.stderr.write("[ProAlas] DAP exited code=%s\n" % dap_proc.returncode)
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (dap_proc, alas_proc):
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
