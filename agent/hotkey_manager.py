"""
Hotkey Manager — create/list/delete global hotkeys (via xdotool or custom scripts).
"""
import json
import subprocess
import shutil
from pathlib import Path
from loguru import logger

HOTKEY_DIR = Path.home() / ".config" / "rav-spy" / "hotkeys"

class HotkeyManager:
    def __init__(self):
        HOTKEY_DIR.mkdir(parents=True, exist_ok=True)
        self.hotkeys = self._load()

    def _load(self) -> dict:
        f = HOTKEY_DIR / "hotkeys.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return {}

    def _save(self):
        with open(HOTKEY_DIR / "hotkeys.json", "w") as f:
            json.dump(self.hotkeys, f, indent=2)

    def create(self, name: str, key_combo: str) -> str:
        self.hotkeys[name.lower()] = key_combo
        self._save()
        return f"⌨️ Hotkey '{name}' -> {key_combo}"

    def list_hotkeys(self) -> str:
        if not self.hotkeys:
            return "Belum ada hotkey."
        lines = ["Daftar Hotkey:"]
        for name, combo in sorted(self.hotkeys.items()):
            lines.append(f"  {name}: {combo}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        if name.lower() in self.hotkeys:
            del self.hotkeys[name.lower()]
            self._save()
            return f"Hotkey '{name}' dihapus."
        return f"Hotkey '{name}' tidak ditemukan."

hotkey_manager = HotkeyManager()
