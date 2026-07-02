"""
Network Reconnaissance — LAN scan, ARP table, open ports, network shares.
"""
import subprocess
import shutil
import re
import asyncio
from loguru import logger


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def arp_table() -> str:
    output = _run(["ip", "neigh", "show"])
    if not output or output.startswith("Error"):
        output = _run(["arp", "-a"])
    if not output or output.startswith("Error"):
        return "Tidak bisa membaca ARP table."
    
    lines = ["📡 ARP Table (LAN Devices):"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line.strip()}")
    return "\n".join(lines)


def routing_table() -> str:
    output = _run(["ip", "route"])
    if not output or output.startswith("Error"):
        output = _run(["netstat", "-rn"])
    if not output or output.startswith("Error"):
        return "Tidak bisa membaca routing table."

    lines = ["🌐 Routing Table:"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line.strip()}")
    return "\n".join(lines[:20])


def dns_info() -> str:
    output = _run(["resolvectl", "status"])
    if output.startswith("Error"):
        output = _run(["systemd-resolve", "--status"])
    if output.startswith("Error"):
        try:
            with open("/etc/resolv.conf") as f:
                output = f.read()
        except Exception:
            return "Tidak bisa membaca DNS info."
    
    return f"📖 DNS Configuration:\n  {output.strip()[:1000]}"


def active_ports() -> str:
    output = _run(["ss", "-tuln"])
    if output.startswith("Error"):
        output = _run(["netstat", "-tuln"])
    if output.startswith("Error"):
        return "Tidak bisa membaca port aktif."

    lines = ["🔌 Active Listening Ports:"]
    for line in output.split("\n"):
        if "LISTEN" in line or line.startswith("tcp") or line.startswith("udp"):
            lines.append(f"  {line.strip()}")
    return "\n".join(lines[:25])


def network_shares() -> str:
    if shutil.which("smbclient"):
        output = _run(["smbclient", "-L", "localhost", "-N"], timeout=5)
        if not output.startswith("Error"):
            return f"📁 Network Shares:\n  {output[:1000]}"
    return "📁 Network Shares: smbclient tidak tersedia."


def full_recon() -> str:
    sections = [
        "=" * 40,
        "📡 NETWORK RECONNAISSANCE REPORT",
        "=" * 40,
        "",
        arp_table(),
        "",
        routing_table(),
        "",
        dns_info(),
        "",
        active_ports(),
    ]
    return "\n".join(sections)
