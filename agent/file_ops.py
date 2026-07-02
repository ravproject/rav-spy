"""
File Operations — quick upload, recent files, content search, convert, organize, clean.
"""
import os
import shutil
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

from agent.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS, get_platform_paths

UPLOAD_DIR = Path.home() / "Downloads" / "rav-spy"

def quick_upload() -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return f"📁 Folder upload siap: {UPLOAD_DIR}\nKirim file dari HP untuk diupload ke folder ini."

EXCLUDE_DIRS = {"__pycache__", "node_modules", "venv", ".git", "__pycache__"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".cache"}

def recent_files(item_type: str = "files", count: int = 10) -> str:
    home = Path.home()
    count = min(count, 50)
    items = []
    for p in home.rglob("*"):
        if p.is_symlink():
            continue
        if any(part.startswith(".") or part in EXCLUDE_DIRS for part in p.parts):
            continue
        if item_type == "files" and p.is_file():
            if p.suffix.lower() in EXCLUDE_EXTS:
                continue
            items.append((p.stat().st_mtime, p))
        elif item_type == "folders" and p.is_dir():
            items.append((p.stat().st_mtime, p))
    items.sort(key=lambda x: x[0], reverse=True)
    top = items[:count]
    if not top:
        return f"Tidak ada {item_type} terbaru."
    lines = [f"📂 {item_type.title()} terbaru (terakhir {count}):"]
    for ts, p in top:
        dt = datetime.fromtimestamp(ts).strftime("%H:%M %d/%m")
        lines.append(f"  [{dt}] {p.relative_to(home) if p != home else p}")
    return "\n".join(lines)

def search_content(keyword: str, folder: str = None) -> str:
    search_root = Path(folder).expanduser() if folder else Path.home()
    if not search_root.exists():
        return f"❌ Folder tidak ditemukan: {folder or '~'}"
    results = []
    text_exts = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".xml",
                 ".html", ".css", ".cfg", ".conf", ".ini", ".log", ".csv", ".sh", ".env"}
    for p in search_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in text_exts:
            continue
        if any(part.startswith(".") or part in EXCLUDE_DIRS for part in p.parts):
            continue
        try:
            if p.stat().st_size > 1024 * 100:
                continue
            content = p.read_text(errors="ignore")
            if keyword.lower() in content.lower():
                rel = p.relative_to(search_root) if p != search_root else p.name
                results.append(f"📄 {rel}")
                if len(results) >= 20:
                    break
        except Exception:
            pass
    if not results:
        return f"🔍 Tidak ditemukan konten '{keyword}' di {search_root}."
    return f"🔍 Hasil pencarian '{keyword}' di {search_root}:\n" + "\n".join(results)

def convert_file(filepath: str, target_format: str) -> str:
    src = Path(filepath).expanduser()
    if not src.exists():
        return f"❌ File tidak ditemukan: {filepath}"
    target_format = target_format.lstrip(".")
    dst = src.with_suffix(f".{target_format}")
    if src.suffix[1:] == target_format:
        return f"File sudah dalam format .{target_format}"
    import subprocess
    if shutil.which("pandoc"):
        try:
            res = subprocess.run(["pandoc", str(src), "-o", str(dst)], capture_output=True, text=True, timeout=30)
            if dst.exists():
                return f"✅ Konversi selesai: {dst}"
            return f"❌ Gagal konversi: {res.stderr[:200]}"
        except Exception as e:
            return f"❌ Error konversi: {e}"
    if shutil.which("ffmpeg") and src.suffix[1:] in ("mp3", "wav", "ogg", "flac") and target_format in ("mp3", "wav", "ogg", "flac"):
        try:
            subprocess.run(["ffmpeg", "-i", str(src), str(dst), "-y"], capture_output=True, timeout=60)
            return f"✅ Konversi audio: {dst}"
        except Exception as e:
            return f"❌ Gagal konversi audio: {e}"
    return f"❌ Tidak ada converter untuk {src.suffix} → .{target_format}. Install pandoc atau ffmpeg."

