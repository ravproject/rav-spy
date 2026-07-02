"""
Fleet pairing — generate/apply kode SPY1.* untuk hindari setup .env manual per mesin.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
from pathlib import Path

PAIR_PREFIX = "SPY1."


def detect_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def sanitize_agent_id(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in (name or "agent"))
    cleaned = cleaned.strip("-")[:32]
    return cleaned or "agent"


def encode_pairing_code(payload: dict) -> str:
    import base64

    raw = json.dumps(payload, separators=(",", ":")).encode()
    return PAIR_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_pairing_code(code: str) -> dict:
    trimmed = code.strip()
    if not trimmed.startswith(PAIR_PREFIX):
        raise ValueError("Kode pairing harus diawali SPY1.")
    raw = trimmed[len(PAIR_PREFIX) :]
    import base64

    padded = raw + "=" * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode())


def pairing_code_from_env(hub_url: str | None = None) -> str:
    """Buat kode pairing dari .env hub yang sudah ada."""
    fk = os.environ.get("FLEET_PAIRING_KEY")
    if not fk:
        raise ValueError("FLEET_PAIRING_KEY tidak ada di .env — jalankan setup hub dulu.")

    port = os.environ.get("AGENT_PORT", "8765")
    url = hub_url or os.environ.get("HUB_URL") or f"http://{detect_lan_ip()}:{port}"

    payload = {
        "v": 1,
        "hub": url.rstrip("/"),
        "fk": fk,
        "otp": os.environ["OTP_SECRET_KEY"],
        "jwt": os.environ["JWT_SECRET_KEY"],
        "enc": os.environ["ENCRYPTION_KEY"],
        "uid": os.environ.get("ALLOWED_USER_IDS", ""),
    }
    return encode_pairing_code(payload)


def build_agent_env(pairing: dict, agent_id: str | None = None, agent_api_key: str | None = None) -> dict[str, str]:
    """Bangun isi .env untuk mesin agent dari payload pairing."""
    import platform

    aid = agent_id or sanitize_agent_id(platform.node())
    api_key = agent_api_key or secrets.token_urlsafe(32)

    return {
        "RAV_MODE": "agent",
        "TELEGRAM_BOT_TOKEN": "",
        "WHATSAPP_SESSION_PATH": "./sessions/wa_session",
        "OTP_SECRET_KEY": pairing["otp"],
        "JWT_SECRET_KEY": pairing["jwt"],
        "ALLOWED_USER_IDS": pairing.get("uid", ""),
        "ENCRYPTION_KEY": pairing["enc"],
        "FLEET_PAIRING_KEY": pairing["fk"],
        "HUB_URL": pairing["hub"],
        "AGENT_ID": aid,
        "AGENT_HOST": "localhost",
        "AGENT_PORT": "8765",
        "AGENT_BIND_HOST": "0.0.0.0",
        "AGENT_API_KEY": api_key,
        "NVIDIA_NIM_API_KEY": "",
        "AI_MODE_ENABLED": "false",
        "MAX_COMMANDS_PER_MINUTE": "10",
        "MAX_FILE_SIZE_MB": "50",
        "LOG_LEVEL": "INFO",
        "LOG_FILE": "./logs/audit.log",
    }


def write_env_file(env: dict[str, str], path: Path | None = None) -> Path:
    target = path or Path.cwd() / ".env"
    lines = "\n".join(f"{k}={v}" for k, v in env.items()) + "\n"
    target.write_text(lines)
    return target


def format_add_command(agent_id: str, api_key: str, host: str | None = None, port: int = 8765) -> str:
    ip = host or detect_lan_ip()
    return f"python scripts/manage_agents.py add {agent_id} {ip} {port} {api_key}"
