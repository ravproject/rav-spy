"""
WhatsApp Spy — monitor online/offline status kontak WhatsApp via Baileys (Node.js bridge).
Notifikasi otomatis ke Telegram saat status berubah.
Event-driven via WebSocket — lebih cepat dan ringan dari Playwright.
"""
import os
import time
import json
import asyncio
import subprocess
import signal
from pathlib import Path
from datetime import datetime
from loguru import logger

CONFIG_DIR = Path.home() / ".config" / "rav-spy"
QR_FILE = CONFIG_DIR / "whatsapp_qr.png"
BRIDGE_JS = Path(__file__).parent / "whatsapp" / "bridge.js"

from agent.wa_database import (
    init_db as _init_wa_db,
    insert_message as _db_insert_message,
    search_messages_db as _db_search_messages,
    get_chat_history as _db_chat_history,
    get_all_chats as _db_all_chats,
    get_message_stats as _db_message_stats,
    get_activity_pattern as _db_activity_pattern,
    export_chat_db as _db_export_chat,
    auto_reply_get_all as _db_auto_reply_get_all,
    auto_reply_set as _db_auto_reply_set,
    auto_reply_delete as _db_auto_reply_delete,
    keyword_alerts_get_all as _db_keyword_alerts,
    keyword_alert_add as _db_keyword_add,
    keyword_alert_remove as _db_keyword_remove,
    monitors_get_all as _db_monitors_get_all,
    monitor_save as _db_monitor_save,
    monitor_delete as _db_monitor_delete,
    forward_get_all as _db_forward_get_all,
    forward_set as _db_forward_set,
    forward_delete as _db_forward_delete,
    index_message_embedding as _db_index_embedding,
    semantic_search as _db_semantic_search,
)

_init_wa_db()

_bridge_proc = None
_bridge_lock = asyncio.Lock()
_bridge_connected = False
_qr_pending = False
_response_futures = {}
_active_monitors = {}


async def _telegram_send(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ALLOWED_USER_IDS", "").split(",")[0] if os.environ.get("ALLOWED_USER_IDS") else ""
    if not token or not chat_id:
        return False
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        return True
    except Exception as e:
        logger.error(f"Telegram send: {e}")
        return False


async def _telegram_photo(path: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ALLOWED_USER_IDS", "").split(",")[0] if os.environ.get("ALLOWED_USER_IDS") else ""
    if not token or not chat_id:
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            with open(path, "rb") as f:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id},
                    files={"photo": f},
                )
    except Exception as e:
        logger.error(f"Telegram photo: {e}")


def _generate_qr_image(qr_text: str) -> bool:
    try:
        import qrcode
        img = qrcode.make(qr_text)
        QR_FILE.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(QR_FILE))
        return True
    except ImportError:
        logger.warning("qrcode not installed, saving raw QR data")
        QR_FILE.parent.mkdir(parents=True, exist_ok=True)
        QR_FILE.write_text(qr_text)
        return False
    except Exception as e:
        logger.error(f"QR generate error: {e}")
        QR_FILE.parent.mkdir(parents=True, exist_ok=True)
        QR_FILE.write_text(qr_text)
        return False


_bridge_ready_event = asyncio.Event()
_qr_sent = False
_last_qr_data = None
_last_qr_ts = 0.0
_QR_MIN_INTERVAL = 30  # detik minimal antar pengiriman QR ke Telegram

