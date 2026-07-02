"""
Email Monitoring — reads Thunderbird/Evolution local mail storage.
"""
import os
import mailbox
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

THUNDERBIRD_DIR = Path.home() / ".thunderbird"
EVOLUTION_DIR = Path.home() / ".local" / "share" / "evolution"


def _find_mbox_files(base: Path) -> list[Path]:
    mboxes = []
    if not base.exists():
        return mboxes
    try:
        for p in base.rglob("*.mbox"):
            if p.is_file():
                mboxes.append(p)
        for p in base.rglob("**/INBOX"):
            if p.is_file() and "Mail" in str(p):
                mboxes.append(p)
    except Exception:
        pass
    return mboxes


def recent(limit: int = 10, source: str = "thunderbird") -> str:
    if source == "thunderbird":
        profiles = list(THUNDERBIRD_DIR.glob("*.default*"))
        if not profiles:
            return "Tidak ada profil Thunderbird ditemukan."
        mboxes = _find_mbox_files(profiles[0])
    elif source == "evolution":
        mboxes = _find_mbox_files(EVOLUTION_DIR)
    else:
        return f"Source '{source}' tidak dikenal."

    if not mboxes:
        return f"Tidak ada mailbox ditemukan di {source}."

    results = []
    for mbox_path in mboxes[:3]:
        try:
            mbox = mailbox.mbox(str(mbox_path))
            for i, msg in enumerate(mbox):
                if i >= limit:
                    break
                subject = msg.get("Subject", "(no subject)")[:80]
                sender = msg.get("From", "?")[:50]
                date = msg.get("Date", "?")[:30]
                results.append({
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "mailbox": mbox_path.name,
                })
        except Exception as e:
            logger.error(f"Mailbox read error {mbox_path}: {e}")

    if not results:
        return f"Tidak bisa membaca email dari {source}."

    lines = [f"📧 Recent Emails ({source}):"]
    for r in results[:limit]:
        lines.append(f"  📩 [{r['mailbox']}] {r['subject']}")
        lines.append(f"     From: {r['from']}")
        lines.append(f"     🕐 {r['date']}")
    return "\n".join(lines)


def contacts() -> str:
    """Extract contacts from Thunderbird address book."""
    abooks = []
    for prof in THUNDERBIRD_DIR.glob("*.default*"):
        abooks.extend(prof.glob("*.mab"))
        abooks.extend(prof.glob("**/abook.*"))

    if not abooks:
        return "Tidak ada address book ditemukan."

    lines = ["👥 Contacts:"]
    for ab in abooks[:3]:
        try:
            import sqlite3
            copy_path = None
            import shutil
            import tempfile
            copy_path = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
            shutil.copy2(str(ab), copy_path)
            conn = sqlite3.connect(copy_path)
            cur = conn.cursor()
            try:
                cur.execute("SELECT displayName, primaryEmail FROM MOZ_CONTACTS LIMIT 30")
                for name, email in cur.fetchall():
                    if name or email:
                        lines.append(f"  👤 {name or '?'} <{email or '?'}>")
            except Exception:
                pass
            conn.close()
            try:
                os.unlink(copy_path)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Address book error: {e}")

    return "\n".join(lines) if len(lines) > 1 else "Tidak ada kontak ditemukan."
