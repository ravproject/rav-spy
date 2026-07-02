"""
Scheduler — schedule commands to run at specified times or intervals.
"""
import os
import json
import asyncio
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta, date
from loguru import logger

SCHEDULE_FILE = Path.home() / ".config" / "rav-spy" / "schedules.json"

scheduled_alerts: list = []
scheduled_files: list = []

class Scheduler:
    def __init__(self):
        self.schedules = self._load()
        self._wake_event = asyncio.Event()

    def _load(self) -> list:
        if SCHEDULE_FILE.exists():
            try:
                with open(SCHEDULE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(self.schedules, f, indent=2)

    def add(self, command: str, time_str: str, repeat: str | None = None) -> str:
        now = datetime.now()
        target = None
        try:
            time_str = time_str.lower().strip()
            if time_str.startswith("in "):
                parts = time_str[3:].strip().split()
                if parts:
                    match = re.match(r"(\d+)", parts[0])
                    val = int(match.group(1)) if match else 0
                    if "jam" in time_str or parts[-1].endswith("h"):
                        target = now + timedelta(hours=val)
                    elif "menit" in time_str or parts[-1].endswith("m"):
                        target = now + timedelta(minutes=val)
                    elif "detik" in time_str or parts[-1].endswith("s"):
                        target = now + timedelta(seconds=val)
            elif ":" in time_str:
                parts_ = time_str.split(":")
                target = now.replace(hour=int(parts_[0]), minute=int(parts_[1]), second=0)
                if target < now:
                    target += timedelta(days=1)
        except Exception as e:
            return f"Format waktu salah: {e}. Contoh: in 30m, 14:30"
        if not target:
            return "Format waktu tidak dikenal. Contoh: in 30m, 14:30"

        parsed_repeat = repeat
        if parsed_repeat is None and "weekday" in time_str:
            parsed_repeat = "weekday"
            if ":" in time_str:
                tpart = time_str.split()[-1]
                parts_t = tpart.split(":")
                target = now.replace(hour=int(parts_t[0]), minute=int(parts_t[1]), second=0)
                if target < now:
                    target += timedelta(days=1)
            else:
                target = now + timedelta(hours=1)

        entry = {
            "id": len(self.schedules) + 1,
            "command": command,
            "time": target.isoformat(),
            "created": now.isoformat(),
            "done": False,
            "repeat": parsed_repeat
        }
        self.schedules.append(entry)
        self._save()
        self._wake_event.set()
        repeat_info = f" (ulang: {parsed_repeat})" if parsed_repeat else ""
        return f"📅 Terjadwal: '{command}' pada {target.strftime('%H:%M %d/%m/%Y')}{repeat_info}"

    def _next_repeat(self, entry: dict) -> datetime | None:
        repeat = entry.get("repeat")
        if not repeat:
            return None
        try:
            current = datetime.fromisoformat(entry["time"])
        except Exception:
            return None
        now = datetime.now()

        if repeat == "daily":
            nxt = current + timedelta(days=1)
            return nxt
        elif repeat == "hourly":
            nxt = current + timedelta(hours=1)
            return nxt
        elif repeat == "weekday":
            nxt = current + timedelta(days=1)
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
            return nxt
        elif re.match(r"^\d+[mh]$", repeat):
            val = int(repeat[:-1])
            unit = repeat[-1]
            delta = timedelta(minutes=val) if unit == "m" else timedelta(hours=val)
            nxt = now + delta
            return nxt
        elif re.match(r"^\d+d$", repeat):
            nxt = current + timedelta(days=int(repeat[:-1]))
            return nxt

        return None

    def list_schedules(self) -> str:
        if not self.schedules:
            return "Belum ada jadwal."
        lines = ["Daftar Jadwal:"]
        now = datetime.now()
        for s in self.schedules:
            status = "DONE" if s.get("done") else "PENDING"
            try:
                t = datetime.fromisoformat(s["time"])
                if not s.get("done") and now > t:
                    status = "LEWAT"
                rep = s.get("repeat")
                rep_info = f" [repeat: {rep}]" if rep else ""
                lines.append(f"  #{s['id']} [{status}] {s['command']} ({t.strftime('%H:%M %d/%m')}){rep_info}")
            except Exception:
                lines.append(f"  #{s['id']} [{status}] {s['command']}")
        return "\n".join(lines)

    def delete(self, schedule_id: int) -> str:
        for i, s in enumerate(self.schedules):
            if s["id"] == schedule_id:
                removed = self.schedules.pop(i)
                self._save()
                return f"Jadwal #{schedule_id} '{removed['command']}' dihapus."
        return f"Jadwal #{schedule_id} tidak ditemukan."

    async def check_loop(self, execute_func):
        while True:
            now = datetime.now()
            triggered = []
            for s in self.schedules:
                if s.get("done"):
                    continue
                try:
                    t = datetime.fromisoformat(s["time"])
                    if now >= t:
                        triggered.append(s)
                except Exception:
                    pass

            for entry in triggered:
                try:
                    result = await execute_func(entry["command"])
                    cmd = entry["command"]

                    if isinstance(result, bytes) and len(result) > 100:
                        is_video = "video" in cmd.lower() or "vid" in cmd.lower() or "record" in cmd.lower()
                        ftype = "video" if is_video else "photo"
                        icon = "🎥" if is_video else "📸"
                        lbl = "Video" if is_video else "Foto"
                        fid = len(scheduled_files) + 1
                        scheduled_files.append({
                            "id": fid, "type": ftype, "data": result,
                            "caption": f"Scheduled: {cmd}",
                            "filename": "scheduled.mp4" if is_video else "scheduled.jpg",
                            "command": cmd
                        })
                        scheduled_alerts.append(f"{icon} [{cmd}]: {lbl} tersedia")

                    elif isinstance(result, str) and result:
                        scheduled_alerts.append(f"✅ [{cmd}]: {result}")

                    elif isinstance(result, dict):
                        res_type = result.get("type", "")
                        caption = result.get("caption", "")
                        content = result.get("content", "")

                        if res_type in ("photo", "video", "document", "audio"):
                            if isinstance(content, dict):
                                data = content.get("data", b"")
                                filename = content.get("filename", f"scheduled.{res_type}")
                                mimetype = content.get("mimetype", "")
                            elif isinstance(content, bytes):
                                data = content
                                filename = f"scheduled.{res_type}"
                                mimetype = ""
                            else:
                                data = result.get("data", b"")
                                filename = f"scheduled.{res_type}"
                                mimetype = ""

                            if isinstance(data, bytes) and len(data) > 100:
                                icons = {"photo": "📸", "video": "🎥", "document": "📄", "audio": "🎵"}
                                labels = {"photo": "Foto", "video": "Video", "document": "File", "audio": "Audio"}
                                fid = len(scheduled_files) + 1
                                scheduled_files.append({
                                    "id": fid, "type": res_type, "data": data,
                                    "filename": filename, "mimetype": mimetype,
                                    "caption": caption or f"Scheduled: {cmd}",
                                    "command": cmd
                                })
                                scheduled_alerts.append(f"{icons.get(res_type, '📎')} [{cmd}]: {labels.get(res_type, 'File')} tersedia")
                        else:
                            text = caption or content
                            if isinstance(text, str) and text:
                                scheduled_alerts.append(f"✅ [{cmd}]: {text[:200]}")
                            else:
                                scheduled_alerts.append(f"✅ [{cmd}]: executed")
                    else:
                        scheduled_alerts.append(f"✅ [{cmd}]: executed")

                    logger.info(f"Scheduled command executed: {cmd}")
                except Exception as e:
                    err_msg = f"❌ [{entry['command']}]: {e}"
                    scheduled_alerts.append(err_msg)
                    logger.error(f"Failed to execute scheduled command: {e}")

                if entry.get("repeat"):
                    nxt = self._next_repeat(entry)
                    if nxt:
                        entry["time"] = nxt.isoformat()
                        entry["done"] = False
                        scheduled_alerts.append(f"🔁 [{entry['command']}] dijadwalkan ulang: {nxt.strftime('%H:%M %d/%m')}")
                        logger.info(f"Rescheduled '{entry['command']}' to {nxt.strftime('%H:%M %d/%m/%Y')}")
                    else:
                        entry["done"] = True
                else:
                    entry["done"] = True

            if triggered:
                self._save()

            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

scheduler = Scheduler()
