"""
Wi-Fi Surveillance — scan nearby APs, history, geolocation via BSSID.
"""
import subprocess
import json
import asyncio
from pathlib import Path
from loguru import logger

WIFI_LOG = Path.home() / ".config" / "rav-spy" / "wifi_history.json"


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def scan() -> str:
    output = _run(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi", "list"])
    if output.startswith("Error") or not output:
        output = _run(["iwlist", "scan"])
        if not output.startswith("Error") and output:
            return "📡 Wi-Fi Networks:\n  (iwlist output not formatted)"
        return "Tidak bisa scan Wi-Fi (nmcli tidak tersedia)."

    lines = ["📡 Wi-Fi Networks:"]
    for entry in output.split("\n"):
        if ":" in entry:
            parts = entry.split(":")
            ssid = parts[0] if parts[0] else "(hidden)"
            bssid = parts[1] if len(parts) > 1 else "?"
            signal = parts[2] if len(parts) > 2 else "?"
            security = parts[3] if len(parts) > 3 else "?"
            bars = "█" * (int(signal) // 20) if signal.isdigit() else "?"
            lines.append(f"  {bars} {ssid} ({signal}%) [{bssid}] 🔒{security}")
    return "\n".join(lines)


def known_networks() -> str:
    output = _run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"])
    if output.startswith("Error"):
        return "Tidak bisa membaca known networks."

    lines = ["📜 Known Networks:"]
    for entry in output.split("\n"):
        if "wifi" in entry.lower() or "wireless" in entry.lower():
            parts = entry.split(":")
            name = parts[0] if parts else "?"
            lines.append(f"  📶 {name}")
    return "\n".join(lines) if len(lines) > 1 else "Belum ada known networks."


def _save_scan():
    try:
        output = _run(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL", "dev", "wifi", "list"])
        if output.startswith("Error") or not output:
            return
        networks = []
        for line in output.split("\n"):
            if ":" in line:
                parts = line.split(":")
                networks.append({
                    "ssid": parts[0] or "(hidden)",
                    "bssid": parts[1] if len(parts) > 1 else "",
                    "signal": parts[2] if len(parts) > 2 else "0",
                })

        history = {"timestamp": __import__("datetime").datetime.now().isoformat(), "networks": networks}
        WIFI_LOG.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if WIFI_LOG.exists():
            existing = json.loads(WIFI_LOG.read_text())
            if isinstance(existing, list):
                existing = existing[-50:]
        if isinstance(existing, list):
            existing.append(history)
        else:
            existing = [history]
        WIFI_LOG.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        logger.error(f"WiFi log save: {e}")


def tracking(on: bool):
    if on:
        _save_scan()
        return "WiFi tracking: snapshot saved."
    return "WiFi tracking: log saved."
