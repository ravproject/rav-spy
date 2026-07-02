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
MONITOR_DB = CONFIG_DIR / "whatsapp_monitors.json"
BRIDGE_JS = Path(__file__).parent / "whatsapp" / "bridge.js"

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


async def _save_monitors():
    MONITOR_DB.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for phone, m in _active_monitors.items():
        data[phone] = {"interval": m.get("interval", 60), "last_status": m.get("last_status"), "last_seen": m.get("last_seen")}
    MONITOR_DB.write_text(json.dumps(data, indent=2))


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
