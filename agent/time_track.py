import json
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path.home() / ".config/rav-spy/timetrack"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "sessions.json"

def _load():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"active": None, "history": []}

def _save(data):
    DB_FILE.write_text(json.dumps(data, indent=2, default=str))

def _format_duration(seconds):
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def start_track(project: str):
    data = _load()
    now = datetime.now()
    data["active"] = {"project": project, "start": now.isoformat()}
    _save(data)
    return f"⏱️ Tracking dimulai untuk '{project}'."

def stop_track():
    data = _load()
    if not data["active"]:
        return "Tidak ada tracking aktif."
    now = datetime.now()
    start = datetime.fromisoformat(data["active"]["start"])
    elapsed = int((now - start).total_seconds())
    entry = {**data["active"], "end": now.isoformat(), "elapsed": elapsed}
    data["history"].append(entry)
    data["active"] = None
    _save(data)
    return f"⏱️ '{entry['project']}' selesai. Durasi: {_format_duration(elapsed)}."

def status_track():
    data = _load()
    if not data["active"]:
        return "Tidak ada tracking aktif."
    start = datetime.fromisoformat(data["active"]["start"])
    elapsed = int((datetime.now() - start).total_seconds())
    return f"⏱️ Tracking '{data['active']['project']}' berjalan: {_format_duration(elapsed)}."

def report_track(days: int = 7):
    data = _load()
    cutoff = datetime.now() - timedelta(days=days)
    total = 0
    projects = {}
    for e in data["history"]:
        end = datetime.fromisoformat(e["end"])
        if end >= cutoff:
            total += e["elapsed"]
            p = e["project"]
            projects[p] = projects.get(p, 0) + e["elapsed"]
    lines = [f"📊 Laporan {days} hari terakhir:"]
    lines.append(f"Total: {_format_duration(total)}")
    for p, s in sorted(projects.items(), key=lambda x: -x[1]):
        pct = s / total * 100 if total else 0
        lines.append(f"  {p}: {_format_duration(s)} ({pct:.0f}%)")
    return "\n".join(lines)
