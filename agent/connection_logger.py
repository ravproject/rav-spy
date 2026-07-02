"""
Connection Logger — passive monitoring of TCP connections, DNS queries.
"""
import os
import json
import subprocess
import asyncio
from pathlib import Path
from datetime import datetime
from loguru import logger

CONN_LOG = Path.home() / ".config" / "rav-spy" / "connections.jsonl"
_logging_active = False
_log_task = None


def _tcp_connections() -> list[dict]:
    try:
        res = subprocess.run(["ss", "-tup", "-H"], capture_output=True, text=True, timeout=5)
        connections = []
        for line in res.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 5:
                connections.append({
                    "proto": parts[0],
                    "local": parts[4] if len(parts) > 4 else "",
                    "remote": parts[5] if len(parts) > 5 else "",
                    "state": parts[1] if len(parts) > 1 else "",
                })
        return connections
    except Exception:
        return []


def snapshot() -> str:
    conns = _tcp_connections()
    lines = ["🔌 Active TCP Connections:"]
    for c in conns[:20]:
        lines.append(f"  {c['proto']} {c['local']} → {c['remote']} [{c['state']}]")
    return "\n".join(lines)


def _log_connections():
    try:
        conns = _tcp_connections()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "count": len(conns),
            "connections": conns[:30],
        }
        CONN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CONN_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"Connection log error: {e}")


async def start(interval: int = 60):
    global _logging_active, _log_task
    if _logging_active:
        return "Connection logging sudah aktif."

    _logging_active = True

    async def _loop():
        while _logging_active:
            _log_connections()
            await asyncio.sleep(interval)

    _log_task = asyncio.create_task(_loop())
    return f"Connection logging started (interval: {interval}s)"


async def stop():
    global _logging_active, _log_task
    _logging_active = False
    if _log_task:
        _log_task.cancel()
        _log_task = None
    return "Connection logging stopped."


def export() -> str:
    if not CONN_LOG.exists():
        return "Belum ada data connection log."
    try:
        lines = CONN_LOG.read_text().strip().split("\n")
        total = len(lines)
        return f"📊 Connection Log: {total} entries\nPath: {CONN_LOG}"
    except Exception as e:
        return f"Error reading log: {e}"
