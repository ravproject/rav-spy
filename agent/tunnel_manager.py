import subprocess
import shutil
from pathlib import Path
import json

TUNNEL_DIR = Path.home() / ".config/rav-spy/tunnels"
TUNNEL_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = TUNNEL_DIR / "tunnels.json"

def _load():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"tunnels": []}

def _save(data):
    DB_FILE.write_text(json.dumps(data, indent=2, default=str))

def create_tunnel(name: str, remote: str, remote_port: int, local_port: int = None) -> str:
    data = _load()
    for t in data["tunnels"]:
        if t["name"] == name:
            return f"Tunnel '{name}' sudah ada."
    data["tunnels"].append({
        "name": name, "remote": remote,
        "remote_port": remote_port,
        "local_port": local_port or remote_port
    })
    _save(data)
    return f"✅ Tunnel '{name}' dibuat: {remote}:{remote_port} -> local:{local_port or remote_port}"

def list_tunnels() -> str:
    data = _load()
    if not data["tunnels"]:
        return "Belum ada tunnel."
    lines = ["🔗 Tunnel tersimpan:"]
    for t in data["tunnels"]:
        lines.append(f"  {t['name']:15s} {t['remote']}:{t['remote_port']} -> local:{t['local_port']}")
    return "\n".join(lines)

def start_tunnel(name: str) -> str:
    if not shutil.which("ssh"):
        return "SSH tidak ditemukan."
    data = _load()
    t = next((x for x in data["tunnels"] if x["name"] == name), None)
    if not t:
        return f"Tunnel '{name}' tidak ditemukan."
    try:
        cmd = ["ssh", "-N", "-L", f"{t['local_port']}:localhost:{t['remote_port']}", t["remote"]]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"🔗 Tunnel '{name}' aktif: local:{t['local_port']} -> {t['remote']}:{t['remote_port']}"
    except Exception as e:
        return f"Gagal start tunnel: {e}"

def delete_tunnel(name: str) -> str:
    data = _load()
    before = len(data["tunnels"])
    data["tunnels"] = [t for t in data["tunnels"] if t["name"] != name]
    if len(data["tunnels"]) == before:
        return f"Tunnel '{name}' tidak ditemukan."
    _save(data)
    return f"🗑️ Tunnel '{name}' dihapus."
