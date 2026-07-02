"""
Smart Clipboard — auto-detect clipboard data type and offer quick actions.
"""
import re
import json
from pathlib import Path
from datetime import datetime
from loguru import logger

CLIP_HISTORY_FILE = Path.home() / ".config" / "rav-spy" / "clip_history.json"

class SmartClipboard:
    def __init__(self):
        self.active = False
        self.history = self._load_history()

    def _load_history(self) -> list:
        if CLIP_HISTORY_FILE.exists():
            try:
                with open(CLIP_HISTORY_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        CLIP_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CLIP_HISTORY_FILE, "w") as f:
            json.dump(self.history[-100:], f, indent=2)

    def _detect_type(self, text: str) -> str:
        if not text:
            return "empty"
        if re.match(r"^https?://", text):
            return "url"
        if re.match(r"^[\w.+-]+@[\w-]+\.[\w.]+$", text):
            return "email"
        if re.match(r"^\d{10,}$", text):
            return "phone"
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", text):
            return "ip"
        if re.match(r"^[A-Za-z0-9+/=]{20,}$", text):
            return "base64"
        if text.startswith("{") and text.endswith("}"):
            try:
                json.loads(text)
                return "json"
            except Exception:
                pass
        if len(text) > 200:
            return "long_text"
        return "text"

    def start(self) -> str:
        self.active = True
        return "🧠 Smart Clipboard AKTIF. Tipe data terdeteksi otomatis."

    def stop(self) -> str:
        self.active = False
        return "🧠 Smart Clipboard NONAKTIF."

    def record(self, text: str) -> str:
        if not self.active:
            return ""
        clip_type = self._detect_type(text)
        entry = {
            "text": text[:500],
            "type": clip_type,
            "time": datetime.now().isoformat()
        }
        self.history.append(entry)
        self._save_history()
        type_labels = {
            "url": "🔗 URL", "email": "📧 Email", "phone": "📞 Telepon",
            "ip": "🌐 IP", "base64": "🔐 Base64", "json": "📋 JSON",
            "long_text": "📄 Teks Panjang", "text": "📝 Teks"
        }
        label = type_labels.get(clip_type, "📋")
        return f"{label} terdeteksi: {text[:100]}"

    def show_history(self, limit: int = 10) -> str:
        if not self.history:
            return "Belum ada riwayat clipboard."
        lines = [f"Riwayat Clipboard (terakhir {limit}):"]
        for entry in self.history[-limit:]:
            t = entry.get("time", "")[11:19] if entry.get("time") else ""
            clip_type = entry.get("type", "text")
            text = entry.get("text", "")[:80]
            lines.append(f"  [{t}] ({clip_type}) {text}")
        return "\n".join(lines)

smart_clip = SmartClipboard()
