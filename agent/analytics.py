"""
Usage Analytics Collector — mencatat pola penggunaan user.
"""
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

ANALYTICS_FILE = Path.home() / ".config" / "rav-spy" / "analytics" / "usage.json"


class UsageAnalytics:
    def __init__(self):
        ANALYTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if ANALYTICS_FILE.exists():
            with open(ANALYTICS_FILE) as f:
                self.data = json.load(f)
        else:
            self.data = {
                "command_counts": {},
                "hourly_usage": {str(h): 0 for h in range(24)},
                "total_commands": 0,
            }

    def _save(self):
        with open(ANALYTICS_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def record_command(self, command_name: str):
        hour = datetime.now().hour
        self.data["command_counts"][command_name] = self.data["command_counts"].get(command_name, 0) + 1
        self.data["hourly_usage"][str(hour)] = self.data["hourly_usage"].get(str(hour), 0) + 1
        self.data["total_commands"] += 1
        self._save()

    def get_peak_hours(self) -> list[int]:
        sorted_hours = sorted(
            self.data["hourly_usage"].items(),
            key=lambda x: -x[1],
        )
        return [int(h) for h, _ in sorted_hours[:3] if _ > 0]

    def get_most_used_features(self, limit: int = 5) -> list[tuple[str, int]]:
        sorted_cmds = sorted(
            self.data["command_counts"].items(),
            key=lambda x: -x[1],
        )
        return [(c, n) for c, n in sorted_cmds[:limit]]

    def get_total_commands(self) -> int:
        return self.data.get("total_commands", 0)


usage_analytics = UsageAnalytics()
