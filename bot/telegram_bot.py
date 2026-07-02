"""
Telegram Bot Handler
Menggunakan python-telegram-bot v21 (async)
"""
import os
import asyncio
import warnings
import json
import re
import base64
import httpx
import tempfile
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
from html import escape

# Suppress python-telegram-bot shutdown warning
warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine 'Updater.stop' was never awaited")

load_dotenv()

from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    filters,
    ContextTypes,
    ApplicationBuilder,
)
from telegram.error import TimedOut, NetworkError
from loguru import logger
from .auth import AuthManager
from .command_router import CommandRouter, HELP_TEXT
from security.audit_logger import AuditLogger
from .monitor_task import MonitorTask

from bot.agent_registry import registry
from bot.inline_handler import inline_query

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
# Remove global AGENT_URL and AGENT_API_KEY variables

router = CommandRouter()
auditor = AuditLogger()

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "sessions", "tg_sessions.json")

def markdown_to_html(text: str) -> str:
    parts = re.split(r'(```[\s\S]*?```)', text)
    formatted_parts = []
    
    for part in parts:
        if part.startswith('```') and part.endswith('```'):
            lines = part.split('\n')
            code_lines = lines[1:-1] if len(lines) > 2 else []
            code_content = '\n'.join(code_lines)
            escaped_code = escape(code_content)
            formatted_parts.append(f"<pre>{escaped_code}</pre>")
        else:
            escaped = escape(part)
            escaped = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', escaped)
            escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
            escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', escaped)
            lines = escaped.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('#'):
                    clean_line = line.lstrip('#').strip()
                    lines[i] = f"<b>{clean_line}</b>"
                elif line.strip().startswith('* ') or line.strip().startswith('- '):
                    lines[i] = line.replace('* ', '• ', 1).replace('- ', '• ', 1)
            escaped = '\n'.join(lines)
            formatted_parts.append(escaped)
            
    return ''.join(formatted_parts)

def load_initial_sessions() -> dict[str, str]:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r") as f:
            data = json.load(f)
        valid = {}
        for uid, token in data.items():
            if AuthManager.verify_session_token(token):
                valid[uid] = token
        return valid
    except Exception as e:
        logger.error(f"Failed to load sessions: {e}")
        return {}

def save_current_sessions():
    try:
        os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
        with open(SESSIONS_FILE, "w") as f:
            json.dump(_user_sessions, f)
    except Exception as e:
        logger.error(f"Failed to save sessions: {e}")

_user_sessions: dict[str, str] = load_initial_sessions()
_user_active_agent: dict[str, str] = {}
_terminal_mode: dict[str, bool] = {}
_terminal_tasks: dict[str, asyncio.Task] = {}

