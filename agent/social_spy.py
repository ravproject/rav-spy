"""
Social Media Activity Monitor — detect social media usage via active window tracking.
"""
import re
from datetime import datetime, timedelta
from loguru import logger

SOCIAL_PATTERNS = {
    "WhatsApp Web": ["web.whatsapp.com", "WhatsApp"],
    "Telegram Web": ["web.telegram.org"],
    "Instagram": ["instagram.com"],
    "Twitter/X": ["twitter.com", "x.com"],
    "Facebook": ["facebook.com", "fb.com"],
    "TikTok": ["tiktok.com"],
    "YouTube": ["youtube.com"],
    "Reddit": ["reddit.com"],
    "LinkedIn": ["linkedin.com"],
}

_activity_log = []


def _get_active_window() -> str:
    try:
        import subprocess
        res = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=3)
        return res.stdout.strip().lower() if res.stdout else ""
    except Exception:
        return ""


def detect_social() -> str:
    window = _get_active_window()
    if not window:
        return "Tidak bisa mendeteksi window aktif."

    found = []
    for platform, patterns in SOCIAL_PATTERNS.items():
        for p in patterns:
            if p.lower() in window:
                found.append(platform)
                break

    if found:
        return "👁️ Social Media Terdeteksi: " + ", ".join(found)
    return "Tidak ada social media terdeteksi."


def track():
    window = _get_active_window()
    now = datetime.now()
    for platform, patterns in SOCIAL_PATTERNS.items():
        for p in patterns:
            if p.lower() in window:
                _activity_log.append({
                    "platform": platform,
                    "timestamp": now.isoformat(),
                    "window": window,
                })
                return f"📝 Logged: {platform}"
    return None


def report(hours: int = 24) -> str:
    since = datetime.now() - timedelta(hours=hours)
    recent = [a for a in _activity_log if datetime.fromisoformat(a["timestamp"]) > since]

    if not recent:
        return f"Tidak ada aktivitas social media dalam {hours} jam terakhir."

    from collections import Counter
    platforms = Counter(a["platform"] for a in recent)
    lines = [f"📊 Social Media Activity ({hours}h):"]
    for platform, count in platforms.most_common():
        lines.append(f"  {platform}: {count}x")
    lines.append(f"Total: {len(recent)} events")
    return "\n".join(lines)
