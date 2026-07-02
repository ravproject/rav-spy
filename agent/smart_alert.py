"""
Smart Alerting — keyword triggers, network triggers, webcam triggers.
"""
import json
import asyncio
from pathlib import Path
from loguru import logger

ALERT_CONFIG = Path.home() / ".config" / "rav-spy" / "alerts.json"

_alerts = {}


def _load():
    global _alerts
    if ALERT_CONFIG.exists():
        try:
            _alerts = json.loads(ALERT_CONFIG.read_text())
        except Exception:
            _alerts = {}


def _save():
    ALERT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    ALERT_CONFIG.write_text(json.dumps(_alerts, indent=2))


def config_set(key: str, value: str) -> str:
    _load()
    _alerts[key] = value
    _save()
    return f"Alert '{key}' set to: {value}"


def config_get(key: str = None) -> str:
    _load()
    if key:
        val = _alerts.get(key, "not set")
        return f"Alert '{key}': {val}"
    if not _alerts:
        return "Belum ada alert configured."
    lines = ["🔔 Alert Configuration:"]
    for k, v in _alerts.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def config_delete(key: str) -> str:
    _load()
    if key in _alerts:
        del _alerts[key]
        _save()
        return f"Alert '{key}' dihapus."
    return f"Alert '{key}' tidak ditemukan."


def silence(seconds: int = 300) -> str:
    _load()
    _alerts["_silenced_until"] = __import__("time").time() + seconds
    _save()
    return f"Alert silenced for {seconds}s."


def is_silenced() -> bool:
    silenced_until = _alerts.get("_silenced_until", 0)
    return __import__("time").time() < silenced_until
