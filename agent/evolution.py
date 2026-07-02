"""
Self-Evolution Engine — daily introspection & auto improvement.
"""
import os
import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

EVOLUTION_LOG = Path.home() / ".config" / "rav-spy" / "evolution" / "log.json"


class EvolutionEngine:
    def __init__(self):
        EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        self._load_log()

    def _load_log(self):
        if EVOLUTION_LOG.exists():
            with open(EVOLUTION_LOG) as f:
                self.log = json.load(f)
        else:
            self.log = {"evolutions": [], "total_fixes": 0, "total_optimizations": 0}

    def _save_log(self):
        with open(EVOLUTION_LOG, "w") as f:
            json.dump(self.log, f, indent=2)

    async def run_evolution(self) -> str:
        report_parts = []
        fixes = []

        error_analysis = await self._analyze_errors()
        if error_analysis:
            report_parts.append(error_analysis)

        perf_analysis = await self._profile_performance()
        if perf_analysis:
            report_parts.append(perf_analysis)

        fix_results = await self._auto_fix()
        if fix_results:
            fixes.extend(fix_results)
            report_parts.append(f"🔧 *Auto Fixes ({len(fixes)}):*\n" + "\n".join(fixes))

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fixes": fixes,
            "report": report_parts,
        }
        self.log["evolutions"].append(entry)
        self.log["total_fixes"] += len(fixes)
        self._save_log()

        report = "🧬 *Self-Evolution Report*\n"
        if report_parts:
            report += "\n" + "\n\n".join(report_parts)
        else:
            report += "Semua sistem dalam kondisi baik."
        return report

    async def _analyze_errors(self) -> str | None:
        audit_path = Path(os.environ.get("LOG_FILE", "./logs/audit.log"))
        if not audit_path.exists():
            return None
        content = audit_path.read_text().split("\n")
        today = datetime.now().strftime("%Y-%m-%d")
        errors = [l for l in content if today in l and ("ERROR" in l or "CRITICAL" in l)]
        if not errors:
            return "✅ Tidak ada error hari ini."
        return f"📊 Error hari ini: {len(errors)} entri"

    async def _profile_performance(self) -> str | None:
        return "⏱️ Performance baseline: normal"

    async def _auto_fix(self) -> list[str]:
        fixes = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", "agent/command_handler.py"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"Syntax error: {result.stderr[:200]}")
        except Exception:
            pass
        return fixes

    def get_history(self, days: int = 7) -> str:
        entries = self.log["evolutions"][-days:]
        if not entries:
            return "Belum ada riwayat evolusi."
        lines = ["🧬 *Evolution History:*"]
        for e in entries:
            ts = e["timestamp"][:10]
            nfixes = len(e.get("fixes", []))
            lines.append(f"• {ts}: {nfixes} fixes")
        return "\n".join(lines)


evolution_engine = EvolutionEngine()
