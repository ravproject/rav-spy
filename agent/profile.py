import json
import subprocess
import shutil
from pathlib import Path

PROFILE_DIR = Path.home() / ".config/rav-spy/profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = PROFILE_DIR / "profiles.json"
ACTIVE_FILE = PROFILE_DIR / "active.txt"

def _load():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"profiles": []}

def _save(data):
    DB_FILE.write_text(json.dumps(data, indent=2, default=str))

def create_profile(name: str, apps: list[str] = None, power: str = "balanced", theme: str = None) -> str:
    data = _load()
    for p in data["profiles"]:
        if p["name"] == name:
            return f"Profile '{name}' sudah ada."
    data["profiles"].append({
        "name": name, "apps": apps or [], "power": power, "theme": theme
    })
    _save(data)
    return f"✅ Profile '{name}' dibuat (apps: {len(apps or [])}, power: {power})."

def list_profiles() -> str:
    data = _load()
    if not data["profiles"]:
        return "Belum ada profile."
    active = _get_active()
    lines = ["👤 Profile tersedia:"]
    for p in data["profiles"]:
        marker = " ◀ AKTIF" if p["name"] == active else ""
        lines.append(f"  {p['name']}{marker}")
    return "\n".join(lines)

def _get_active():
    if ACTIVE_FILE.exists():
        return ACTIVE_FILE.read_text().strip()
    return None

def apply_profile(name: str) -> str:
    data = _load()
    profile = next((p for p in data["profiles"] if p["name"] == name), None)
    if not profile:
        return f"Profile '{name}' tidak ditemukan."
    launched = 0
    for app in profile.get("apps", []):
        if shutil.which(app):
            try:
                subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                launched += 1
            except Exception:
                pass
    ACTIVE_FILE.write_text(name)
    return f"🔄 Profile '{name}' diterapkan ({launched} app diluncurkan, power: {profile.get('power', 'balanced')})."

def delete_profile(name: str) -> str:
    data = _load()
    before = len(data["profiles"])
    data["profiles"] = [p for p in data["profiles"] if p["name"] != name]
    if len(data["profiles"]) == before:
        return f"Profile '{name}' tidak ditemukan."
    _save(data)
    if _get_active() == name:
        ACTIVE_FILE.unlink(missing_ok=True)
    return f"🗑️ Profile '{name}' dihapus."
