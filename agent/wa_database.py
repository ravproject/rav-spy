"""
WA Database — persistent SQLite storage for messages, config, analytics.
Replaces ephemeral Baileys store + JSON config files.
Includes vector search via chromadb for semantic message retrieval.
"""
import os
import json
import sqlite3
import threading
import httpx
from pathlib import Path
from datetime import datetime
from loguru import logger

DB_DIR = Path.home() / ".config" / "rav-spy"
DB_FILE = DB_DIR / "wa_store.db"

# --- Optional Vector Search (chromadb) ---
HAS_CHROMA = False
_chroma_client = None
_chroma_collection = None
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    pass

_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            remote_jid TEXT NOT NULL,
            phone TEXT,
            sender TEXT,
            push_name TEXT,
            from_me INTEGER DEFAULT 0,
            content_type TEXT,
            content_text TEXT,
            content_json TEXT,
            media_path TEXT,
            timestamp TEXT,
            received_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_jid ON messages(remote_jid);
        CREATE INDEX IF NOT EXISTS idx_messages_phone ON messages(phone);
        CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_messages_from_me ON messages(from_me);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content_text, push_name, sender,
            content='messages',
            content_rowid='rowid'
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS auto_replies (
            phone TEXT PRIMARY KEY,
            prompt TEXT DEFAULT '',
            style TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS keyword_alerts (
            keyword TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS monitors (
            phone TEXT PRIMARY KEY,
            interval_sec INTEGER DEFAULT 60,
            last_status TEXT,
            last_seen TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_forward (
            jid TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            text TEXT NOT NULL,
            execute_at TEXT NOT NULL,
            executed INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    logger.info(f"WA DB initialized: {DB_FILE}")


def insert_message(msg: dict) -> bool:
    try:
        conn = _get_conn()
        content = msg.get("content", {})
        content_type = content.get("type", "unknown")
        content_text = ""
        if content_type == "text":
            content_text = content.get("text", "")
        elif content_type in ("image", "video"):
            content_text = content.get("caption", "") or ""
        elif content_type == "document":
            content_text = content.get("filename", "") or ""

        conn.execute(
            """INSERT OR IGNORE INTO messages
               (id, remote_jid, phone, sender, push_name, from_me,
                content_type, content_text, content_json, media_path, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.get("id"),
                msg.get("jid", ""),
                msg.get("phone", ""),
                msg.get("sender", ""),
                msg.get("pushName", ""),
                1 if msg.get("fromMe") else 0,
                content_type,
                content_text[:2000],
                json.dumps(content, default=str)[:5000],
                msg.get("mediaPath"),
                msg.get("timestamp"),
            ),
        )
        # Update FTS
        if content_text:
            rowid = conn.execute(
                "SELECT rowid FROM messages WHERE id = ?", (msg.get("id"),)
            ).fetchone()
            if rowid:
                try:
                    conn.execute(
                        "INSERT INTO messages_fts(rowid, content_text, push_name, sender) VALUES (?, ?, ?, ?)",
                        (rowid[0], content_text, msg.get("pushName", ""), msg.get("sender", "")),
                    )
                except sqlite3.IntegrityError:
                    conn.execute(
                        "UPDATE messages_fts SET content_text=?, push_name=?, sender=? WHERE rowid=?",
                        (content_text, msg.get("pushName", ""), msg.get("sender", ""), rowid[0]),
                    )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"DB insert_message: {e}")
        return False


def search_messages_db(keyword: str, limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        # Try FTS first
        rows = conn.execute(
            """SELECT m.* FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE messages_fts MATCH ?
               ORDER BY m.timestamp DESC
               LIMIT ?""",
            (keyword, limit),
        ).fetchall()
        if rows:
            return [_row_to_dict(r) for r in rows]
        # Fallback to LIKE
        pattern = f"%{keyword}%"
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE content_text LIKE ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (pattern, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"DB search: {e}")
        return []


def get_chat_history(jid: str, limit: int = 50, offset: int = 0) -> list[dict]:
    try:
        conn = _get_conn()
        if not jid.endswith("@"):
            pattern = f"%{jid}%"
            rows = conn.execute(
                """SELECT * FROM messages
                   WHERE remote_jid LIKE ? OR phone = ?
                   ORDER BY timestamp DESC
                   LIMIT ? OFFSET ?""",
                (pattern, jid, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM messages
                   WHERE remote_jid = ?
                   ORDER BY timestamp DESC
                   LIMIT ? OFFSET ?""",
                (jid, limit, offset),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"DB get_chat_history: {e}")
        return []


def get_all_chats() -> list[dict]:
    try:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT remote_jid, phone,
                      MAX(timestamp) as last_message_at,
                      COUNT(*) as message_count,
                      SUM(CASE WHEN from_me = 0 THEN 1 ELSE 0 END) as received_count
               FROM messages
               GROUP BY remote_jid
               ORDER BY last_message_at DESC"""
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"DB get_all_chats: {e}")
        return []


def get_message_stats(jid: str, limit: int = 200) -> dict:
    try:
        conn = _get_conn()
        if jid:
            jid_pattern = f"%{jid}%"
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE remote_jid LIKE ? OR phone = ?",
                (jid_pattern, jid),
            ).fetchone()[0]
            by_type = conn.execute(
                """SELECT content_type, COUNT(*) as cnt FROM messages
                   WHERE (remote_jid LIKE ? OR phone = ?)
                   GROUP BY content_type ORDER BY cnt DESC""",
                (jid_pattern, jid),
            ).fetchall()
            from_me = conn.execute(
                "SELECT SUM(from_me) as sent, SUM(1-from_me) as received FROM messages WHERE remote_jid LIKE ? OR phone = ?",
                (jid_pattern, jid),
            ).fetchone()
        else:
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            by_type = conn.execute(
                "SELECT content_type, COUNT(*) as cnt FROM messages GROUP BY content_type ORDER BY cnt DESC"
            ).fetchall()
            from_me = conn.execute(
                "SELECT SUM(from_me) as sent, SUM(1-from_me) as received FROM messages"
            ).fetchone()
        return {
            "total": total,
            "sent": int(from_me[0]) if from_me and from_me[0] else 0,
            "received": int(from_me[1]) if from_me and from_me[1] else 0,
            "by_type": {r[0]: r[1] for r in by_type},
        }
    except Exception as e:
        logger.error(f"DB get_message_stats: {e}")
        return {"total": 0, "sent": 0, "received": 0, "by_type": {}}


def get_activity_pattern(jid: str, limit: int = 200) -> dict:
    try:
        conn = _get_conn()
        jid_pattern = f"%{jid}%"
        rows = conn.execute(
            """SELECT timestamp FROM messages
               WHERE (remote_jid LIKE ? OR phone = ?) AND from_me = 0
               ORDER BY timestamp DESC LIMIT ?""",
            (jid_pattern, jid, limit),
        ).fetchall()
        hours = {}
        for r in rows:
            ts = r[0]
            if not ts:
                continue
            try:
                h = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
                hours[h] = hours.get(h, 0) + 1
            except Exception:
                pass
        peak_hour = max(hours, key=hours.get) if hours else None
        return {"hours": hours, "peak_hour": peak_hour}
    except Exception as e:
        logger.error(f"DB get_activity_pattern: {e}")
        return {"hours": {}, "peak_hour": None}


def export_chat_db(jid: str, limit: int = 200) -> list[dict]:
    return get_chat_history(jid, limit)


# --- Config CRUD ---

def config_get(key: str, default=None) -> str | None:
    try:
        r = _get_conn().execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return r[0] if r else default
    except Exception:
        return default


def config_set(key: str, value: str):
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)", (key, value)
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB config_set: {e}")


def config_delete(key: str):
    try:
        _get_conn().execute("DELETE FROM config WHERE key = ?", (key,))
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB config_delete: {e}")


# --- Auto-Reply CRUD ---

def auto_reply_get_all() -> dict:
    try:
        rows = _get_conn().execute("SELECT phone, prompt, style FROM auto_replies").fetchall()
        return {r[0]: {"prompt": r[1], "style": r[2]} for r in rows}
    except Exception:
        return {}


def auto_reply_set(phone: str, prompt: str = "", style: str = ""):
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO auto_replies(phone, prompt, style) VALUES (?, ?, ?)",
            (phone, prompt, style),
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB auto_reply_set: {e}")


def auto_reply_delete(phone: str):
    try:
        _get_conn().execute("DELETE FROM auto_replies WHERE phone = ?", (phone,))
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB auto_reply_delete: {e}")


# --- Keyword Alerts CRUD ---

def keyword_alerts_get_all() -> list[str]:
    try:
        rows = _get_conn().execute("SELECT keyword FROM keyword_alerts").fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def keyword_alert_add(keyword: str):
    try:
        _get_conn().execute(
            "INSERT OR IGNORE INTO keyword_alerts(keyword) VALUES (?)", (keyword.lower(),)
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB keyword_alert_add: {e}")


def keyword_alert_remove(keyword: str):
    try:
        _get_conn().execute(
            "DELETE FROM keyword_alerts WHERE keyword = ?", (keyword.lower(),)
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB keyword_alert_remove: {e}")


# --- Monitors CRUD ---

def monitors_get_all() -> dict:
    try:
        rows = _get_conn().execute("SELECT * FROM monitors").fetchall()
        return {
            r["phone"]: {
                "interval": r["interval_sec"],
                "last_status": r["last_status"],
                "last_seen": r["last_seen"],
            }
            for r in rows
        }
    except Exception:
        return {}


def monitor_save(phone: str, interval: int = 60, last_status: str = None, last_seen: str = None):
    try:
        _get_conn().execute(
            """INSERT OR REPLACE INTO monitors(phone, interval_sec, last_status, last_seen)
               VALUES (?, ?, ?, ?)""",
            (phone, interval, last_status, last_seen),
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB monitor_save: {e}")


def monitor_delete(phone: str):
    try:
        _get_conn().execute("DELETE FROM monitors WHERE phone = ?", (phone,))
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB monitor_delete: {e}")


# --- Forward Config CRUD ---

def forward_get_all() -> set:
    try:
        rows = _get_conn().execute(
            "SELECT jid FROM chat_forward WHERE enabled = 1"
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def forward_set(jid: str, enabled: bool = True):
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO chat_forward(jid, enabled) VALUES (?, ?)",
            (jid, 1 if enabled else 0),
        )
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB forward_set: {e}")


def forward_delete(jid: str):
    try:
        _get_conn().execute("DELETE FROM chat_forward WHERE jid = ?", (jid,))
        _get_conn().commit()
    except Exception as e:
        logger.error(f"DB forward_delete: {e}")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# --- Vector Search (chromadb) ---

def _init_chroma():
    global _chroma_client, _chroma_collection
    if not HAS_CHROMA:
        return False
    try:
        _chroma_client = chromadb.PersistentClient(path=str(DB_DIR / "chroma"))
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="wa_messages",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB initialized for WA vector search")
        return True
    except Exception as e:
        logger.warning(f"ChromaDB init failed: {e}")
        return False


async def _get_embedding(text: str) -> list[float] | None:
    """Get embedding from NVIDIA NIM API."""
    api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
                + "/embeddings",
                json={
                    "model": os.environ.get("NVIDIA_NIM_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5"),
                    "input": text,
                    "input_type": "query",
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return r.json()["data"][0]["embedding"]
    except Exception as e:
        logger.error(f"Embedding API error: {e}")
        return None


async def index_message_embedding(msg_id: str, text: str, metadata: dict | None = None):
    """Index a message embedding for semantic search."""
    if not HAS_CHROMA or _chroma_collection is None:
        if not _init_chroma():
            return
    embedding = await _get_embedding(text[:500])
    if not embedding:
        return
    try:
        _chroma_collection.add(
            ids=[msg_id],
            embeddings=[embedding],
            metadatas=[metadata or {"text": text[:200]}],
        )
    except Exception as e:
        logger.error(f"Chroma add error: {e}")


async def semantic_search(query: str, limit: int = 10) -> list[dict]:
    """Semantic search messages by meaning (not keyword)."""
    if not HAS_CHROMA or _chroma_collection is None:
        if not _init_chroma():
            return []
    embedding = await _get_embedding(query)
    if not embedding:
        return []
    try:
        results = _chroma_collection.query(
            query_embeddings=[embedding],
            n_results=limit,
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else []
        metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
        output = []
        for i, msg_id in enumerate(ids):
            msg = _get_conn().execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
            entry = {
                "id": msg_id,
                "score": round(1 - distances[i], 3) if i < len(distances) else 0,
            }
            if msg:
                entry.update(_row_to_dict(msg))
            elif i < len(metadatas):
                entry["content_text"] = metadatas[i].get("text", "")
            output.append(entry)
        return output
    except Exception as e:
        logger.error(f"Chroma query error: {e}")
        return []


def close():
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None