def organize_folder(folder: str, method: str = "type") -> str:
    target = Path(folder).expanduser()
    if not target.exists():
        return f"❌ Folder tidak ditemukan: {folder}"
    if not target.is_dir():
        return f"❌ Bukan folder: {folder}"
    files = [f for f in target.iterdir() if f.is_file()]
    if not files:
        return f"Folder {folder} kosong."
    moved = 0
    for f in files:
        try:
            if method == "type":
                subfolder = f.suffix[1:].lower() or "no_ext"
            elif method == "date":
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                subfolder = mtime.strftime("%Y-%m")
            else:
                return "Metode tidak dikenal. Gunakan: type, date"
            dest_dir = target / subfolder
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(f), str(dest_dir / f.name))
            moved += 1
        except Exception as e:
            logger.error(f"Gagal memindah {f.name}: {e}")
    return f"📂 {moved} file diorganisir ke subfolder berdasarkan {method} di {target}."

def _get_clean_dirs() -> list[Path]:
    paths = get_platform_paths()
    dirs = [Path(tempfile.gettempdir())]
    if IS_LINUX:
        dirs += [Path.home() / ".cache", Path.home() / ".local/share/Trash"]
    elif IS_MACOS:
        dirs += [Path.home() / "Library/Caches", Path.home() / ".Trash"]
    elif IS_WINDOWS:
        dirs += [Path(os.environ.get("TEMP", "C:\\Windows\\Temp")),
                 Path.home() / "AppData/Local/Temp"]
    return dirs


def clean_disk(scope: str = "all") -> str:
    freed = 0
    reports = []
    if scope in ("temp", "all"):
        for d in _get_clean_dirs():
            if d.exists():
                try:
                    size_before = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                    shutil.rmtree(d, ignore_errors=True)
                    d.mkdir(exist_ok=True)
                    freed += size_before
                    reports.append(f"🧹 {d}: {size_before // 1024 // 1024} MB")
                except Exception as e:
                    reports.append(f"⚠️ {d}: {e}")
    if scope in ("cache", "all"):
        pip_cache = Path.home() / ".cache/pip"
        if IS_WINDOWS:
            pip_cache = Path.home() / "AppData/Local/pip/cache"
        if pip_cache.exists():
            try:
                size = sum(f.stat().st_size for f in pip_cache.rglob("*") if f.is_file())
                shutil.rmtree(pip_cache, ignore_errors=True)
                freed += size
                reports.append(f"🧹 pip cache: {size // 1024 // 1024} MB")
            except Exception:
                pass
        npm_cache = Path.home() / ".npm"
        if IS_WINDOWS:
            npm_cache = Path(os.environ.get("APPDATA", "")) / "npm-cache"
        if npm_cache.exists():
            try:
                size = sum(f.stat().st_size for f in npm_cache.rglob("*") if f.is_file())
                shutil.rmtree(npm_cache, ignore_errors=True)
                freed += size
                reports.append(f"🧹 npm cache: {size // 1024 // 1024} MB")
            except Exception:
                pass
    if scope in ("duplicates", "all"):
        home = Path.home()
        seen = {}
        dupe_count = 0
        dupe_size = 0
        for p in home.rglob("*"):
            if p.is_file() and p.stat().st_size > 1024:
                try:
                    h = hashlib.md5(p.read_bytes()[:4096]).hexdigest()
                    key = (p.name, p.stat().st_size, h)
                    if key in seen:
                        dupe_count += 1
                        dupe_size += p.stat().st_size
                    else:
                        seen[key] = p
                except Exception:
                    pass
        if dupe_count:
            freed += dupe_size
            reports.append(f"🧹 Duplikat: {dupe_count} file ({dupe_size // 1024 // 1024} MB)")
    if not reports:
        return "Tidak ada yang dibersihkan."
    freed_mb = freed // 1024 // 1024
    return f"✅ Pembersihan {scope} selesai:\n" + "\n".join(reports) + f"\n💾 Total: ~{freed_mb} MB dibebaskan."
