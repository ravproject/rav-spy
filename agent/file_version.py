"""
File Versioning — local file version control (snapshot-based).
"""
import os
import json
import shutil
import filecmp
from pathlib import Path
from datetime import datetime
from loguru import logger

VERSION_DIR = Path.home() / ".config" / "rav-spy" / "versions"
VERSION_INDEX = VERSION_DIR / "index.json"

class FileVersionManager:
    def __init__(self):
        VERSION_DIR.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()

    def _load_index(self) -> dict:
        if VERSION_INDEX.exists():
            try:
                with open(VERSION_INDEX) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self):
        with open(VERSION_INDEX, "w") as f:
            json.dump(self.index, f, indent=2)

    def commit(self, filepath: str) -> str:
        src = Path(filepath).expanduser()
        if not src.exists():
            return f"❌ File tidak ditemukan: {filepath}"
        if not src.is_file():
            return f"❌ Bukan file: {filepath}"
        key = str(src)
        if key not in self.index:
            self.index[key] = []
        versions = self.index[key]
        if versions:
            last_path = VERSION_DIR / versions[-1]["file"]
            if last_path.exists() and filecmp.cmp(str(src), str(last_path), shallow=False):
                return f"ℹ️ Tidak ada perubahan sejak versi terakhir: {src.name}"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_name = f"{src.stem}_{ts}{src.suffix}"
        ver_path = VERSION_DIR / safe_name
        shutil.copy2(str(src), str(ver_path))
        entry = {
            "version": len(versions) + 1,
            "file": safe_name,
            "timestamp": datetime.now().isoformat(),
            "size": src.stat().st_size,
        }
        versions.append(entry)
        if len(versions) > 20:
            old = versions.pop(0)
            old_path = VERSION_DIR / old["file"]
            if old_path.exists():
                old_path.unlink()
        self._save_index()
        return f"💾 Versi {len(versions)} tersimpan: {src.name}"

    def history(self, filepath: str) -> str:
        key = str(Path(filepath).expanduser())
        if key not in self.index or not self.index[key]:
            return f"Belum ada riwayat versi untuk: {filepath}"
        lines = [f"📜 Riwayat Versi: {Path(filepath).name}"]
        for v in self.index[key]:
            t = v.get("timestamp", "")[:16] if v.get("timestamp") else ""
            size_kb = v.get("size", 0) // 1024
            lines.append(f"  v{v['version']} [{t}] ({size_kb} KB)")
        return "\n".join(lines)

    def revert(self, filepath: str, version: int = None) -> str:
        key = str(Path(filepath).expanduser())
        if key not in self.index or not self.index[key]:
            return f"Tidak ada versi untuk: {filepath}"
        versions = self.index[key]
        if version is None or version > len(versions):
            version = len(versions)
        if version < 1:
            return "Nomor versi tidak valid."
        entry = versions[version - 1]
        ver_path = VERSION_DIR / entry["file"]
        if not ver_path.exists():
            return f"File versi {version} tidak ditemukan di penyimpanan."
        dst = Path(filepath).expanduser()
        shutil.copy2(str(ver_path), str(dst))
        return f"↩️ {dst.name} dikembalikan ke versi {version} ({entry.get('timestamp','')[:16]})."

    def status(self, filepath: str = None) -> str:
        if filepath:
            key = str(Path(filepath).expanduser())
            if key in self.index and self.index[key]:
                v = self.index[key][-1]
                return f"ℹ️ {Path(filepath).name}: versi terakhir v{v['version']} ({v.get('timestamp','')[:16]})"
            return "Belum ada versi tersimpan."
        if not self.index:
            return "Belum ada file yang di-versioning."
        lines = ["📊 Status Versioning:"]
        for path, versions in self.index.items():
            lines.append(f"  {Path(path).name}: {len(versions)} versi")
        return "\n".join(lines)

file_version_manager = FileVersionManager()
