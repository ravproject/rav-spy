"""
Reminder System — desktop + Telegram notification scheduler.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

REMINDER_FILE = Path.home() / ".config" / "rav-spy" / "reminders.json"

class ReminderManager:
    def __init__(self):
        self.reminders = self._load()

    def _load(self) -> list:
        if REMINDER_FILE.exists():
            try:
                with open(REMINDER_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        REMINDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REMINDER_FILE, "w") as f:
            json.dump(self.reminders, f, indent=2)

    def add(self, text: str, time_str: str) -> str:
        from agent.time_utils import parse_duration
        now = datetime.now()
        target = None
        try:
            ts = time_str.lower().strip()
            if ":" in ts:
                parts = ts.split(":")
                target = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0)
                if target < now:
                    target += timedelta(days=1)
            else:
                seconds = parse_duration(ts)
                target = now + timedelta(seconds=seconds)
        except Exception as e:
            return f"Format waktu tidak dikenal: {e}. Gunakan: '30m', '2jam', '14:30'"
        if not target:
            return "Format waktu tidak dikenal. Gunakan: '30m', '2jam', '14:30'"
        self.reminders.append({"text": text, "time": target.isoformat(), "done": False})
        self._save()
        return f"Pengingat: '{text}' pada {target.strftime('%H:%M %d/%m/%Y')}"

    def list_reminders(self) -> str:
        if not self.reminders:
            return "Tidak ada pengingat."
        lines = ["Daftar Pengingat:"]
        now = datetime.now()
        for i, r in enumerate(self.reminders, 1):
            status = "DONE" if r.get("done") else "PENDING"
            try:
                t = datetime.fromisoformat(r["time"])
                if not r.get("done") and now > t:
                    status = "LEWAT"
                lines.append(f"  {i}. [{status}] {r['text']} ({t.strftime('%H:%M %d/%m')})")
            except Exception:
                lines.append(f"  {i}. [{status}] {r['text']}")
        return "\n".join(lines)

    def delete(self, index: int) -> str:
        if 0 < index <= len(self.reminders):
            removed = self.reminders.pop(index - 1)
            self._save()
            return f"Pengingat '{removed['text']}' dihapus."
        return "Nomor tidak valid."

reminder_manager = ReminderManager()
reminder_alerts = []

def check_reminders():
    """Check due reminders, send alerts, and mark them as done."""
    now = datetime.now()
    triggered = []
    for r in reminder_manager.reminders:
        if not r.get("done"):
            try:
                t = datetime.fromisoformat(r["time"])
                if now >= t:
                    r["done"] = True
                    triggered.append(r["text"])
            except Exception:
                pass
    if triggered:
        reminder_manager._save()
        for text in triggered:
            reminder_alerts.append(f"⏰ Pengingat: {text}")
            try:
                from agent.notifier import send_notification
                if not send_notification("RAV-SPY Reminder", text):
                    logger.warning(f"Desktop notification failed for reminder: {text}")
            except Exception as e:
                logger.warning(f"Desktop notification error for reminder '{text}': {e}")
