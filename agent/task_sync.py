"""
Task Sync — synchronize tasks with external services (Todoist, Google Tasks, etc).
Initial implementation uses local JSON with API-ready structure.
"""
import json
import os
from pathlib import Path
from datetime import datetime

TASK_FILE = Path.home() / ".config" / "rav-spy" / "tasks.json"

class TaskManager:
    def __init__(self):
        self.tasks = self._load()

    def _load(self) -> list:
        if TASK_FILE.exists():
            try:
                with open(TASK_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_FILE, "w") as f:
            json.dump(self.tasks, f, indent=2)

    def add(self, text: str, deadline: str = None) -> str:
        task = {
            "id": len(self.tasks) + 1,
            "text": text,
            "done": False,
            "created": datetime.now().isoformat(),
            "deadline": deadline,
            "source": "rav-spy"
        }
        self.tasks.append(task)
        self._save()
        msg = f"Tugas ditambahkan: {text}"
        if deadline:
            msg += f" (deadline: {deadline})"
        return msg

    def list_tasks(self) -> str:
        if not self.tasks:
            return "Belum ada tugas."
        lines = ["Daftar Tugas:"]
        for t in self.tasks:
            status = "DONE" if t.get("done") else "PENDING"
            deadline = f" [{t['deadline']}]" if t.get("deadline") else ""
            lines.append(f"  #{t['id']} [{status}]{deadline} {t['text']}")
        return "\n".join(lines)

    def done(self, task_id: int) -> str:
        for t in self.tasks:
            if t["id"] == task_id:
                t["done"] = True
                self._save()
                return f"Tugas #{task_id} '{t['text']}' selesai."
        return f"Tugas #{task_id} tidak ditemukan."

    def delete(self, task_id: int) -> str:
        for i, t in enumerate(self.tasks):
            if t["id"] == task_id:
                removed = self.tasks.pop(i)
                self._save()
                return f"Tugas #{task_id} '{removed['text']}' dihapus."
        return f"Tugas #{task_id} tidak ditemukan."

task_manager = TaskManager()
