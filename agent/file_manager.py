"""
Module for file management operations.
"""
import os
from pathlib import Path
from security.sanitizer import InputSanitizer
from loguru import logger

def list_files(path: str) -> str:
    """
    List files in a directory.
    """
    sanitizer = InputSanitizer()
    safe_path = sanitizer.sanitize_filepath(path)
    if not safe_path:
        return "❌ Path tidak diizinkan atau tidak valid."

    target = Path(safe_path)
    if not target.exists() or not target.is_dir():
        return "❌ Direktori tidak ditemukan."

    entries = []
    for item in sorted(target.iterdir()):
        if item.is_dir():
            entries.append(f"📁 {item.name}/")
        else:
            size = item.stat().st_size
            size_str = f"{size // 1024}KB" if size > 1024 else f"{size}B"
            entries.append(f"📄 {item.name} ({size_str})")

    return f"""📂 `{safe_path}`:
""" + """
""".join(entries[:50])  # Max 50 entries

def get_file(filepath: str) -> dict:
    """
    Get a file.
    """
    sanitizer = InputSanitizer()
    safe_path = sanitizer.sanitize_filepath(filepath)
    if not safe_path:
        return {"error": "Path tidak diizinkan."}

    target = Path(safe_path)
    if not target.exists() or not target.is_file():
        return {"error": "File tidak ditemukan."}



    # Cek ukuran (max 50MB)
    max_size = int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
    if target.stat().st_size > max_size:
        return {"error": "File terlalu besar (max 50MB)."}

    with open(target, "rb") as f:
        return {
            "filename": target.name,
            "data": f.read(),
            "mimetype": _guess_mimetype(target.suffix),
        }

def save_file(filename: str, content: bytes) -> str:
    """
    Save an uploaded file to the safe Downloads directory.
    """
    try:
        sanitizer = InputSanitizer()
        # Sanitize filename
        safe_name = "".join([c for c in filename if c.isalnum() or c in "._- "]).strip()
        if not safe_name:
            return "❌ Nama file tidak valid."
        
        save_dir = Path.home() / "Downloads" / "rav-spy"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = save_dir / safe_name
        
        # Security check: Ensure we stay within Downloads/rav-spy
        if not target_path.resolve().is_relative_to(save_dir.resolve()):
            return "❌ Path traversal terdeteksi."

        with open(target_path, "wb") as f:
            f.write(content)
        
        return f"✅ File berhasil disimpan di: `{target_path}`"
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        return f"❌ Gagal menyimpan file: {str(e)}"

def _guess_mimetype(suffix: str) -> str:
    mimetypes = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".log": "text/plain",
    }
    return mimetypes.get(suffix.lower(), "application/octet-stream")