async def _start_bridge():
    global _bridge_proc, _bridge_connected, _qr_pending, _qr_sent, _last_qr_data, _last_qr_ts

    if _bridge_proc and _bridge_proc.poll() is None:
        return

    _bridge_connected = False
    _qr_pending = False
    _qr_sent = False
    _last_qr_data = None
    _last_qr_ts = 0.0
    _bridge_ready_event.clear()

    # Hapus auth corrupt: jika creds.json ada tapi gak punya field 'me' (alias belom pairing selesai)
    auth_dir = CONFIG_DIR / "baileys_auth"
    if auth_dir.exists():
        creds_file = auth_dir / "creds.json"
        if creds_file.exists():
            try:
                creds = json.loads(creds_file.read_text())
                if not creds.get("me"):
                    import shutil
                    shutil.rmtree(str(auth_dir))
                    logger.info("Deleted partial/unregistered auth state")
            except Exception:
                pass

    _bridge_proc = subprocess.Popen(
        ["node", str(BRIDGE_JS)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    async def _read_stdout():
        global _bridge_connected, _qr_pending, _qr_sent, _last_qr_data, _last_qr_ts
        while _bridge_proc and _bridge_proc.poll() is None:
            line = await asyncio.get_event_loop().run_in_executor(None, _bridge_proc.stdout.readline)
            if not line:
                await asyncio.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "ready":
                if msg.get("status") != "initializing":
                    was_disconnected = not _bridge_connected
                    _bridge_connected = True
                    _qr_pending = False
                    _qr_sent = False
                    _last_qr_data = None
                    _bridge_ready_event.set()
                    if was_disconnected:
                        await _telegram_send("✅ WhatsApp Web berhasil terhubung!")

            elif mtype == "qr":
                logger.info("📱 QR received from bridge, setting ready event")
                _qr_pending = True
                _bridge_ready_event.set()
                now = time.time()
                if not _bridge_connected and msg["data"] != _last_qr_data and (now - _last_qr_ts) >= _QR_MIN_INTERVAL:
                    _last_qr_data = msg["data"]
                    _last_qr_ts = now
                    has_qrcode = _generate_qr_image(msg["data"])
                    if has_qrcode:
                        await _telegram_photo(str(QR_FILE))
                        await _telegram_send("📱 *WhatsApp Web Login*\nScan QR code di atas untuk menghubungkan WhatsApp.")
                    else:
                        await _telegram_send(f"📱 *WhatsApp Web Login*\nQR data: {msg['data'][:200]}...\nInstall 'pip install qrcode[pil]' untuk gambar QR.")

            elif mtype == "logged_out":
                _bridge_connected = False
                _qr_sent = False
                _last_qr_data = None
                _last_qr_ts = 0.0
                await _telegram_send("⚠️ WhatsApp session expired. Scan QR ulang dengan `!wa check <nomor>`.")

            elif mtype == "presence":
                jid = msg.get("jid", "")
                if jid and jid in _active_monitors:
                    await _handle_presence_update(jid, msg)

            elif mtype == "message":
                await _handle_incoming_message(msg)

            elif mtype == "story_update":
                await _handle_story_update(msg.get("data", {}))

            elif mtype == "forward":
                await _handle_forward_message(msg.get("data", {}))

            elif mtype == "message_update":
                logger.debug(f"Message update: {msg.get('id')} status={msg.get('status')}")

            elif mtype == "result":
                fut = _response_futures.get("last")
                if fut and not fut.done():
                    fut.set_result(msg.get("data"))

            elif mtype == "error":
                fut = _response_futures.get("last")
                if fut and not fut.done():
                    fut.set_result({"error": msg.get("message", "Unknown error")})

    async def _read_stderr():
        while _bridge_proc and _bridge_proc.poll() is None:
            line = await asyncio.get_event_loop().run_in_executor(None, _bridge_proc.stderr.readline)
            if line:
                stripped = line.strip()
                if stripped:
                    logger.warning(f"[bridge] {stripped}")

    asyncio.create_task(_read_stdout())
    asyncio.create_task(_read_stderr())

    try:
        await asyncio.wait_for(_bridge_ready_event.wait(), timeout=20)
    except asyncio.TimeoutError:
        logger.warning("Bridge initialization timed out (QR not emitted within 20s)")
    logger.info(f"_start_bridge returning: proc_alive={_bridge_proc.poll() is None}, connected={_bridge_connected}, qr={_qr_pending}")


async def _send_command(cmd: dict):
    async with _bridge_lock:
        await _start_bridge()
        if not _bridge_proc or not _bridge_proc.stdin:
            logger.warning("Bridge not available after start")
            return {"error": "Bridge not available"}

        logger.info(f"Bridge proc alive: {_bridge_proc.poll() is None}, connected={_bridge_connected}, qr={_qr_pending}")
        # Tunggu sampai bridge benar-benar connected, kecuali perintah status
        if cmd.get("type") in ("check", "subscribe", "monitor"):
            try:
                await asyncio.wait_for(_wait_connected(), timeout=25)
                logger.info(f"Wait connected done: connected={_bridge_connected}, qr={_qr_pending}")
            except asyncio.TimeoutError:
                logger.warning(f"Wait connected timed out after 25s: connected={_bridge_connected}, qr={_qr_pending}, proc_alive={_bridge_proc.poll() is None}")
                return {"error": "Bridge not connected after timeout"}

        fut = asyncio.get_event_loop().create_future()
        _response_futures["last"] = fut
        _bridge_proc.stdin.write(json.dumps(cmd) + "\n")
        _bridge_proc.stdin.flush()
        try:
            result = await asyncio.wait_for(fut, timeout=30)
            return result
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for bridge response"}
    return {"error": "Bridge not available"}


async def _wait_connected():
    while not _bridge_connected and not _qr_pending:
        if _bridge_proc and _bridge_proc.poll() is not None:
            break
        await asyncio.sleep(0.5)



async def _handle_presence_update(phone: str, msg: dict):
    status = msg.get("status")
    last_seen = msg.get("last_seen")
    ts = datetime.now().strftime("%H:%M:%S")
    prev = _active_monitors.get(phone, {}).get("last_status")

    if status == "online" and prev != "online":
        _active_monitors[phone]["last_status"] = "online"
        _active_monitors[phone]["last_seen"] = None
        await _save_monitors()
        await _telegram_send(f"🟢 *{phone}* AKTIF pada pukul {ts}")

    elif status == "offline" and prev == "online":
        _active_monitors[phone]["last_status"] = "offline"
        _active_monitors[phone]["last_seen"] = last_seen
        await _save_monitors()
        seen = last_seen or "tidak diketahui"
        await _telegram_send(f"🔴 *{phone}* OFFLINE pada pukul {ts}\n📅 Terakhir dilihat: {seen}")

    elif prev is None:
        _active_monitors[phone]["last_status"] = status
        _active_monitors[phone]["last_seen"] = last_seen
        await _save_monitors()


async def _handle_incoming_message(msg: dict):
    content = msg.get("content", {})
    ctype = content.get("type", "unknown")
    phone = msg.get("phone", "?")
    sender = msg.get("sender", "?")
    push_name = msg.get("pushName", "")
    ts = msg.get("timestamp", "")
    from_me = msg.get("fromMe", False)
    media_path = msg.get("mediaPath")

    _db_insert_message(msg)

    # Async vector indexing
    asyncio.create_task(_index_message_vector(msg))

    if from_me:
        return

    text = ""
    if ctype == "text":
        text = content.get("text", "")
    elif ctype == "image":
        text = f"🖼 Image: {content.get('caption', '(no caption)')}"
    elif ctype == "video":
        text = f"🎬 Video: {content.get('caption', '(no caption)')}"
    elif ctype == "audio":
        text = "🎵 Audio message"
    elif ctype == "document":
        text = f"📄 Document: {content.get('filename', 'file')}"
    elif ctype == "sticker":
        text = "🃏 Sticker"
    elif ctype == "contact":
        text = f"👤 Contact: {content.get('text', '')}"
    elif ctype == "location":
        text = f"📍 Location"
    else:
        text = f"📨 Message type: {ctype}"

    # Auto-reply + keyword alert (fire regardless of smart inbox)
    if ctype == "text" and text:
        asyncio.create_task(_process_keyword_alert(phone, text, push_name))
        asyncio.create_task(_process_auto_reply(phone, text, push_name))

    # Smart inbox: AI filter — skip notification if not important
    if _smart_inbox_active and ctype == "text" and text:
        api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
        if not api_key:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions",
                    json={
                        "model": os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct"),
                        "messages": [
                            {"role": "system", "content": f"Kamu filter pesan WhatsApp. Apakah pesan ini penting? Kriteria: {_smart_inbox_prompt}. Jawab TRUE kalau penting, FALSE kalau nggak. Cuma TRUE atau FALSE aja."},
                            {"role": "user", "content": f"Pesan dari {push_name}: {text}"}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 10,
                    },
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                decision = r.json()["choices"][0]["message"]["content"].strip().upper()
                if decision != "TRUE":
                    return
        except Exception:
            return

    # Build and send notification
    message_text = f"📩 *Pesan Baru* — {phone}"
    if push_name:
        message_text += f" ({push_name})"
    message_text += f"\n👤 Dari: {sender}"
    message_text += f"\n💬 {text}"
    if ts:
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            message_text += f"\n🕐 {t.strftime('%H:%M:%S')}"
        except Exception:
            pass
    await _telegram_send(message_text)

    # Auto-forward all
    if _AUTO_FORWARD_ALL:
        await _telegram_send(f"📨 *Forward All: {phone}*\n{text}")

    if media_path:
        try:
            import httpx
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("ALLOWED_USER_IDS", "").split(",")[0] if os.environ.get("ALLOWED_USER_IDS") else ""
            if token and chat_id and Path(media_path).exists():
                ext = Path(media_path).suffix.lower()
                async with httpx.AsyncClient(timeout=60) as client:
                    with open(media_path, "rb") as f:
                        if ext in (".jpg", ".jpeg", ".png", ".webp"):
                            await client.post(
                                f"https://api.telegram.org/bot{token}/sendPhoto",
                                data={"chat_id": chat_id},
                                files={"photo": f},
                            )
                        elif ext in (".mp4", ".webm", ".gif"):
                            await client.post(
                                f"https://api.telegram.org/bot{token}/sendVideo",
                                data={"chat_id": chat_id},
                                files={"video": f},
                            )
                        elif ext in (".ogg", ".mp3", ".wav", ".m4a"):
                            await client.post(
                                f"https://api.telegram.org/bot{token}/sendAudio",
                                data={"chat_id": chat_id},
                                files={"audio": f},
                            )
                        else:
                            await client.post(
                                f"https://api.telegram.org/bot{token}/sendDocument",
                                data={"chat_id": chat_id},
                                files={"document": f},
                            )
        except Exception as e:
            logger.error(f"Forward media: {e}")


async def _handle_forward_message(data: dict):
    content = data.get("content", {})
    ctype = content.get("type", "unknown")
    phone = data.get("phone", "?")
    sender = data.get("sender", "?")
    push_name = data.get("pushName", "")

    text = ""
    if ctype == "text":
        text = content.get("text", "")
    else:
        text = f"[{ctype}] {content.get('caption', '') or content.get('text', '') or ''}"

    msg = f"🔄 *WA Forward* — {phone}"
    if push_name:
        msg += f" ({push_name})"
    msg += f"\n👤 {sender}: {text[:300]}"
    await _telegram_send(msg)


async def _handle_story_update(data: dict):
    content = data.get("content", {})
    ctype = content.get("type", "unknown")
    phone = data.get("phone", "?")
    sender = data.get("sender", "?")
    push_name = data.get("pushName", "")
    text = ""
    if ctype == "text":
        text = content.get("text", "")
    elif ctype == "image":
        text = f"🖼 {content.get('caption', '(no caption)')}"
    elif ctype == "video":
        text = f"🎬 {content.get('caption', '(no caption)')}"
    else:
        text = f"[{ctype}]"
    msg = f"📸 *Status Update* — {sender}"
    if push_name:
        msg += f" ({push_name})"
    msg += f"\n{text}"
    await _telegram_send(msg)
    media_path = data.get("mediaPath")
    if media_path and Path(media_path).exists():
        try:
            ext = Path(media_path).suffix.lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp"):
                await _telegram_photo(media_path)
        except Exception:
            pass


async def _save_monitors():
    for phone, m in _active_monitors.items():
        _db_monitor_save(phone, m.get("interval", 60), m.get("last_status"), m.get("last_seen"))
    # Clean removed monitors from DB
    stored = _db_monitors_get_all()
    for p in stored:
        if p not in _active_monitors:
            _db_monitor_delete(p)


async def check(phone: str) -> str:
    result = await _send_command({"type": "check", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal cek {phone}: {result['error']}"

    status = result.get("status", "unknown")
    last_seen = result.get("last_seen")
    ts = datetime.fromisoformat(result.get("timestamp", datetime.now().isoformat())).strftime("%H:%M:%S")

    seen = ""
    if last_seen:
        try:
            seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            seen = seen_dt.astimezone().strftime("%H:%M:%S")
        except Exception:
            seen = last_seen

    if status == "online":
        return f"🟢 *{phone}* ONLINE — {ts}"
    elif status == "offline":
        msg = f"🔴 *{phone}* OFFLINE"
        if seen:
            msg += f"\n📅 Terakhir online: {seen}"
        return msg
    return f"⚪ *{phone}* Status tidak diketahui."


async def scan() -> str:
    """Tampilkan QR pairing (ulang kirim QR ke Telegram atau trigger baru)."""
    global _qr_sent, _last_qr_data

    if _bridge_connected:
        return "✅ WhatsApp sudah terhubung, tidak perlu scan ulang."

    if QR_FILE.exists():
        _qr_sent = False
        _last_qr_data = None
        # Cek apakah file PNG (binary) atau text (raw QR data)
        try:
            data = QR_FILE.read_bytes()
            is_png = data[:4] == b'\x89PNG'
        except Exception:
            is_png = False
        if is_png:
            await _telegram_photo(str(QR_FILE))
            await _telegram_send("📱 *WhatsApp Web Login*\nScan QR code di atas untuk menghubungkan WhatsApp.")
            return "📱 QR code dikirim ulang ke chat ini."
        # File berisi raw QR data → generate ulang
        has_qrcode = _generate_qr_image(QR_FILE.read_text())
        if has_qrcode:
            await _telegram_photo(str(QR_FILE))
        await _telegram_send("📱 *WhatsApp Web Login*\nScan QR code di atas untuk menghubungkan WhatsApp.")
        return "📱 QR code dikirim ulang ke chat ini."

    # QR file ga ada → reset state biar bridge kirim QR baru
    _qr_sent = False
    _last_qr_data = None
    await _start_bridge()
    if _bridge_connected:
        return "✅ WhatsApp sudah terhubung, tidak perlu scan ulang."
    if _qr_pending:
        return "📱 QR code sudah dikirim ke chat ini. Scan dari HP untuk pairing."
    return "⏳ Menyiapkan QR... tunggu beberapa detik."


async def monitor_start(phone: str, interval: int = 60) -> str:
    if phone in _active_monitors:
        return f"⚠️ Monitor untuk {phone} sudah aktif."

    _active_monitors[phone] = {
        "interval": max(30, interval),
        "last_status": None,
        "last_seen": None,
    }
    await _save_monitors()

    result = await _send_command({"type": "subscribe", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        del _active_monitors[phone]
        await _save_monitors()
        return f"❌ Gagal subscribe {phone}: {result['error']}"

    # Trigger initial check
    asyncio.create_task(_delayed_check(phone))
    return f"📡 Monitoring *{phone}* dimulai. Notifikasi akan dikirim ke Telegram saat status berubah."


async def _delayed_check(phone: str):
    await asyncio.sleep(3)
    result = await _send_command({"type": "check", "jid": phone})
    if isinstance(result, dict):
        status = result.get("status")
        last_seen = result.get("last_seen")
        if phone in _active_monitors:
            _active_monitors[phone]["last_status"] = status
            _active_monitors[phone]["last_seen"] = last_seen
            await _save_monitors()

            if status == "online":
                ts = datetime.now().strftime("%H:%M:%S")
                await _telegram_send(f"🟢 *{phone}* AKTIF pada pukul {ts}")


async def monitor_stop(phone: str) -> str:
    if phone not in _active_monitors:
        return f"❌ Tidak ada monitor aktif untuk {phone}."
    del _active_monitors[phone]
    await _save_monitors()
    return f"⏹ Monitoring *{phone}* dihentikan."


async def monitor_stop_all() -> str:
    if not _active_monitors:
        return "Tidak ada monitor aktif."
    count = len(_active_monitors)
    _active_monitors.clear()
    await _save_monitors()
    return f"⏹ Semua monitor ({count}) dihentikan."


def monitor_list() -> str:
    if not _active_monitors:
        return "Tidak ada monitor WhatsApp aktif."

    lines = ["📋 *WhatsApp Monitor Aktif*:"]
    for phone, m in _active_monitors.items():
        status = m.get("last_status", "menunggu") or "menunggu"
        icon = "🟢" if status == "online" else "🔴" if status == "offline" else "⚪"
        lines.append(f"  {icon} {phone} — {status}")
    return "\n".join(lines)


async def session_status() -> str:
    auth_dir = CONFIG_DIR / "baileys_auth"
    if not auth_dir.exists() or not any(auth_dir.iterdir()):
        return "❌ WhatsApp belum terhubung. Jalankan `!wa check <nomor>` untuk pairing."

    result = await _send_command({"type": "qr_status"})
    if isinstance(result, dict) and result.get("connected"):
        return "✅ WhatsApp terhubung via Baileys."
    return "❌ WhatsApp tidak terhubung. Coba `!wa check <nomor>`."


async def reset() -> str:
    """Hapus auth dan force QR pairing baru."""
    result = await _send_command({"type": "reset"})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal reset: {result['error']}"
    return "🔄 Auth dihapus. Tunggu QR pairing baru muncul di chat ini."


async def get_messages(phone: str, limit: int = 20) -> str:
    """Ambil riwayat pesan dari chat."""
    result = await _send_command({"type": "get_messages", "jid": phone, "limit": limit})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil pesan: {result['error']}"

    messages = result.get("messages", [])
    if not messages:
        return f"💬 Tidak ada pesan dengan {phone}."

    lines = [f"💬 *Pesan dengan {phone}* ({len(messages)}):"]
    for m in reversed(messages):
        sender = "🧑" if not m.get("fromMe") else "👤"
        name = m.get("pushName", "") or m.get("sender", "?")
        content = m.get("content", {})
        ctype = content.get("type", "?")
        ts = m.get("timestamp", "")
        time_str = ""
        if ts:
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                time_str = t.strftime("%H:%M")
            except Exception:
                time_str = ts[-8:] if len(ts) > 8 else ts

        text = ""
        if ctype == "text":
            text = content.get("text", "")
        elif ctype == "image":
            text = f"🖼 {content.get('caption', '')}"
        elif ctype == "video":
            text = f"🎬 {content.get('caption', '')}"
        elif ctype == "audio":
            text = "🎵 Audio"
        elif ctype == "document":
            text = f"📄 {content.get('filename', 'file')}"
        elif ctype == "sticker":
            text = "🃏 Sticker"
        else:
            text = f"[{ctype}]"

        preview = text[:80].replace("\n", " ")
        lines.append(f"  {sender} {name} [{time_str}]: {preview}")

    return "\n".join(lines)


async def get_groups() -> str:
    """Daftar grup WhatsApp yang diikuti."""
    result = await _send_command({"type": "get_groups"})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil grup: {result['error']}"

    groups = result.get("groups", [])
    if not groups:
        return "Tidak ada grup."

    lines = [f"👥 *Grup WhatsApp* ({len(groups)}):"]
    for g in sorted(groups, key=lambda x: x.get("subject", "").lower()):
        name = g.get("subject", "?")
        size = g.get("size", 0)
        jid = g.get("jid", "").split("@")[0]
        lines.append(f"  👥 {name} ({size} anggota)")
        lines.append(f"     ID: {jid}")
        desc = g.get("desc", "")
        if desc:
            lines.append(f"     {desc[:100]}")
    return "\n".join(lines)


async def send_message(phone: str, text: str) -> str:
    """Kirim pesan WhatsApp."""
    if not text:
        return "❌ Teks pesan kosong."
    result = await _send_command({"type": "send_message", "jid": phone, "text": text})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal kirim: {result['error']}"
    return f"✅ Pesan terkirim ke {phone}."


async def forward_chat(phone: str | None, action: str) -> str:
    """Aktifkan/nonaktifkan forwarding pesan ke Telegram."""
    if action == "status":
        result = await _send_command({"type": "forward_status", "action": "status"})
        if isinstance(result, dict) and "chats" in result:
            chats = result["chats"]
            if chats:
                lines = ["🔄 *Forward Aktif:*"]
                for c in chats:
                    lines.append(f"  📩 {c.split('@')[0]}")
                return "\n".join(lines)
            return "Tidak ada chat yang di-forward."
        return str(result)

    if not phone:
        return "Gunakan: !wa forward on/off <nomor>"

    result = await _send_command({"type": "forward_status", "action": action, "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ {result['error']}"
    if action == "on":
        return f"✅ Forward dari *{phone}* diaktifkan. Pesan baru akan dikirim ke Telegram."
    return f"⏹ Forward dari *{phone}* dimatikan."


async def reply_message(phone: str, message_id: str, text: str, quoted_text: str = "") -> str:
    """Balas pesan WhatsApp."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    if not text:
        return "❌ Teks balasan kosong."
    result = await _send_command({
        "type": "reply", "jid": phone,
        "message_id": message_id, "text": text,
        "quoted_text": quoted_text
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal balas: {result['error']}"
    return f"✅ Balasan terkirim ke {phone}."


async def react_message(phone: str, message_id: str, emoji: str = "👍") -> str:
    """Reaksi ke pesan WhatsApp."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    result = await _send_command({
        "type": "react", "jid": phone,
        "message_id": message_id, "emoji": emoji
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal reaksi: {result['error']}"
    return f"✅ Reaksi {emoji} terkirim ke {phone}."


async def send_media(phone: str, file_path: str, media_type: str = "image", caption: str = "") -> str:
    """Kirim media (image/video/audio/document) ke WhatsApp."""
    if not os.path.exists(file_path):
        return f"❌ File tidak ditemukan: {file_path}"
    result = await _send_command({
        "type": "send_media", "jid": phone,
        "file": file_path, "media_type": media_type,
        "caption": caption
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal kirim media: {result['error']}"
    return f"✅ Media terkirim ke {phone}."


async def mark_read(phone: str, message_id: str | None = None) -> str:
    """Tandai pesan sebagai sudah dibaca."""
    cmd = {"type": "read", "jid": phone}
    if message_id:
        cmd["message_id"] = message_id
    result = await _send_command(cmd)
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal mark read: {result['error']}"
    return f"✅ Pesan di *{phone}* ditandai sudah dibaca."


async def typing_indicator(phone: str, action: str = "on") -> str:
    """Kirim indikator typing/recording."""
    if action not in ("on", "off", "recording"):
        return "❌ Gunakan: on (typing), off (stop), recording (voice)"
    result = await _send_command({
        "type": "typing", "jid": phone, "action": action
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal: {result['error']}"
    labels = {"on": "mengetik", "off": "berhenti", "recording": "merekam"}
    return f"✅ Indikator {labels.get(action, action)} terkirim ke {phone}."


async def delete_message(phone: str, message_id: str, for_everyone: bool = True) -> str:
    """Hapus pesan WhatsApp."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    result = await _send_command({
        "type": "delete", "jid": phone,
        "message_id": message_id, "from_me": True,
        "delete_for": "everyone" if for_everyone else "me"
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal hapus: {result['error']}"
    return f"✅ Pesan dihapus dari {phone}."


async def group_add(phone: str, participants: list[str]) -> str:
    """Tambah anggota ke grup."""
    if not participants:
        return "❌ Daftar peserta harus diisi."
    p_list = [p if "@" in p else p + "@s.whatsapp.net" for p in participants]
    result = await _send_command({
        "type": "group_add", "jid": phone, "participants": p_list
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal tambah anggota: {result['error']}"
    return f"✅ {len(participants)} anggota ditambahkan ke grup."


async def group_remove(phone: str, participants: list[str]) -> str:
    """Keluarkan anggota dari grup."""
    if not participants:
        return "❌ Daftar peserta harus diisi."
    p_list = [p if "@" in p else p + "@s.whatsapp.net" for p in participants]
    result = await _send_command({
        "type": "group_remove", "jid": phone, "participants": p_list
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal keluarkan anggota: {result['error']}"
    return f"✅ {len(participants)} anggota dikeluarkan dari grup."


async def group_promote(phone: str, participants: list[str]) -> str:
    """Jadikan admin grup."""
    if not participants:
        return "❌ Daftar peserta harus diisi."
    p_list = [p if "@" in p else p + "@s.whatsapp.net" for p in participants]
    result = await _send_command({
        "type": "group_promote", "jid": phone, "participants": p_list
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal promote: {result['error']}"
    return f"✅ {len(participants)} anggota di-promote jadi admin."


async def group_demote(phone: str, participants: list[str]) -> str:
    """Turunkan admin grup."""
    if not participants:
        return "❌ Daftar peserta harus diisi."
    p_list = [p if "@" in p else p + "@s.whatsapp.net" for p in participants]
    result = await _send_command({
        "type": "group_demote", "jid": phone, "participants": p_list
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal demote: {result['error']}"
    return f"✅ {len(participants)} anggota di-demote dari admin."


async def group_subject(phone: str, subject: str) -> str:
    """Ubah nama grup."""
    if not subject:
        return "❌ Nama grup harus diisi."
    result = await _send_command({
        "type": "group_subject", "jid": phone, "subject": subject
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ubah nama grup: {result['error']}"
    return f"✅ Nama grup diubah menjadi: {subject}"


async def group_desc(phone: str, description: str) -> str:
    """Ubah deskripsi grup."""
    result = await _send_command({
        "type": "group_desc", "jid": phone, "description": description
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ubah deskripsi grup: {result['error']}"
    return f"✅ Deskripsi grup diubah."


async def group_invite(phone: str) -> str:
    """Dapatkan link undangan grup."""
    result = await _send_command({"type": "group_invite", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal dapatkan invite: {result['error']}"
    code = result.get("invite_code", "")
    link = result.get("link", "")
    return f"🔗 *Link Undangan Grup*\nKode: {code}\nLink: {link}"


async def group_leave(phone: str) -> str:
    """Keluar dari grup."""
    result = await _send_command({"type": "group_leave", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal keluar grup: {result['error']}"
    return f"✅ Keluar dari grup."


async def group_members(phone: str) -> str:
    """Daftar anggota grup."""
    result = await _send_command({"type": "group_members", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil anggota grup: {result['error']}"
    subject = result.get("subject", "Grup")
    participants = result.get("participants", [])
    if not participants:
        return f"👥 *{subject}*\nTidak ada data anggota."
    lines = [f"👥 *{subject}* ({len(participants)} anggota):"]
    for p in participants:
        jid = p.get("jid", "?")
        admin = p.get("admin", "")
        icon = "👑" if admin else "👤"
        name = p.get("name", "") or jid
        lines.append(f"  {icon} {name} ({jid}){' [ADMIN]' if admin else ''}")
    return "\n".join(lines)


async def get_contacts() -> str:
    """Daftar kontak WhatsApp."""
    result = await _send_command({"type": "contacts"})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil kontak: {result['error']}"
    contacts = result.get("contacts", [])
    if not contacts:
        return "📖 Tidak ada kontak."
    lines = [f"📖 *Kontak WhatsApp* ({len(contacts)}):"]
    for c in contacts:
        name = c.get("name", "") or c.get("jid", "?")
        jid = c.get("jid", "")
        lines.append(f"  👤 {name} — {jid}")
    return "\n".join(lines)


async def block_contact(phone: str) -> str:
    """Blokir kontak."""
    result = await _send_command({"type": "block", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal blokir: {result['error']}"
    return f"⛔ *{phone}* diblokir."


async def unblock_contact(phone: str) -> str:
    """Buka blokir kontak."""
    result = await _send_command({"type": "unblock", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal buka blokir: {result['error']}"
    return f"✅ *{phone}* dibuka blokirnya."


async def get_profile(phone: str) -> str:
    """Ambil foto profil + status WhatsApp."""
    result = await _send_command({"type": "profile", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil profil: {result['error']}"
    lines = [f"👤 *Profil {phone}*"]
    pic = result.get("picture")
    if pic:
        lines.append(f"  🖼 Foto profil: {pic[:100]}")
    else:
        lines.append("  🖼 Tidak ada foto profil")
    status = result.get("status", "")
    if status:
        lines.append(f"  📝 Status: {status[:200]}")
    lines.append(f"  🔗 JID: {phone}@s.whatsapp.net")
    return "\n".join(lines)


# ============================================================
# NEW FEATURES: AI Auto-Reply, Keyword Alert, Message Search,
# Status Spy, Voice Transcriber, Chat Export, Broadcast,
# Poll, Scheduled Messages, Smart Inbox, and more
# ============================================================

_AUTO_FORWARD_ALL = False

# --- AI Auto-Reply ---

async def auto_reply_set(phone: str, prompt: str = "", style: str = "") -> str:
    """Set AI auto-reply untuk chat tertentu."""
    if not prompt and not style:
        _db_auto_reply_delete(phone)
        return f"⏹ Auto-reply untuk *{phone}* dinonaktifkan."
    _db_auto_reply_set(phone, prompt, style)
    return f"✅ Auto-reply untuk *{phone}* diaktifkan."


async def auto_reply_status() -> str:
    """Status auto-reply."""
    replies = _db_auto_reply_get_all()
    if not replies:
        return "Tidak ada auto-reply aktif."
    lines = ["🤖 *Auto-Reply Aktif*:"]
    for phone, cfg in replies.items():
        p = cfg.get("prompt", "")[:50]
        s = cfg.get("style", "default")
        lines.append(f"  💬 {phone} — style: {s}")
    return "\n".join(lines)

async def ai_natural_response(context: str, detail: str = "") -> str:
    """Generate natural Indonesian response for errors/help using AI."""
    api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
    if not api_key:
        return context
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions",
                json={
                    "model": os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct"),
                    "messages": [
                        {"role": "system", "content": "Kamu asisten yang jawab dengan santai, natural, pake bahasa Indonesia sehari-hari. Jawab singkat, langsung ke inti, nggak usah basa-basi."},
                        {"role": "user", "content": f"Kontek: {context}. Detail: {detail}. Bales dengan natural, kayak ngomong sama temen."}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 60,
                },
                headers={"Authorization": f"Bearer {api_key}"}
            )
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return context


async def _process_auto_reply(phone: str, incoming_text: str, push_name: str):
    """Internal: proses auto-reply AI dengan balasan natural."""
    replies = _db_auto_reply_get_all()
    jid = phone if "@" in phone else phone + "@s.whatsapp.net"
    if jid not in replies and phone not in replies:
        return
    cfg = replies.get(jid) or replies.get(phone, {})
    prompt = cfg.get("prompt", "")
    style = cfg.get("style", "")
    api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
    if not api_key:
        return
    try:
        import httpx
        base = "Kamu asisten yang lagi bales chat WhatsApp. Ngobrolnya santai, natural, kayak temen ngobrol biasa. Pakai bahasa Indonesia sehari-hari. Jawab singkat dan to the point, nggak usah pake formalitas."
        if style:
            base += f" Tambahan gaya: {style}."
        if prompt:
            base += f" Yang perlu diingat: {prompt}"
        system = base
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions",
                json={
                    "model": os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct"),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"{push_name} ngirim pesan: {incoming_text}"}
                    ],
                    "temperature": 0.9,
                    "max_tokens": 200,
                },
                headers={"Authorization": f"Bearer {api_key}"}
            )
            data = r.json()
            reply_text = data["choices"][0]["message"]["content"].strip()
            await reply_message(phone, "", reply_text)
            await _telegram_send(f"🤖 *Auto-Reply ke {phone}*\n{reply_text[:200]}")
    except Exception as e:
        logger.error(f"Auto-reply LLM error: {e}")


# --- Keyword Alert ---

async def keyword_alert_add(keywords: list[str]) -> str:
    """Tambah keyword alert."""
    for kw in keywords:
        _db_keyword_add(kw)
    return f"✅ Keyword alert ditambahkan: {', '.join(keywords)}"

async def keyword_alert_remove(keywords: list[str]) -> str:
    """Hapus keyword alert."""
    for kw in keywords:
        _db_keyword_remove(kw)
    return f"⏹ Keyword alert dihapus: {', '.join(keywords)}"

async def keyword_alert_list() -> str:
    """Daftar keyword alert."""
    alerts = _db_keyword_alerts()
    if not alerts:
        return "Tidak ada keyword alert."
    return "🔑 *Keyword Alert:*\n" + "\n".join(f"  • {k}" for k in alerts)

async def _process_keyword_alert(phone: str, text: str, push_name: str):
    """Internal: cek keyword dalam pesan."""
    alerts = _db_keyword_alerts()
    if not alerts:
        return
    lower = text.lower()
    for keyword in alerts:
        if keyword in lower:
            await _telegram_send(
                f"🚨 *Keyword Alert!*\n{keyword} ditemukan di chat *{phone} ({push_name})*\n\n{text[:300]}"
            )


# --- Message Search ---

async def search_messages(keyword: str, limit: int = 30) -> str:
    """Cari pesan di semua chat berdasarkan keyword (DB + bridge fallback)."""
    results = _db_search_messages(keyword, limit)
    if not results:
        result = await _send_command({"type": "search_messages", "keyword": keyword, "limit": limit})
        if isinstance(result, dict) and "error" in result:
            return f"❌ Gagal search: {result['error']}"
        results = result.get("results", [])
    if not results:
        return f"🔍 Tidak ada pesan mengandung '{keyword}'."
    lines = [f"🔍 *Pesan mengandung '{keyword}'* ({len(results)}):"]
    for m in results:
        sender = "👤" if not m.get("fromMe") else "🧑"
        jid = m.get("phone") or m.get("jid", "?")
        text = m.get("content_text") or m.get("text", "") or ""
        lines.append(f"  {sender} {jid}: {text[:80]}")
    return "\n".join(lines)


# --- Chat Export ---

async def chat_export(phone: str, limit: int = 200) -> str:
    """Export riwayat chat ke file (DB + bridge fallback)."""
    messages = _db_export_chat(phone, limit)
    if not messages:
        result = await _send_command({"type": "export_chat", "jid": phone, "limit": limit})
        if isinstance(result, dict) and "error" in result:
            return f"❌ Gagal export: {result['error']}"
        messages = result.get("messages", [])
    if not messages:
        return f"Tidak ada pesan dengan {phone}."
    export_dir = CONFIG_DIR / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    fname = f"wa_{phone}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    fpath = export_dir / fname
    fpath.write_text(json.dumps(messages, indent=2, default=str))
    return f"📁 Export {len(messages)} pesan ke `{fpath}`."


# --- Vector Search ---

async def _index_message_vector(msg: dict):
    """Async vector indexing for incoming message."""
    content = msg.get("content", {})
    text = content.get("text", "") or content.get("caption", "") or ""
    if not text:
        return
    metadata = {
        "phone": msg.get("phone", ""),
        "sender": msg.get("sender", ""),
        "type": content.get("type", ""),
        "timestamp": str(msg.get("timestamp", "")),
    }
    await _db_index_embedding(msg["id"], text, metadata)


async def semantic_search(query: str, limit: int = 10) -> str:
    """Cari pesan berdasarkan makna (semantic search)."""
    results = await _db_semantic_search(query, limit)
    if not results:
        return "Tidak ada hasil semantic search."
    lines = ["🔍 *Semantic Search* — " + query]
    for r in results:
        score = r.get("score", 0)
        txt = (r.get("content_text", "") or "")[:80]
        sender = r.get("sender", "")
        ts = r.get("timestamp", "")
        lines.append(f"  [{score:.2f}] {sender} @ {ts}: {txt}")
    return "\n".join(lines)


# --- Broadcast ---

async def broadcast(jids: list[str], text: str) -> str:
    """Kirim pesan ke banyak kontak."""
    if not text:
        return "❌ Teks pesan kosong."
    if not jids:
        return "❌ Daftar nomor harus diisi."
    jid_list = [j if "@" in j else j + "@s.whatsapp.net" for j in jids]
    result = await _send_command({"type": "broadcast", "jids": jid_list, "text": text})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal broadcast: {result['error']}"
    sent = result.get("sent", 0)
    failed = result.get("failed", 0)
    return f"📨 Broadcast: {sent} terkirim, {failed} gagal (dari {len(jids)} target)."


# --- Poll Create ---

async def poll_create(phone: str, question: str, options: list[str]) -> str:
    """Buat poll di chat/grup."""
    if len(options) < 2:
        return "❌ Minimal 2 opsi."
    result = await _send_command({
        "type": "poll_create", "jid": phone,
        "question": question, "options": options
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal buat poll: {result['error']}"
    return f"📊 Poll terkirim ke {phone}."


# --- Disappearing Messages ---

async def toggle_disappearing(phone: str, duration: int = 86400) -> str:
    """Atur disappearing messages (0=off, 86400=24h, 604800=7d, 7776000=90d)."""
    labels = {0: "off", 86400: "24 jam", 604800: "7 hari", 7776000: "90 hari"}
    label = labels.get(duration, f"{duration} detik")
    result = await _send_command({"type": "toggle_disappearing", "jid": phone, "expiration": duration})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal: {result['error']}"
    return f"✅ Disappearing messages di *{phone}*: {label}"


# --- Scheduled Messages ---

_scheduled_tasks = {}

async def schedule_message(phone: str, delay_seconds: int, text: str) -> str:
    """Kirim pesan terjadwal."""
    if delay_seconds < 1:
        return "❌ Waktu minimal 1 detik."
    task = asyncio.create_task(_do_scheduled(phone, delay_seconds, text))
    _scheduled_tasks[f"{phone}_{time.time()}"] = task
    if delay_seconds >= 60:
        readable = f"{delay_seconds//60} menit"
    else:
        readable = f"{delay_seconds} detik"
    return f"📅 Pesan terjadwal ke *{phone}* dalam {readable}."

async def _do_scheduled(phone: str, delay: int, text: str):
    await asyncio.sleep(delay)
    result = await send_message(phone, text)
    await _telegram_send(f"📅 *Pesan Terjadwal*\nKe: {phone}\n{result}")


# --- Auto-Forward All ---

async def auto_forward_all(action: str) -> str:
    """Forward semua pesan ke Telegram."""
    global _AUTO_FORWARD_ALL
    if action == "on":
        _AUTO_FORWARD_ALL = True
        return "✅ Auto-forward semua pesan diaktifkan."
    elif action == "off":
        _AUTO_FORWARD_ALL = False
        return "⏹ Auto-forward semua pesan dimatikan."
    return f"Status: {'🟢 AKTIF' if _AUTO_FORWARD_ALL else '🔴 NONAKTIF'}"


# --- Voice Note Transcriber ---

async def transcribe_latest(phone: str, limit: int = 10) -> str:
    """Transkrip voice note terbaru."""
    result = await _send_command({"type": "get_messages", "jid": phone, "limit": limit})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal: {result['error']}"
    messages = result.get("messages", [])
    audio_msgs = [m for m in messages if m.get("content", {}).get("type") == "audio"]
    if not audio_msgs:
        return f"Tidak ada voice note di {limit} pesan terakhir."
    api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
    if not api_key:
        return "❌ API key tidak tersedia untuk transkripsi."
    lines = [f"🎤 *Voice Note Transcription* ({len(audio_msgs)}):"]
    import httpx
    for m in audio_msgs:
        sender = m.get("pushName", "") or m.get("sender", "?")
        ts = m.get("timestamp", "")[:10] if m.get("timestamp") else ""
        lines.append(f"\n🎵 Dari {sender} ({ts}):")
        lines.append("  (transkripsi memerlukan file audio — gunakan !wa send_media untuk kirim file audio ke AI)")
    return "\n".join(lines)


# --- Mention Alert ---

_mention_alerts_active = False

async def mention_alert(action: str) -> str:
    """Aktifkan/nonaktifkan notifikasi mention."""
    global _mention_alerts_active
    if action == "on":
        _mention_alerts_active = True
        return "✅ Mention alert diaktifkan."
    _mention_alerts_active = False
    return "⏹ Mention alert dimatikan."


# --- Chat Stats ---

async def chat_stats(phone: str, limit: int = 200) -> str:
    """Statistik chat (DB + bridge fallback)."""
    stats = _db_message_stats(phone, limit)
    if stats["total"] == 0:
        result = await _send_command({"type": "export_chat", "jid": phone, "limit": limit})
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            total = len(msgs)
            from_me = sum(1 for m in msgs if m.get("fromMe"))
            by_type = {}
            for m in msgs:
                ct = m.get("content", {}).get("type", "unknown")
                by_type[ct] = by_type.get(ct, 0) + 1
            return (
                f"📊 *Statistik Chat {phone}* ({total} pesan via bridge):\n"
                f"  👤 Anda: {from_me} | 👥 Target: {total - from_me}\n"
                f"  💬 Teks: {by_type.get('text', 0)} | 🖼 Gambar: {by_type.get('image', 0)}\n"
                f"  🎬 Video: {by_type.get('video', 0)} | 🎵 Audio: {by_type.get('audio', 0)}"
            )
        return f"❌ Gagal: {result.get('error', 'Tidak ada data') if isinstance(result, dict) else 'Tidak ada data'}"
    by_type = stats["by_type"]
    return (
        f"📊 *Statistik Chat {phone}* ({stats['total']} pesan di DB):\n"
        f"  👤 Anda: {stats['sent']} | 👥 Target: {stats['received']}\n"
        f"  💬 Teks: {by_type.get('text', 0)} | 🖼 Gambar: {by_type.get('image', 0)}\n"
        f"  🎬 Video: {by_type.get('video', 0)} | 🎵 Audio: {by_type.get('audio', 0)}"
    )


# --- Activity Pattern ---

async def activity_pattern(phone: str, limit: int = 200) -> str:
    """Deteksi pola aktivitas target (DB + bridge fallback)."""
    pattern = _db_activity_pattern(phone, limit)
    if not pattern.get("hours"):
        result = await _send_command({"type": "export_chat", "jid": phone, "limit": limit})
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            hours = {}
            for m in msgs:
                if m.get("fromMe"): continue
                ts = m.get("timestamp", "")
                if ts:
                    try:
                        h = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
                        hours[h] = hours.get(h, 0) + 1
                    except Exception: pass
            if not hours:
                return "Tidak cukup data untuk analisis pola."
            peak_hour = max(hours, key=hours.get)
        else:
            return "Tidak cukup data untuk analisis pola."
    else:
        hours = pattern["hours"]
        peak_hour = pattern.get("peak_hour")

    lines = [f"📈 *Pola Aktivitas {phone}*:"]
    for h in sorted(hours):
        bar = "█" * min(hours[h], 20)
        lines.append(f"  {h:02d}:00 {bar} {hours[h]}")
    lines.append(f"\n⏰ Puncak aktivitas: jam {peak_hour}:00 ({hours[peak_hour]} pesan)")
    return "\n".join(lines)


# --- Smart Inbox (AI filter) ---

_smart_inbox_active = False
_smart_inbox_prompt = "Forward only important messages"

async def smart_inbox(action: str, prompt: str = "") -> str:
    """Smart inbox: AI filter untuk forward pesan penting."""
    global _smart_inbox_active, _smart_inbox_prompt
    if action == "on":
        _smart_inbox_active = True
        if prompt:
            _smart_inbox_prompt = prompt
        return f"✅ Smart inbox diaktifkan. Kriteria: {_smart_inbox_prompt}"
    elif action == "off":
        _smart_inbox_active = False
        return "⏹ Smart inbox dimatikan."
    return f"Status: {'🟢 AKTIF' if _smart_inbox_active else '🔴 NONAKTIF'} - {_smart_inbox_prompt}"


# --- Chat Backup ---

async def chat_backup(phone: str = "") -> str:
    """Backup chat ke file (DB + bridge fallback)."""
    export_dir = CONFIG_DIR / "backups"
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if phone:
        msgs = _db_export_chat(phone, 1000)
        if not msgs:
            result = await _send_command({"type": "export_chat", "jid": phone, "limit": 1000})
            if isinstance(result, dict) and "error" in result:
                return f"❌ Gagal: {result['error']}"
            msgs = result.get("messages", [])
        if not msgs:
            return f"Tidak ada pesan untuk {phone}."
        fname = f"backup_{phone}_{timestamp}.json"
        (export_dir / fname).write_text(json.dumps(msgs, indent=2, default=str))
        return f"💾 Backup {phone}: {len(msgs)} pesan → `{fname}`"
    else:
        # Backup all chats from DB
        chats = _db_all_chats()
        backed_up = 0
        for c in chats:
            jid = c.get("remote_jid", "")
            phone_id = c.get("phone", jid.split("@")[0])
            msgs = _db_export_chat(jid, 200) or _db_export_chat(phone_id, 200)
            if msgs:
                fname = f"backup_{phone_id}_{timestamp}.json"
                (export_dir / fname).write_text(json.dumps(msgs, indent=2, default=str))
                backed_up += 1
        if not backed_up:
            return "Belum ada data chat di DB."
        return f"💾 Backup {backed_up} chat selesai → `{export_dir}/`"


# --- Group Settings ---

async def group_settings(phone: str, setting: str) -> str:
    """Ubah pengaturan grup (announcement/locked)."""
    valid = ("announcement", "not_announcement", "locked", "not_locked")
    if setting not in valid:
        return f"❌ Setting harus salah satu: {', '.join(valid)}"
    result = await _send_command({
        "type": "group_settings", "jid": phone, "setting": setting
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal: {result['error']}"
    labels = {"announcement": "hanya admin", "not_announcement": "semua anggota", "locked": "terkunci", "not_locked": "terbuka"}
    return f"✅ Pengaturan grup diubah: {labels.get(setting, setting)}."


# --- Chat Management ---

async def mute_chat(phone: str, hours: int = 8) -> str:
    """Mute chat untuk durasi tertentu."""
    duration = hours * 3600
    result = await _send_command({
        "type": "mute", "jid": phone, "duration": duration
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal mute: {result['error']}"
    return f"🔇 Chat *{phone}* dimute selama {hours} jam."


async def unmute_chat(phone: str) -> str:
    """Unmute chat."""
    result = await _send_command({"type": "unmute", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal unmute: {result['error']}"
    return f"🔊 Chat *{phone}* di-unmute."


async def pin_chat(phone: str) -> str:
    """Pin chat ke atas."""
    result = await _send_command({"type": "pin", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal pin: {result['error']}"
    return f"📌 Chat *{phone}* di-pin."


async def unpin_chat(phone: str) -> str:
    """Unpin chat."""
    result = await _send_command({"type": "unpin", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal unpin: {result['error']}"
    return f"📌 Chat *{phone}* di-unpin."


async def archive_chat(phone: str) -> str:
    """Arsipkan chat."""
    result = await _send_command({"type": "archive", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal arsip: {result['error']}"
    return f"📦 Chat *{phone}* diarsipkan."


async def unarchive_chat(phone: str) -> str:
    """Keluarkan chat dari arsip."""
    result = await _send_command({"type": "unarchive", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal unarsip: {result['error']}"
    return f"📦 Chat *{phone}* dikeluarkan dari arsip."


# --- Message Actions ---

async def star_message(phone: str, message_id: str) -> str:
    """Tandai pesan berbintang."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    result = await _send_command({
        "type": "star", "jid": phone, "message_id": message_id
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal star: {result['error']}"
    return f"⭐ Pesan di-star."


async def unstar_message(phone: str, message_id: str) -> str:
    """Hapus tanda bintang dari pesan."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    result = await _send_command({
        "type": "unstar", "jid": phone, "message_id": message_id
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal unstar: {result['error']}"
    return f"⭐ Star dihapus dari pesan."


async def edit_message(phone: str, message_id: str, text: str) -> str:
    """Edit pesan yang sudah dikirim."""
    if not message_id or not text:
        return "❌ ID pesan dan teks harus diisi."
    result = await _send_command({
        "type": "edit", "jid": phone,
        "message_id": message_id, "text": text
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal edit: {result['error']}"
    return f"✏️ Pesan diedit."


async def react_remove(phone: str, message_id: str) -> str:
    """Hapus reaksi dari pesan."""
    if not message_id:
        return "❌ ID pesan harus diisi."
    result = await _send_command({
        "type": "react_remove", "jid": phone, "message_id": message_id
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal hapus reaksi: {result['error']}"
    return f"✅ Reaksi dihapus."


# --- Group Tools ---

async def group_revoke(phone: str) -> str:
    """Cabut link undangan grup dan buat yang baru."""
    result = await _send_command({"type": "group_revoke", "jid": phone})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal revoke: {result['error']}"
    code = result.get("invite_code", "")
    link = result.get("link", "")
    return f"🔄 *Link Grup Dicabut*\nKode baru: {code}\nLink baru: {link}"


async def blocklist_view() -> str:
    """Lihat daftar kontak yang diblokir."""
    result = await _send_command({"type": "blocklist"})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil blocklist: {result['error']}"
    contacts = result.get("contacts", [])
    if not contacts:
        return "✅ Tidak ada kontak yang diblokir."
    lines = [f"⛔ *Kontak Diblokir* ({len(contacts)}):"]
    for c in contacts:
        lines.append(f"  ⛔ {c.get('jid', '?')}")
    return "\n".join(lines)


# --- Interactive Messages ---

async def list_message(phone: str, title: str, text: str, options: list[str]) -> str:
    """Kirim interactive list message."""
    if len(options) < 2:
        return "❌ Minimal 2 opsi."
    sections = [{
        "title": title or "Pilihan",
        "rows": [{"title": o.strip(), "rowId": f"opt_{i}"} for i, o in enumerate(options)]
    }]
    result = await _send_command({
        "type": "list_message", "jid": phone,
        "title": title, "text": text,
        "button_text": "Pilih", "sections": sections
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal kirim list: {result['error']}"
    return f"📋 List message terkirim ke {phone}."


async def send_location(phone: str, latitude: float, longitude: float) -> str:
    """Kirim lokasi ke chat."""
    result = await _send_command({
        "type": "location", "jid": phone,
        "latitude": latitude, "longitude": longitude
    })
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal kirim lokasi: {result['error']}"
    return f"📍 Lokasi terkirim ke {phone}."


# --- Status/Story Tools ---

async def story_list(limit: int = 30) -> str:
    """Lihat status/story terbaru dari kontak."""
    result = await _send_command({"type": "story_list", "limit": limit})
    if isinstance(result, dict) and "error" in result:
        return f"❌ Gagal ambil story: {result['error']}"
    stories = result.get("stories", [])
    if not stories:
        return "📸 Tidak ada story terbaru."
    lines = [f"📸 *Story Terbaru* ({len(stories)}):"]
    for s in stories:
        sender = s.get("pushName", "") or s.get("sender", "?")
        content = s.get("content", {})
        ctype = content.get("type", "?")
        ts = s.get("timestamp", "")
        time_str = ""
        if ts:
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                time_str = t.strftime("%H:%M %d/%m")
            except Exception:
                time_str = ts[-16:] if len(ts) > 16 else ts
        icon = {"text": "📝", "image": "🖼", "video": "🎬", "audio": "🎵"}.get(ctype, "📄")
        lines.append(f"  {icon} {sender} — {time_str}")
    return "\n".join(lines)
