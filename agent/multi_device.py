import json
from pathlib import Path
from datetime import datetime

DEVICE_DIR = Path.home() / ".config/rav-spy/devices"
DEVICE_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DEVICE_DIR / "registry.json"

def _load():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"devices": []}

def _save(data):
    DB_FILE.write_text(json.dumps(data, indent=2, default=str))

def register_device(name: str, ip: str = None) -> str:
    data = _load()
    for d in data["devices"]:
        if d["name"] == name:
            d["ip"] = ip or d["ip"]
            d["last_seen"] = datetime.now().isoformat()
            _save(data)
            return f"✅ Device '{name}' diperbarui."
    data["devices"].append({
        "name": name, "ip": ip or "", "registered": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat()
    })
    _save(data)
    return f"✅ Device '{name}' terdaftar."

def list_devices() -> str:
    data = _load()
    if not data["devices"]:
        return "Belum ada device terdaftar."
    lines = ["📱 Device terdaftar:"]
    for d in data["devices"]:
        ip = d.get("ip", "") or "-"
        seen = d.get("last_seen", "?")[:16]
        lines.append(f"  {d['name']:15s} IP: {ip:15s} Terakhir: {seen}")
    return "\n".join(lines)

def remove_device(name: str) -> str:
    data = _load()
    before = len(data["devices"])
    data["devices"] = [d for d in data["devices"] if d["name"] != name]
    if len(data["devices"]) == before:
        return f"Device '{name}' tidak ditemukan."
    _save(data)
    return f"🗑️ Device '{name}' dihapus."

def send_command(device: str, command: str) -> str:
    data = _load()
    dev = next((d for d in data["devices"] if d["name"] == device), None)
    if not dev:
        return f"Device '{device}' tidak dikenal."
    if not dev.get("ip"):
        return f"Device '{device}' tidak memiliki alamat IP. Daftarkan dengan IP."
    return f"📤 Perintah dikirim ke {device} ({dev['ip']}): {command}"
