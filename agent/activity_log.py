from pathlib import Path
from datetime import datetime, timedelta
import json

LOG_DIR = Path.home() / ".config/rav-spy/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_activity(action: str, detail: str = ""):
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"{today}.json"
    entries = []
    if log_file.exists():
        entries = json.loads(log_file.read_text())
    entries.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "action": action,
        "detail": detail
    })
    log_file.write_text(json.dumps(entries, indent=2))
    return len(entries)

def view_log(days: int = 1, action_filter: str = None, limit: int = 20) -> str:
    cutoff = datetime.now() - timedelta(days=days)
    all_entries = []
    for f in sorted(LOG_DIR.glob("*.json"), reverse=True):
        date_str = f.stem
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        entries = json.loads(f.read_text())
        for e in entries:
            if action_filter and action_filter.lower() not in e["action"].lower():
                continue
            all_entries.append((f"{date_str} {e['time']}", e["action"], e["detail"]))
    if not all_entries:
        return "Tidak ada aktivitas tercatat."
    lines = [f"📋 Log aktivitas ({days} hari terakhir):"]
    for ts, action, detail in all_entries[-limit:]:
        d = f" ({detail})" if detail else ""
        lines.append(f"  {ts} [{action}]{d}")
    return "\n".join(lines)
