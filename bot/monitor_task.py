"""
Monitor Task — Mengelola status Agent dan Alerting.
Mendukung Pull Model (Bot -> Agent) dan transisi state ONLINE/DEGRADED/OFFLINE.
"""
import asyncio
import time
import httpx
from loguru import logger
from telegram.ext import Application
import os
from html import escape

# State monitoring: {agent_id: {"state": "ONLINE", "last_seen": timestamp}}
_agent_status = {}
_status_lock: asyncio.Lock | None = None

def _get_lock() -> asyncio.Lock:
    global _status_lock
    if _status_lock is None:
        _status_lock = asyncio.Lock()
    return _status_lock

# Thresholds
TIMEOUT_DEGRADED = 90   # 1.5 menit tanpa heartbeat
TIMEOUT_OFFLINE = 180    # 3 menit tanpa heartbeat

class MonitorTask:
    def __init__(self, app: Application):
        self.app = app
        raw_ids = os.environ.get("ALLOWED_USER_IDS", "")
        self.allowed_users = set(uid.strip() for uid in raw_ids.split(",") if uid.strip())
        logger.info(f"MonitorTask initialized for users: {self.allowed_users}")

    async def update_heartbeat(self, agent_id: str, metrics: dict):
        """Update last seen dan cek transisi state."""
        now = time.time()
        alert_msg = None
        
        async with _get_lock():
            prev_data = _agent_status.get(agent_id, {"state": "OFFLINE", "last_seen": 0})
            prev_state = prev_data["state"]

            _agent_status[agent_id] = {
                "state": "ONLINE",
                "last_seen": now,
                "metrics": metrics
            }

            if prev_state != "ONLINE":
                cpu = escape(str(metrics.get('cpu', '0')))
                ram = escape(str(metrics.get('ram', '0')))
                alert_msg = f"✅ <b>Agent Online:</b> {escape(agent_id)}\nMetrics: CPU {cpu}% | RAM {ram}%"
                logger.info(f"Agent {agent_id} transitioned to ONLINE")
                
        if alert_msg:
            await self._broadcast_alert(alert_msg)

    async def _check_status_once(self, now: float):
        """Satu iterasi pengecekan status (dipisahkan untuk testing)."""
        alerts_to_send = []
        
        async with _get_lock():
            for agent_id, data in list(_agent_status.items()):
                elapsed = now - data["last_seen"]
                current_state = data["state"]

                if elapsed > TIMEOUT_OFFLINE and current_state != "OFFLINE":
                    data["state"] = "OFFLINE"
                    alerts_to_send.append(
                        f"🔴 <b>Agent Offline:</b> {escape(agent_id)}\n"
                        f"Terakhir terlihat {int(elapsed/60)} menit yang lalu."
                    )
                    logger.warning(f"Agent {agent_id} transitioned to OFFLINE")

                elif elapsed > TIMEOUT_DEGRADED and current_state == "ONLINE":
                    data["state"] = "DEGRADED"
                    alerts_to_send.append(
                        f"⚠️ <b>Agent Degraded:</b> {escape(agent_id)}\n"
                        f"Koneksi mungkin fluktuatif."
                    )
                    logger.warning(f"Agent {agent_id} transitioned to DEGRADED")
                    
        for msg in alerts_to_send:
            await self._broadcast_alert(msg)

    async def _check_todo_deadlines_once(self):
        """Memeriksa tenggat waktu todo dan mengirimkan pengingat jika sudah lewat/waktunya."""
        import json
        import subprocess
        from datetime import datetime
        
        todo_file = "todo.json"
        if not os.path.exists(todo_file):
            return

        try:
            with open(todo_file, "r") as f:
                todos = json.load(f)
        except Exception:
            return

        updated = False
        now = datetime.now()

        for item in todos:
            if not item.get("done", False) and item.get("deadline") and not item.get("reminded", False):
                try:
                    deadline_dt = datetime.strptime(item["deadline"], "%Y-%m-%d %H:%M")
                    if now >= deadline_dt:
                        item["reminded"] = True
                        updated = True
                        
                        task_desc = item["task"]
                        deadline_str = item["deadline"]
                        
                        # 1. Kirim alert teks ke Telegram
                        msg = (
                            f"⏱️ <b>PENGINGAT TUGAS (TODO):</b>\n"
                            f"Tugas \"<b>{escape(task_desc)}</b>\" sudah mencapai tenggat waktu ({escape(deadline_str)})!"
                        )
                        await self._broadcast_alert(msg)

                        # 2. Kirim desktop notification di laptop
                        try:
                            subprocess.Popen(
                                ["notify-send", "Pengingat RAV-SPY", f"Tugas: {task_desc} sudah mencapai tenggat waktu!"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                        except Exception:
                            pass

                        # 3. Hasilkan TTS suara, kirim voice note ke Telegram, dan putar suara di laptop
                        import tempfile
                        import shutil
                        
                        voice = "id-ID-GadisNeural"
                        temp_dir = tempfile.gettempdir()
                        temp_mp3 = os.path.join(temp_dir, f"todo_remind_{int(time.time())}.mp3")
                        tts_text = f"Halo! Mengingatkan tugas Anda: {task_desc} sudah mencapai tenggat waktu!"
                        
                        try:
                            import edge_tts
                            communicate = edge_tts.Communicate(tts_text, voice)
                            await communicate.save(temp_mp3)
                            
                            # Kirim voice note ke Telegram
                            await self._broadcast_voice_alert(
                                temp_mp3, 
                                caption=f"🗣️ Asisten Suara: Tenggat tugas '{task_desc}' tiba!"
                            )
                            
                            # Putar suara di speaker laptop secara lokal jika diatur speak_local
                            if item.get("speak_local", False):
                                player = None
                                for p in ["mpg123", "mpv", "play", "ffplay", "paplay", "vlc"]:
                                    if shutil.which(p):
                                        player = p
                                        break
                                if player:
                                    if player == "ffplay":
                                        subprocess.Popen(["ffplay", "-nodisp", "-autoexit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    elif player == "vlc":
                                        subprocess.Popen(["cvlc", "--play-and-exit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    else:
                                        subprocess.Popen([player, temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception as tts_err:
                            logger.error(f"Failed to play or broadcast TTS voice alert: {tts_err}")
                            
                except Exception as e:
                    logger.error(f"Error parsing or reminding todo: {e}")

        if updated:
            try:
                with open(todo_file, "w") as f:
                    json.dump(todos, f, indent=4)
            except Exception as e:
                logger.error(f"Error saving updated todos: {e}")

    async def _check_file_watcher_once(self):
        """Poll file watcher changes from agent and broadcast to users."""
        agent_url = f"http://{os.environ.get('AGENT_HOST', 'localhost')}:{os.environ.get('AGENT_PORT', '8765')}"
        api_key = os.environ.get("AGENT_API_KEY", "")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{agent_url}/system/file-watcher-changes",
                    headers={"X-API-Key": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("changes", []):
                        folder = item.get("folder", "")
                        changes = item.get("changes", [])
                        if changes:
                            msg = f"📡 <b>File Watcher:</b> {escape(folder)}\n" + "\n".join(escape(c) for c in changes[:5])
                            await self._broadcast_alert(msg)
        except Exception:
            pass

    async def run_monitoring_loop(self):
        """Background loop untuk mengecek timeout heartbeat dan tenggat waktu todo."""
        while True:
            await self._check_status_once(time.time())
            await self._check_todo_deadlines_once()
            await self._check_file_watcher_once()
            await asyncio.sleep(30)

    async def _broadcast_alert(self, message: str):
        """Kirim pesan ke semua user yang terdaftar."""
        for user_id in self.allowed_users:
            try:
                if user_id:
                    logger.info(f"Broadcasting alert to {user_id}...")
                    # Set high timeout for slow networks
                    await self.app.bot.send_message(
                        chat_id=user_id, 
                        text=message, 
                        parse_mode="HTML",
                        read_timeout=60,
                        connect_timeout=60
                    )
                    logger.info(f"Successfully broadcasted to {user_id}")
            except Exception as e:
                logger.error(f"Failed to broadcast alert to {user_id}: {e}")

    async def _broadcast_voice_alert(self, file_path: str, caption: str):
        """Kirim voice note audio ke semua user yang terdaftar."""
        for user_id in self.allowed_users:
            try:
                if user_id:
                    logger.info(f"Broadcasting voice alert to {user_id}...")
                    with open(file_path, "rb") as voice_file:
                        await self.app.bot.send_voice(
                            chat_id=user_id,
                            voice=voice_file,
                            caption=caption,
                            read_timeout=60,
                            connect_timeout=60
                        )
                    logger.info(f"Successfully broadcasted voice alert to {user_id}")
            except Exception as e:
                logger.error(f"Failed to broadcast voice alert to {user_id}: {e}")
