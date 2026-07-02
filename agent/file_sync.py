"""
File Sync — two-way folder sync with cloud services (local mock + rclone support).
"""
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from loguru import logger

SYNC_DIR = Path.home() / ".config" / "rav-spy" / "sync"

class SyncManager:
    def __init__(self):
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        self.syncs = {}

    def sync_folder(self, folder: str, service: str = "local") -> str:
        target = Path(folder).expanduser()
        if not target.exists():
            return f"❌ Folder tidak ditemukan: {folder}"
        if service == "local":
            dest = SYNC_DIR / target.name
            try:
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(str(target), str(dest))
                size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
                return f"✅ Sinkronisasi lokal: {target.name} → rav-spy/sync/ ({size // 1024} KB)"
            except Exception as e:
                return f"❌ Gagal sinkronisasi: {e}"
        elif service in ("gdrive", "googledrive"):
            if shutil.which("rclone"):
                try:
                    res = subprocess.run(["rclone", "sync", str(target), f"{service}:{target.name}"],
                                         capture_output=True, text=True, timeout=120)
                    return f"✅ Sinkronisasi ke {service}: {target.name}\n{res.stdout[:200]}"
                except Exception as e:
                    return f"❌ Gagal sync ke {service}: {e}"
            return "rclone tidak terinstall. Install: sudo apt install rclone"
        return f"Service '{service}' belum didukung. Gunakan: local, gdrive"

sync_manager = SyncManager()