async def heartbeat_poller(app: Application, monitor: MonitorTask):
    """Background task to poll heartbeats from all registered agents."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            agents = registry.get_all()
            for agent_id, data in agents.items():
                try:
                    headers = {"X-API-Key": data['api_key']}
                    agent_url = f"http://{data['host']}:{data['port']}"

                    response = await client.get(f"{agent_url}/system/heartbeat", headers=headers)
                    if response.status_code == 200:
                        resp_data = response.json()
                        metrics = resp_data.get("metrics", {})
                        alerts = resp_data.get("alerts", [])

                        await monitor.update_heartbeat(agent_id, metrics)

                        for alert in alerts:
                            logger.info(f"New alert from {agent_id}: {alert}")
                            await monitor._broadcast_alert(f"⚠️ <b>Alert ({agent_id}):</b> {alert}")

                    elif response.status_code == 401:
                        logger.error(f"Agent {agent_id} returned 401 Unauthorized for heartbeat. Check API keys.")

                    file_resp = await client.get(f"{agent_url}/system/scheduled-files", headers=headers)
                    if file_resp.status_code == 200:
                        files_data = file_resp.json().get("files", [])
                        for f in files_data:
                            try:
                                raw = base64.b64decode(f["data"])
                                caption = f.get("caption", "")
                                ftype = f.get("type", "")
                                filename = f.get("filename", "scheduled.bin")
                                for uid in monitor.allowed_users:
                                    if not uid:
                                        continue
                                    try:
                                        from io import BytesIO
                                        if ftype == "photo":
                                            await app.bot.send_photo(
                                                chat_id=uid, photo=BytesIO(raw),
                                                caption=caption, parse_mode="HTML",
                                                read_timeout=60, connect_timeout=60
                                            )
                                        elif ftype == "video":
                                            await app.bot.send_video(
                                                chat_id=uid, video=BytesIO(raw),
                                                caption=caption, parse_mode="HTML",
                                                filename=filename,
                                                read_timeout=60, connect_timeout=60
                                            )
                                        elif ftype == "audio":
                                            await app.bot.send_audio(
                                                chat_id=uid, audio=BytesIO(raw),
                                                caption=caption, parse_mode="HTML",
                                                filename=filename,
                                                read_timeout=60, connect_timeout=60
                                            )
                                        elif ftype == "document":
                                            await app.bot.send_document(
                                                chat_id=uid, document=BytesIO(raw),
                                                caption=caption, parse_mode="HTML",
                                                filename=filename,
                                                read_timeout=60, connect_timeout=60
                                            )
                                        logger.info(f"Sent scheduled {ftype} to {uid} from {agent_id}")
                                    except Exception as e:
                                        logger.error(f"Failed to send scheduled {ftype} to {uid}: {e}")
                            except Exception as e:
                                logger.error(f"Failed to process scheduled file: {e}")

                except Exception as e:
                    logger.debug(f"Heartbeat poller error for {agent_id} (Agent might be offline): {e}")

            await asyncio.sleep(30)

QUICK_CMDS = [
    ["📸 Screenshot", "ℹ️ Sistem", "📖 Bantuan"],
    ["📁 File List", "🤖 AI", "🎥 Rekam"],
    ["⌨️ Menu"],
]

def reply_keyboard():
    return ReplyKeyboardMarkup(QUICK_CMDS, resize_keyboard=True, is_persistent=True, input_field_placeholder="Ketuk perintah cepat...")

CMD_MAP = {
    "📸 screenshot": "!screenshot",
    "ℹ️ sistem": "!sysinfo",
    "📖 bantuan": "!help",
    "📁 file list": "!ls",
    "🤖 ai": "!opencode",
    "🎥 rekam": "!video 10",
    "⌨️ menu": "!menu",
}

ARG_PROMPTS = {
    "cmd_type_": "✏️ Ketik teks yang ingin diketik:",
    "cmd_press_": "🔘 Ketik tombol yang ingin ditekan (contoh: enter, space, ctrl+c):",
    "cmd_get_": "📄 Ketik path file yang ingin diambil:",
    "cmd_ls_": "📂 Ketik path folder (atau kosongkan untuk folder saat ini):",
    "cmd_web_": "🔎 Ketik kata kunci pencarian:",
    "cmd_cd_": "📂 Ketik path tujuan:",
    "cmd_find_": "🔍 Ketik pola file yang dicari:",
    "cmd_notif_": "💬 Ketik teks notifikasi:",
    "cmd_tts_": "🔊 Ketik teks untuk diucapkan:",
    "cmd_ping_": "🌐 Ketik host (default 8.8.8.8):",
    "cmd_launch_": "🚀 Ketik nama aplikasi (chrome, vscode, spotify):",
    "cmd_todo_": "📋 Ketik: add/done/delete/clear [tugas]:",
    "cmd_brightness_": "☀️ Ketik nilai 0-100:",
    "cmd_volume_": "🔊 Ketik: up/down/mute/0-100:",
    "cmd_media_": "🎵 Ketik: play/pause/next/prev:",
    "cmd_win_": "🪟 Ketik: minimize/close:",
    "cmd_reminder_": "⏰ Format: add [teks] [waktu] / list / delete [id]:",
    "cmd_daily_": "📊 Ketik: today / yesterday / [tanggal]:",
}

async def post_init(application: Application):
    monitor = MonitorTask(application)
    asyncio.create_task(heartbeat_poller(application, monitor))
    asyncio.create_task(monitor.run_monitoring_loop())

    bot = application.bot
    cmds = [
        ("start", "Mulai session"),
        ("menu", "Tampilkan menu utama"),
        ("help", "Bantuan perintah"),
        ("otp", "Login dengan kode OTP"),
        ("logout", "Keluar session"),
        ("screenshot", "Ambil screenshot layar"),
        ("sysinfo", "Info sistem laptop"),
        ("battery", "Status baterai"),
        ("ls", "List file"),
        ("speedtest", "Uji kecepatan internet"),
        ("webcam", "Foto webcam"),
        ("clickimage", "Klik gambar di layar"),
        ("waitimage", "Tunggu gambar muncul"),
        ("shell", "Jalankan shell command"),
        ("scroll", "Scroll mouse"),
        ("macro", "Kelola macro"),
    ]
    try:
        await bot.set_my_commands(cmds)
        logger.info("✅ Bot commands registered for autocomplete")
    except Exception as e:
        logger.warning(f"Gagal set commands: {e}")

    async def log_ready_delayed():
        await asyncio.sleep(2)
        logger.info("✅ Telegram Bot is now polling and ready to receive commands!")
    asyncio.create_task(log_ready_delayed())
    logger.info("Background monitoring tasks initialized.")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    token = _user_sessions.get(user_id)
    
    if not token or not AuthManager.verify_session_token(token):
        await update.message.reply_text("🔐 Belum login atau sesi expired.")
        return

    # Determine Active Agent
    active_agent_id = _user_active_agent.get(user_id)
    agents = registry.get_all()
    if not active_agent_id:
        if len(agents) == 1:
            active_agent_id = list(agents.keys())[0]
            _user_active_agent[user_id] = active_agent_id
        else:
            await update.message.reply_text("⚠️ Pilih agent terlebih dahulu dengan !select &lt;agent_id&gt;")
            return

    agent_data = registry.get_agent(active_agent_id)
    if not agent_data:
        await update.message.reply_text("❌ Agent tidak ditemukan.")
        return

    AGENT_URL = f"http://{agent_data['host']}:{agent_data['port']}"
    AGENT_API_KEY = agent_data['api_key']

    await update.message.reply_text("⏳ Mengunduh file dan mengirim ke laptop...")
    
    try:
        if update.message.document:
            file = await context.bot.get_file(update.message.document.file_id)
            filename = update.message.document.file_name
        elif update.message.photo:
            file = await context.bot.get_file(update.message.photo[-1].file_id)
            filename = f"photo_{update.message.message_id}.jpg"
        else:
            return

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            await file.download_to_drive(custom_path=tmp_file.name)
            
            headers = {"X-API-Key": AGENT_API_KEY, "Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient() as client:
                with open(tmp_file.name, "rb") as f:
                    files = {'file': (filename, f)}
                    data = {'user_id': user_id}
                    res = await client.post(f"{AGENT_URL}/file/upload", data=data, files=files, headers=headers)
                    
            if res.status_code == 200:
                msg = res.json().get("message", "Upload berhasil")
                await update.message.reply_text(msg)
                auditor.log_event(user_id, "FILE_UPLOAD", filename)
            else:
                await update.message.reply_text("❌ Gagal mengirim file ke laptop.")
                
        os.remove(tmp_file.name)
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat upload.")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    token = _user_sessions.get(user_id)
    
    if not token or not AuthManager.verify_session_token(token):
        await update.message.reply_text("🔐 Belum login atau sesi expired.")
        return

    if not AuthManager.check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Terlalu banyak perintah.")
        return

    agents = registry.get_all()
    voice_active = False
    for agent_id, data in agents.items():
        try:
            headers = {"X-API-Key": data['api_key']}
            agent_url = f"http://{data['host']}:{data['port']}"
            resp = await httpx.get(f"{agent_url}/system/voice-cmd-status", headers=headers, timeout=5.0)
            if resp.status_code == 200 and resp.json().get("active"):
                voice_active = True
                break
        except Exception:
            pass

    if not voice_active:
        await update.message.reply_text("🔇 Voice command nonaktif. Aktifkan dengan `!voice_cmd on`")
        return

    await update.message.reply_text("🎙️ Memproses pesan suara...")
    
    tmp_ogg = None
    wav_path = None
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        tmp_ogg = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp_ogg.close()
        await voice_file.download_to_drive(custom_path=tmp_ogg.name)
            
        wav_path = tmp_ogg.name + ".wav"
        audio = AudioSegment.from_file(tmp_ogg.name, format="ogg")
        audio.export(wav_path, format="wav")
        
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="id-ID")
            
        await update.message.reply_text(f"🗣️ <b>Anda berkata:</b> {text}", parse_mode="HTML")
        
        update.message.text = text
        await message_handler(update, context)
        
    except sr.UnknownValueError:
        await update.message.reply_text("❌ Suara tidak terdengar jelas.")
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("❌ Gagal memproses pesan suara.")
    finally:
        if tmp_ogg and os.path.exists(tmp_ogg.name):
            os.remove(tmp_ogg.name)
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)

async def poll_terminal(user_id: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int, agent_url: str, agent_api_key: str):
    token = _user_sessions.get(user_id)
    headers = {
        "X-API-Key": agent_api_key,
        "Authorization": f"Bearer {token}"
    }
    
    accumulated_output = ""
    
    while _terminal_mode.get(user_id):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{agent_url}/terminal/read/{user_id}", headers=headers, timeout=10)
                if response.status_code == 200:
                    output = response.json().get("output", "")
                    if output:
                        accumulated_output += output
                        if len(accumulated_output) > 2000 or "\n" in output:
                            text = f"<code>{accumulated_output[-4000:]}</code>"
                            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                            accumulated_output = ""
                elif response.status_code == 401:
                    break
        except Exception as e:
            logger.error(f"Error polling terminal for {user_id}: {e}")
        
        await asyncio.sleep(1.5)
    
    if accumulated_output:
        await context.bot.send_message(chat_id=chat_id, text=f"<code>{accumulated_output}</code>", parse_mode="HTML")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    user_id = str(update.effective_user.id)
    message_text = override_text if override_text is not None else (update.message.text.strip() if update.message.text else "")

    if message_text.lower() == "!menu":
        await menu_command(update, context)
        return

    quick = message_text.strip().lower()
    if quick in CMD_MAP:
        message_text = CMD_MAP[quick]

    token = _user_sessions.get(user_id)
    if not token:
        await update.message.reply_text("🔐 Belum login. Gunakan /start untuk autentikasi.")
        return

    if not AuthManager.verify_session_token(token):
        del _user_sessions[user_id]
        save_current_sessions()
        await update.message.reply_text("⏰ Sesi expired. Silakan /start ulang.")
        return

    pending = context.user_data.get("pending_cmd")
    if pending and not override_text:
        if message_text.startswith("!"):
            context.user_data["pending_cmd"] = None
        else:
            context.user_data["pending_cmd"] = None
            message_text = pending + message_text.strip()

    # Handle Multi-Agent Commands
    if message_text == "!status" or message_text == "!agents":
        agents = registry.get_all()
        if not agents:
            await update.message.reply_text("📉 Belum ada agent yang terdaftar.")
            return
        
        msg = "🖥️ <b>Daftar Agent:</b>\n"
        for aid in agents.keys():
            mark = "✅" if _user_active_agent.get(user_id) == aid else "▫️"
            msg += f"{mark} <code>{aid}</code>\n"
        msg += "\nGunakan <code>!select &lt;agent_id&gt;</code> untuk memilih target."
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    if message_text.startswith("!select "):
        target_agent = message_text.split(" ", 1)[1].strip()
        if registry.get_agent(target_agent):
            _user_active_agent[user_id] = target_agent
            await update.message.reply_text(f"🎯 Target diubah ke Agent: <b>{target_agent}</b>", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ Agent '{target_agent}' tidak ditemukan.")
        return

    # Determine Active Agent
    active_agent_id = _user_active_agent.get(user_id)
    agents = registry.get_all()
    # Retry once if no agent registered yet (Agent might still be starting up)
    if not agents:
        await asyncio.sleep(3)
        agents = registry.get_all()
    if not active_agent_id:
        if len(agents) == 1:
            active_agent_id = list(agents.keys())[0]
            _user_active_agent[user_id] = active_agent_id
            await update.message.reply_text(f"ℹ️ Auto-select Agent: <b>{active_agent_id}</b>", parse_mode="HTML")
        elif len(agents) > 1:
            await update.message.reply_text("⚠️ Anda memiliki lebih dari 1 Agent.\nGunakan <code>!select &lt;agent_id&gt;</code> terlebih dahulu.", parse_mode="HTML")
            return
        else:
            await update.message.reply_text("❌ Belum ada agent yang terdaftar pada sistem.")
            return

    agent_data = registry.get_agent(active_agent_id)
    if not agent_data:
        del _user_active_agent[user_id]
        await update.message.reply_text("❌ Agent yang dipilih sudah tidak tersedia di registry.")
        return
        
    AGENT_URL = f"http://{agent_data['host']}:{agent_data['port']}"
    AGENT_API_KEY = agent_data['api_key']

    if message_text in ["!term", "!exit"]:
        if message_text == "!term":
            if _terminal_mode.get(user_id):
                await update.message.reply_text("⚠️ Anda sudah berada dalam Mode Terminal.")
                return
            headers = {"X-API-Key": AGENT_API_KEY, "Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient() as client:
                try:
                    res = await client.post(f"{AGENT_URL}/terminal/start", json={"user_id": user_id}, headers=headers)
                    if res.status_code == 200:
                        _terminal_mode[user_id] = True
                        await update.message.reply_text(f"💻 <b>Mode Terminal Aktif ({active_agent_id})</b>", parse_mode="HTML")
                        # Pass AGENT_URL and AGENT_API_KEY directly since they are dynamically resolved
                        task = asyncio.create_task(poll_terminal(user_id, context, update.effective_chat.id, AGENT_URL, AGENT_API_KEY))
                        _terminal_tasks[user_id] = task
                    else:
                        await update.message.reply_text("❌ Gagal memulai terminal.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error: {e}")
        else:
            _terminal_mode[user_id] = False
            if user_id in _terminal_tasks:
                _terminal_tasks[user_id].cancel()
                del _terminal_tasks[user_id]
            headers = {"X-API-Key": AGENT_API_KEY, "Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient() as client:
                await client.post(f"{AGENT_URL}/terminal/stop", json={"user_id": user_id}, headers=headers)
            await update.message.reply_text("👋 Mode Terminal dinonaktifkan.")
        return

    if _terminal_mode.get(user_id):
        processed_text = message_text
        if message_text.startswith("agy ") and "--yolo" not in message_text:
            processed_text = message_text.replace("agy ", "agy --yolo ", 1)
            logger.info(f"Auto-injected --yolo for agy command from {user_id}")
        elif message_text.startswith("opencode ") and "--dangerously-skip-permissions" not in message_text:
            processed_text = message_text.replace("opencode ", "opencode --dangerously-skip-permissions ", 1)
            logger.info(f"Auto-injected --dangerously-skip-permissions for opencode command from {user_id}")

        headers = {"X-API-Key": AGENT_API_KEY, "Authorization": f"Bearer {token}"}
        
        # If terminal command is 'cd', update the global CWD in CommandHandler as well
        if message_text.startswith("cd "):
            target_dir = message_text[3:].strip()
            # We forward this to the agent's CWD state for dedicated commands
            async with httpx.AsyncClient() as client:
                await client.post(f"{AGENT_URL}/command", json={"command": f"!cd {target_dir}", "user_id": user_id}, headers=headers)

        async with httpx.AsyncClient() as client:
            try:
                await client.post(f"{AGENT_URL}/terminal/write", json={"user_id": user_id, "data": processed_text + "\n"}, headers=headers)
            except Exception as e:
                await update.message.reply_text(f"❌ Error writing to terminal: {e}")
        return

    if message_text.startswith("!schedule "):
        try:
            parts = message_text.split(" ", 3)
            if parts[1] == "in":
                time_str = parts[2]
                command_to_run = parts[3]
                
                # Parse time
                unit = time_str[-1]
                value = int(time_str[:-1])
                multiplier = {"s": 1, "m": 60, "h": 3600}.get(unit, 1)
                sleep_seconds = value * multiplier
                
                async def scheduled_task(delay, cmd):
                    await asyncio.sleep(delay)
                    # Use override_text to avoid mutating immutable Update object
                    await message_handler(update, context, override_text=cmd)
                
                asyncio.create_task(scheduled_task(sleep_seconds, command_to_run))
                await update.message.reply_text(f"✅ Perintah `{command_to_run}` dijadwalkan berjalan dalam {time_str}.")
                return
        except Exception as e:
            await update.message.reply_text("❌ Format salah. Gunakan: `!schedule in 30m !lock`")
            return

    cmd_clean = message_text.lower().split()[0] if message_text else ""
    DANGEROUS = {"!reboot","!shutdown","!poweroff","!halt","!logout","!lock","!unlock","!kill","!rm","!delete","!guard"}
    if cmd_clean in DANGEROUS:
        confirm_id = f"confirm_{user_id}_{hash(message_text)}"
        context.user_data[confirm_id] = message_text
        kb = [[
            InlineKeyboardButton("✅ Ya, jalankan", callback_data=confirm_id),
            InlineKeyboardButton("❌ Batalkan", callback_data=f"cancel_{confirm_id}"),
        ]]
        await update.message.reply_text(
            f"⚠️ <b>Konfirmasi</b>\nYakin ingin menjalankan:\n<code>{escape(message_text)}</code>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    if not AuthManager.check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Terlalu banyak perintah.")
        return

    processing_msg = await update.message.reply_text(f"⏳ <b>{active_agent_id}</b> sedang memproses...", parse_mode="HTML")
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

    try:
        headers = {"X-API-Key": AGENT_API_KEY, "Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{AGENT_URL}/command", json={"command": message_text, "user_id": user_id}, headers=headers, timeout=180)

        # Delete processing message before sending result
        await processing_msg.delete()

        if res.status_code == 200:
            add_history(context, message_text)
            result = res.json()
            res_type = result.get("type")
            content = result.get("content")
            
            if res_type == "text":
                if content.lstrip().startswith("🤖 <b>Remote Laptop Control"):
                    sections = re.split(r'(?=<b>\d+\.)', content)
                    sections = [s for s in sections if s.strip()]
                    if len(sections) > 1:
                        sections[0] = sections[0] + '\n' + sections.pop(1)
                    context.user_data["help_sections"] = sections
                    sections[0] = format_section_text(sections[0])
                    btn_data = [
                        ("📷 Media", "help_1"),
                        ("⌨️ Input", "help_2"),
                        ("📁 File", "help_3"),
                        ("🤖 AI", "help_4"),
                    ]
                    btn_data2 = [
                        ("⚙️ Sistem", "help_5"),
                        ("✅ Produktivitas", "help_6"),
                        ("🤖 AI Beta", "help_7"),
                    ]
                    btn_data3 = [
                        ("📡 File Beta", "help_8"),
                        ("🚀 Sys Beta", "help_9"),
                        ("⚡ Pro Beta", "help_10"),
                    ]
                    keyboard = [
                        [InlineKeyboardButton(t, callback_data=d) for t, d in btn_data],
                        [InlineKeyboardButton(t, callback_data=d) for t, d in btn_data2],
                        [InlineKeyboardButton(t, callback_data=d) for t, d in btn_data3],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    intro = sections[0].strip() + "\n\nPilih section:"
                    await update.message.reply_text(intro, parse_mode="HTML", reply_markup=reply_markup)
                else:
                    is_ai = message_text.strip().lower().startswith("!ai ")
                    if is_ai:
                        formatted_content = markdown_to_html(content)
                        MAX_MSG = 4000
                        if len(formatted_content) > MAX_MSG:
                            lines = formatted_content.split('\n')
                            chunk = ''
                            for line in lines:
                                if chunk and len(chunk) + len(line) + 1 > MAX_MSG:
                                    await update.message.reply_text(chunk.strip(), parse_mode="HTML")
                                    chunk = line + '\n'
                                else:
                                    chunk += line + '\n'
                            if chunk.strip():
                                await update.message.reply_text(chunk.strip(), parse_mode="HTML")
                        else:
                            await update.message.reply_text(formatted_content, parse_mode="HTML")
                    else:
                        MAX_MSG = 4000
                        if len(content) > MAX_MSG:
                            lines = content.split('\n')
                            chunk = ''
                            for line in lines:
                                if chunk and len(chunk) + len(line) + 1 > MAX_MSG:
                                    await update.message.reply_text(chunk.strip(), parse_mode="HTML")
                                    chunk = line + '\n'
                                else:
                                    chunk += line + '\n'
                            if chunk.strip():
                                await update.message.reply_text(chunk.strip(), parse_mode="HTML")
                        else:
                            await update.message.reply_text(f"✅ <b>Hasil:</b>\n<code>{escape(content)}</code>", parse_mode="HTML")
            elif res_type == "image":
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_PHOTO)
                import base64
                kwargs = {"photo": base64.b64decode(content)}
                caption = result.get("caption")
                if caption:
                    kwargs["caption"] = caption
                    kwargs["parse_mode"] = "HTML"
                await update.message.reply_photo(**kwargs)
            elif res_type == "video":
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_VIDEO)
                import base64
                if isinstance(content, dict):
                    await update.message.reply_video(base64.b64decode(content["data"]), filename=content.get("filename", "video.mp4"), caption="📹 Rekaman Layar Berhasil")
                else:
                    await update.message.reply_video(base64.b64decode(content), caption="📹 Live Stream Berhasil")
            elif res_type == "audio":
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.RECORD_VOICE)
                import base64
                audio_data = result.get("content", {})
                await update.message.reply_audio(audio=base64.b64decode(audio_data["data"]), filename=audio_data["filename"], caption="🎵 Rekaman Suara Berhasil")
            elif res_type == "document":
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
                import base64
                doc_data = result.get("content", {})
                await update.message.reply_document(document=base64.b64decode(doc_data["data"]), filename=doc_data["filename"])
        elif res.status_code == 400:
            await update.message.reply_text(f"⚠️ <b>Permintaan Ditolak:</b>\n{res.json().get('detail')}", parse_mode="HTML")
        elif res.status_code == 401:
            await update.message.reply_text("❌ <b>Sesi Kadaluarsa:</b> Silakan login kembali dengan <code>/otp</code>", parse_mode="HTML")
        elif res.status_code == 404:
            await update.message.reply_text("❌ <b>Agent Tidak Merespons:</b> Endpoint tidak ditemukan.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ <b>Error Agent ({res.status_code}):</b> Gagal memproses perintah.", parse_mode="HTML")
            
    except httpx.TimeoutException:
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except Exception:
                pass
        retry_kb = [[InlineKeyboardButton("🔄 Coba Lagi", callback_data=f"retry_{user_id}")]]
        context.user_data[f"retry_{user_id}"] = message_text
        await update.message.reply_text("⏳ <b>Waktu Habis:</b> Agent terlalu lama merespons. Mungkin sedang memproses tugas berat.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(retry_kb))
    except Exception as e:
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except Exception:
                pass
        import traceback
        logger.error(f"Command error ({type(e).__module__}.{type(e).__name__}): {e}\n{traceback.format_exc()}")
        retry_kb = [[InlineKeyboardButton("🔄 Coba Lagi", callback_data=f"retry_{user_id}")]]
        context.user_data[f"retry_{user_id}"] = message_text
        await update.message.reply_text("❌ <b>Koneksi Gagal:</b> Tidak dapat menghubungi Agent. Pastikan Agent sedang online.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(retry_kb))

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name or "User"

    if not AuthManager.is_user_allowed(user_id):
        await update.message.reply_text("❌ <b>Akses Ditolak</b>\nAnda tidak terdaftar sebagai pengguna bot ini.", parse_mode="HTML")
        return

    if os.environ.get("DEV_MODE_ENABLED") == "true":
        token = AuthManager.generate_session_token(user_id)
        _user_sessions[user_id] = token
        save_current_sessions()
    else:
        existing = _user_sessions.get(user_id)
        if not existing or not AuthManager.verify_session_token(existing):
            btn = [[InlineKeyboardButton("🔑 Kirim OTP", callback_data="request_otp")]]
            await update.message.reply_text(
                f"👋 <b>Selamat datang, {user_name}!</b>\n\n"
                "🔐 <b>Remote Laptop Control</b>\n"
                "Kontrol laptop Anda dari jarak jauh melalui Telegram.\n\n"
                "Silakan login terlebih dahulu:\n"
                "<code>/otp &lt;kode&gt;</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(btn),
            )
            return

    hostname = "unknown"
    try:
        import socket
        hostname = socket.gethostname()
    except Exception:
        pass
    await update.message.reply_text(
        f"👋 <b>Selamat datang, {user_name}!</b>\n\n"
        f"✅ <b>Remote Laptop Control</b>\n"
        f"🖥️  <code>{hostname}</code>\n"
        f"📡 Status: <b>Terhubung</b>\n\n"
        f"Tap tombol di bawah untuk perintah cepat, atau buka menu di bawah.",
        parse_mode="HTML",
        reply_markup=reply_keyboard(),
    )
    await menu_command(update, context)

async def otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Gunakan: /otp 123456")
        return
    otp_code = context.args[0]
    if AuthManager.verify_otp(otp_code):
        token = AuthManager.generate_session_token(user_id)
        _user_sessions[user_id] = token
        save_current_sessions()
        await update.message.reply_text("✅ <b>Login berhasil!</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ OTP salah.")

async def logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    token = _user_sessions.pop(user_id, None)
    save_current_sessions()
    if token:
        AuthManager.revoke_token(token)
    await update.message.reply_text("👋 Logout berhasil.")

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "show_help":
        sections = context.user_data.get("help_sections")
        if not sections:
            sections = re.split(r'(?=<b>\d+\.)', HELP_TEXT)
            sections = [s for s in sections if s.strip()]
            if len(sections) > 1:
                sections[0] = sections[0] + '\n' + sections.pop(1)
            context.user_data["help_sections"] = sections
        btn_a = [("📷 Media","help_1"),("⌨️ Input","help_2"),("📁 File","help_3"),("🤖 AI","help_4")]
        btn_b = [("⚙️ Sistem","help_5"),("✅ Produktivitas","help_6"),("🤖 AI Beta","help_7")]
        btn_c = [("📡 File Beta","help_8"),("🚀 Sys Beta","help_9"),("⚡ Pro Beta","help_10")]
        keyboard = [
            [InlineKeyboardButton(t,callback_data=d) for t,d in btn_a],
            [InlineKeyboardButton(t,callback_data=d) for t,d in btn_b],
            [InlineKeyboardButton(t,callback_data=d) for t,d in btn_c],
        ]
        intro_table = format_section_text(sections[0].strip())
        await query.edit_message_text(intro_table + "\n\nPilih section:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "request_otp":
        await query.edit_message_text(
            "🔐 <b>Autentikasi</b>\n\n"
            "Gunakan perintah:\n"
            "<code>/otp &lt;kode&gt;</code>\n\n"
            "Kode OTP akan muncul di layar laptop Anda.",
            parse_mode="HTML",
        )

def format_section_text(text: str) -> str:
    return text.strip()

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sections = context.user_data.get("help_sections", [])
    idx = int(query.data.replace("help_", ""))
    list_idx = idx - 1
    if 0 <= list_idx < len(sections):
        raw = sections[list_idx].strip()
        table_text = format_section_text(raw)
        await query.edit_message_text(table_text, parse_mode="HTML")
    else:
        await query.edit_message_text("Section tidak ditemukan.")

def menu_markup(menu):
    btns = {"main": [("📷 Capture","m_cap"),("🖥 System","m_sys"),("⌨️ Input","m_inp")],
            "main2": [("📁 Files","m_file"),("🔊 Audio","m_audio"),("🤖 AI","m_ai")],
            "main3": [("⚙️ Tools","m_tools"),("📋 Tasks","m_tasks"),("🕐 Recent","m_recent")],
            "main4": [("📖 Bantuan","show_help")]}
    sub = {
        "m_cap": ([("📸 Screenshot","cmd_ss"),("🎥 Record 10s","cmd_vid"),("📹 Webcam","cmd_webcam")], "main"),
        "m_sys": ([("ℹ️ Info","cmd_info"),("🔋 Baterai","cmd_bat"),("📶 Speedtest","cmd_speed"),("🌐 WiFi","cmd_wifi"),("☀️ Brightness","cmd_brightness_"),("🔒 Lock","cmd_lock"),("🔄 Reboot","cmd_reboot")], "main"),
        "m_inp": ([("⌨️ Type teks","cmd_type_"),("🔘 Press tombol","cmd_press_"),("🖱 Click (x y)","cmd_click_"),("🪟 Window","cmd_win_"),("🚀 Launch","cmd_launch_")], "main"),
        "m_file": ([("📂 List","cmd_ls_"),("📄 Get file","cmd_get_"),("🔍 Find","cmd_find_"),("📂 CD","cmd_cd_")], "main"),
        "m_audio": ([("🔊 Volume","cmd_volume_"),("🎵 Media","cmd_media_"),("💬 Notif","cmd_notif_"),("🔊 TTS","cmd_tts_"),("🎤 Record","cmd_listen")], "main"),
        "m_ai": ([("🤖 OpenCode","cmd_opencode"),("🧠 Agy","cmd_agy"),("🔎 Web Search","cmd_web_"),("❓ Test AI","cmd_testai")], "main"),
        "m_tools": ([("🌐 Ping","cmd_ping_"),("📡 Ports","cmd_ports"),("🔋 Battery","cmd_bat"),("🔌 Speedtest","cmd_speed"),("🗑️ Logout","cmd_logout")], "main"),
        "m_tasks": ([("📋 Todo","cmd_todo_"),("⏰ Reminder","cmd_reminder_"),("📊 Daily","cmd_daily_"),("🎯 Focus","cmd_focus_"),("📝 Quicknote","cmd_quicknote_")], "main"),
        "m_recent": ([], "main"),
    }
    if menu == "main":
        kb = [[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in [btns["main"], btns["main2"], btns["main3"], btns["main4"]]]
    elif menu in sub:
        items, back = sub[menu]
        kb = [[InlineKeyboardButton(t,callback_data=d) for t,d in items]]
        rows = [items[i:i+2] for i in range(0,len(items),2)]
        kb = [[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows]
        kb.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")])
    else:
        kb = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")]]
    return InlineKeyboardMarkup(kb)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(update.effective_user.id)

    if data == "menu_main":
        await query.edit_message_text("📋 <b>MAIN MENU</b>\nPilih kategori:", parse_mode="HTML", reply_markup=menu_markup("main"))
        return

    if data.startswith("m_"):
        labels = {"m_cap":"📷 CAPTURE","m_sys":"🖥 SYSTEM","m_inp":"⌨️ INPUT","m_file":"📁 FILES","m_audio":"🔊 AUDIO","m_ai":"🤖 AI","m_tools":"⚙️ TOOLS","m_tasks":"📋 TASKS","m_recent":"🕐 RECENT"}
        label = labels.get(data, "MENU")
        if data == "m_recent":
            hist = context.user_data.get("cmd_history", [])
            if not hist:
                await query.edit_message_text("Belum ada riwayat perintah.", parse_mode="HTML")
                return
            items = [(f"🔄 {h[:30]}", f"hist_{i}") for i, h in enumerate(hist)]
            context.user_data["_hist_cmds"] = hist
            rows = [items[i:i+2] for i in range(0,len(items),2)]
            rows.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")])
            await query.edit_message_text(f"<b>{label}</b>\nTap untuk ulangi:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
            return
        await query.edit_message_text(f"<b>{label}</b>\nPilih perintah:", parse_mode="HTML", reply_markup=menu_markup(data))
        return

    if data.startswith("cmd_"):
        noarg = {"cmd_ss":"!screenshot","cmd_vid":"!video 10","cmd_webcam":"!webcam",
                 "cmd_info":"!sysinfo","cmd_bat":"!battery","cmd_speed":"!speedtest","cmd_wifi":"!wifi",
                 "cmd_opencode":"!opencode","cmd_agy":"!agy","cmd_testai":"!testai",
                 "cmd_ports":"!ports","cmd_lock":"!lock","cmd_reboot":"!reboot",
                 "cmd_listen":"!listen 10","cmd_logout":"!logout"}
        if data in noarg:
            await execute_and_reply(update, context, noarg[data])
            return
        prompt = ARG_PROMPTS.get(data)
        if prompt:
            context.user_data["pending_cmd"] = f"!{data[4:]} "
            await query.edit_message_text(prompt, parse_mode="HTML")
        else:
            await query.edit_message_text(f"Gunakan: <code>!{data[4:]}</code>", parse_mode="HTML")
        return

    if data.startswith("hist_"):
        idx = int(data.replace("hist_", ""))
        cmds = context.user_data.get("_hist_cmds", [])
        if idx < len(cmds):
            await execute_and_reply(update, context, cmds[idx])
        return

async def command_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    cmd = text[1:].replace("_", " ")
    if cmd.split()[0] in ("start", "menu", "otp", "logout"):
        return
    await message_handler(update, context, override_text=f"!{cmd}")

async def execute_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    token = _user_sessions.get(user_id)
    if not token:
        await query.answer("🔐 Belum login.")
        return
    agent_data = registry.get_active(user_id)
    if not agent_data:
        await query.answer("❌ Tidak ada agent aktif.")
        return
    api_key = agent_data["api_key"]
    agent_url = f"http://{agent_data['host']}:{agent_data['port']}"
    headers = {"X-API-Key": api_key, "Authorization": f"Bearer {token}"}
    await query.answer("⏳ Memproses...")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(f"{agent_url}/command", json={"command": cmd, "user_id": user_id}, headers=headers, timeout=180)
            if res.status_code == 200:
                rdata = res.json()
                if rdata.get("type") == "text":
                    content = rdata.get("content", "")
                    if cmd.strip().lower().startswith("!ai "):
                        formatted_content = markdown_to_html(content)
                        await context.bot.send_message(chat_id=update.effective_chat.id,
                            text=formatted_content[:4000], parse_mode="HTML")
                    else:
                        await context.bot.send_message(chat_id=update.effective_chat.id,
                            text=f"✅ <b>{cmd}</b>\n<code>{escape(content[:3500])}</code>", parse_mode="HTML")
                elif rdata.get("type") == "image":
                    import base64
                    await context.bot.send_photo(chat_id=update.effective_chat.id,
                        photo=base64.b64decode(rdata["content"]))
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                        text=f"✅ <b>{cmd}</b> selesai.", parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                    text=f"⚠️ Error: {res.status_code}", parse_mode="HTML")
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                text=f"❌ Gagal: {e}", parse_mode="HTML")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 <b>MAIN MENU</b>\nPilih kategori:", parse_mode="HTML", reply_markup=menu_markup("main"))

HISTORY_MAX = 5

def add_history(context: ContextTypes.DEFAULT_TYPE, cmd: str):
    hist = context.user_data.setdefault("cmd_history", [])
    if cmd in hist:
        hist.remove(cmd)
    hist.insert(0, cmd)
    context.user_data["cmd_history"] = hist[:HISTORY_MAX]

async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = context.user_data.get(query.data)
    if not cmd:
        await query.edit_message_text("⏰ Sesi kadaluarsa. Kirim ulang perintah.")
        return
    context.user_data.pop(query.data, None)
    await query.edit_message_text(f"🔄 Mencoba ulang: <code>{escape(cmd)}</code>", parse_mode="HTML")
    await message_handler(update, context, override_text=cmd)

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("cancel_"):
        await query.edit_message_text("❌ Perintah dibatalkan.")
        return
    cmd = context.user_data.get(data)
    if not cmd:
        await query.edit_message_text("⏰ Sesi konfirmasi kadaluarsa.")
        return
    context.user_data.pop(data, None)
    await query.edit_message_text(f"✅ Menjalankan: <code>{escape(cmd)}</code>", parse_mode="HTML")
    await message_handler(update, context, override_text=cmd)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    if isinstance(context.error, TimedOut):
        logger.warning("Telegram API TimedOut. Retrying internal loop...")
    elif isinstance(context.error, NetworkError):
        logger.warning(f"Network error: {context.error}. Bot will attempt to recover.")
    else:
        logger.error(f"Update {update} caused error {context.error}")

if __name__ == "__main__":
    # Increased connect and read timeouts for unstable networks
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).connect_timeout(60).read_timeout(60).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("otp", otp_handler))
    app.add_handler(CommandHandler("logout", logout_handler))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^(show_help|request_otp)$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(menu_main|m_|cmd_)"))
    app.add_handler(CallbackQueryHandler(confirm_callback, pattern="^(confirm_|cancel_confirm_)"))
    app.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    app.add_handler(MessageHandler(filters.COMMAND, command_fallback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, document_handler))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))

    logger.info("Starting Telegram bot...")
    
    # Ensure event loop exists for Python 3.10+ (fixes RuntimeError in some environments)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    app.run_polling(drop_pending_updates=True)
