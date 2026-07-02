"""
Custom Command Aliases — user-defined shortcuts for multi-command sequences.
"""
import json
from pathlib import Path
from loguru import logger

ALIAS_FILE = Path.home() / ".config" / "rav-spy" / "aliases.json"

class AliasManager:
    def __init__(self):
        self.aliases = self._load()

    def _load(self) -> dict:
        if ALIAS_FILE.exists():
            try:
                with open(ALIAS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        ALIAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ALIAS_FILE, "w") as f:
            json.dump(self.aliases, f, indent=2)

    def set(self, name: str, command: str) -> str:
        self.aliases[name.lower()] = command
        self._save()
        return f"Alias '!{name}' -> {command}"

    def get(self, name: str):
        return self.aliases.get(name.lower())

    def list_aliases(self) -> str:
        if not self.aliases:
            return "Belum ada alias."
        lines = ["Daftar Alias:"]
        for name, cmd in sorted(self.aliases.items()):
            lines.append(f"  !{name} -> {cmd}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        if name.lower() in self.aliases:
            del self.aliases[name.lower()]
            self._save()
            return f"Alias '{name}' dihapus."
        return f"Alias '{name}' tidak ditemukan."

alias_manager = AliasManager()
