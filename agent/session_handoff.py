import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

SESSION_DIR = Path.home() / ".config/rav-spy/sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

def save_session(name: str) -> str:
    import psutil
    windows = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if proc.info["create_time"]:
                windows.append({"pid": proc.info["pid"], "name": proc.info["name"],
                                "started": datetime.fromtimestamp(proc.info["create_time"]).isoformat()})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    data = {"name": name, "saved_at": datetime.now().isoformat(), "processes": windows}
    path = SESSION_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    return f"💾 Session '{name}' disimpan ({len(windows)} proses)."

def list_sessions() -> str:
    files = sorted(SESSION_DIR.glob("*.json"))
    if not files:
        return "Belum ada session tersimpan."
    lines = ["📋 Session tersimpan:"]
    for f in files:
        name = f.stem
        data = json.loads(f.read_text())
        lines.append(f"  {name} ({data.get('saved_at', '?')[:10]})")
    return "\n".join(lines)

def restore_session(name: str) -> str:
    path = SESSION_DIR / f"{name}.json"
    if not path.exists():
        return f"Session '{name}' tidak ditemukan."
    data = json.loads(path.read_text())
    restarted = 0
    for p in data.get("processes", []):
        name = p.get("name", "")
        proc_name = name.lower().replace(".exe", "")
        if shutil.which(proc_name):
            try:
                subprocess.Popen([proc_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                restarted += 1
            except Exception:
                pass
    return f"🔄 Session '{name}' dipulihkan ({restarted}/{len(data.get('processes', []))} aplikasi)."

def delete_session(name: str) -> str:
    path = SESSION_DIR / f"{name}.json"
    if not path.exists():
        return f"Session '{name}' tidak ditemukan."
    path.unlink()
    return f"🗑️ Session '{name}' dihapus."
