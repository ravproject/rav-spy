"""
Browser Spy — extract browsing history, bookmarks, downloads, cookies from Chrome/Firefox.
Read-only SQLite access via temporary copy (never locks original DB).
"""
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

CHROME_PROFILES = [
    Path.home() / ".config" / "google-chrome" / "Default",
    Path.home() / ".config" / "chromium" / "Default",
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default",
    Path.home() / ".config" / "microsoft-edge" / "Default",
]
FIREFOX_PROFILES = list(Path.home() / ".mozilla" / "firefox" / "*.default*")


def _copy_db(src: Path) -> str | None:
    """Copy SQLite DB to temp file to avoid locking original."""
    if not src.exists():
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        shutil.copy2(str(src), tmp.name)
        return tmp.name
    except Exception as e:
        logger.error(f"DB copy error: {e}")
        return None


def _query(copy_path: str, query: str, params: tuple = ()) -> list:
    try:
        conn = sqlite3.connect(copy_path)
        conn.text_factory = str
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"SQLite query error: {e}")
        return []
    finally:
        try:
            os.unlink(copy_path)
        except Exception:
            pass


def history(limit: int = 30, since_hours: int = 0) -> str:
    results = []

    for profile in CHROME_PROFILES:
        hist_db = profile / "History"
        copy = _copy_db(hist_db)
        if not copy:
            continue
        since = (datetime.now() - timedelta(hours=since_hours)).timestamp() if since_hours else 0
        rows = _query(copy, """
            SELECT url, title, last_visit_time/1000000-11644473600, visit_count
            FROM urls WHERE last_visit_time/1000000-11644473600 > ?
            ORDER BY last_visit_time DESC LIMIT ?
        """, (since, limit))
        for url, title, ts, count in rows:
            results.append({
                "browser": "Chrome",
                "url": url,
                "title": title or "(no title)",
                "time": datetime.fromtimestamp(ts).isoformat() if ts else "?",
                "visits": count,
            })

    for pattern in FIREFOX_PROFILES:
        for prof in (Path.home() / ".mozilla" / "firefox").glob("*.default*"):
            hist_db = prof / "places.sqlite"
            copy = _copy_db(hist_db)
            if not copy:
                continue
            rows = _query(copy, """
                SELECT url, title, visit_date/1000000, visit_count
                FROM moz_places ORDER BY visit_date DESC LIMIT ?
            """, (limit,))
            for url, title, ts, count in rows:
                results.append({
                    "browser": "Firefox",
                    "url": url,
                    "title": title or "(no title)",
                    "time": datetime.fromtimestamp(ts).isoformat() if ts else "?",
                    "visits": count,
                })

    if not results:
        return "Tidak ada history browser ditemukan."

    lines = [f"📖 Browser History ({len(results)} entries):"]
    for r in results[:limit]:
        lines.append(f"  [{r['browser']}] {r['title'][:60]}")
        lines.append(f"         {r['url'][:80]}")
        lines.append(f"         🕐 {r['time']} ({r['visits']}x)")
    return "\n".join(lines)


def bookmarks() -> str:
    results = []

    for profile in CHROME_PROFILES:
        bm_db = profile / "Bookmarks"
        if not bm_db.exists():
            continue
        try:
            import json
            data = json.loads(bm_db.read_text())
            roots = data.get("roots", {})
            for key in ["bookmark_bar", "other"]:
                folder = roots.get(key, {})
                items = folder.get("children", [])
                for item in items:
                    if item.get("type") == "url":
                        results.append({
                            "browser": "Chrome",
                            "name": item.get("name", ""),
                            "url": item.get("url", ""),
                        })
        except Exception as e:
            logger.error(f"Bookmark parse error: {e}")

    for prof in (Path.home() / ".mozilla" / "firefox").glob("*.default*"):
        bm_db = prof / "places.sqlite"
        copy = _copy_db(bm_db)
        if not copy:
            continue
        rows = _query(copy, """
            SELECT p.url, b.title FROM moz_bookmarks b
            JOIN moz_places p ON b.fk = p.id
            WHERE b.type = 1 LIMIT 100
        """)
        for url, title in rows:
            results.append({"browser": "Firefox", "name": title or "", "url": url})

    if not results:
        return "Tidak ada bookmark ditemukan."

    lines = [f"🔖 Bookmarks ({len(results)}):"]
    for r in results[:30]:
        lines.append(f"  [{r['browser']}] {r['name'][:50]}")
        lines.append(f"         {r['url'][:80]}")
    return "\n".join(lines)


def downloads(limit: int = 20) -> str:
    results = []

    for profile in CHROME_PROFILES:
        hist_db = profile / "History"
        copy = _copy_db(hist_db)
        if not copy:
            continue
        rows = _query(copy, """
            SELECT target_path, current_path, start_time/1000000-11644473600, received_bytes, total_bytes
            FROM downloads ORDER BY start_time DESC LIMIT ?
        """, (limit,))
        for target, current, ts, received, total in rows:
            pct = f"{received / total * 100:.0f}%" if total else "?",
            results.append({
                "browser": "Chrome",
                "path": current or target or "?",
                "time": datetime.fromtimestamp(ts).isoformat() if ts else "?",
                "progress": pct[0] if isinstance(pct, tuple) else pct,
            })

    if not results:
        return "Tidak ada download history."

    lines = [f"⬇️ Downloads ({len(results)}):"]
    for r in results[:limit]:
        lines.append(f"  [{r['browser']}] {Path(r['path']).name}")
        lines.append(f"         {r['path'][:80]}")
        lines.append(f"         🕐 {r['time']} ({r['progress']})")
    return "\n".join(lines)
