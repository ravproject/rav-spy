# RAV-SPY AI: Implementation Plan for 50 New Features

> **Document Version:** 1.0
> **Architecture:** Python 3.11+ / Node.js 20+ (WhatsApp)
> **Status:** Planning Phase — Not yet implemented

---

## 1. PRE-IMPLEMENTATION AUDIT: Features That ALREADY Exist

Before building anything new, the following requested features **already exist** in the codebase.
Per `REBUILD_FEATURE.md` and `DEVELOPMENT_RULES.md`, these must NOT be rebuilt:

| Requested Feature | Existing Equivalent | File(s) | Notes |
|---|---|---|---|
| `!quick upload` | File upload via `Document.ALL`/`PHOTO` handler | `bot/telegram_bot.py:119` | Already works — send file from HP |
| `!schedule` | `!schedule in <time> <cmd>` | `bot/telegram_bot.py:352-375`, `bot/command_router.py:151-153` | Extend, don't rebuild |
| `!volume` | `!volume <level>` | `bot/command_router.py:145-149`, `agent/command_handler.py:189-219` | Works |
| `!mute` | `!mute` | Same as above | Works |
| `!alarm` | `!alarm` | Same as above | Works |
| `!battery health` | `!battery` | `bot/command_router.py:192-195`, `agent/command_handler.py:528-595` | Already shows health % |
| `!window [minimize\|close]` | `!win` / `!winctl` | `bot/command_router.py:262-266`, `agent/command_handler.py:919-978` | Extend for arrange/snap |
| `!smart clipboard` | `!clip sync` | `agent/command_handler.py:679-698` | Already does auto-sync |
| `!voice cmd` | Voice handler via `filters.VOICE` | `bot/telegram_bot.py:161-201` | Voice notes already processed |
| `!quick app` | `!launch` | `bot/command_router.py:284-288`, `agent/command_handler.py:1297-1340` | Same concept |
| `!launch advanced` | `!launch` | Same as above | Extend with args param |
| `!search content` | `!find` | `bot/command_router.py:239-243`, `agent/command_handler.py:700-731` | `!find` already does recursive search |
| `!recent files` | `!find` (with pattern) | Same as above | Minor extension needed |

**Action:** These features should be **extended** (not rebuilt) by modifying existing handlers.

---

## 2. ARCHITECTURE & IMPLEMENTATION PATTERNS

### 2.1 Per-Feature Implementation Checklist (for every new command)

Each new feature MUST touch **exactly these files** in order:

```
1. agent/<feature_module>.py         — Core logic (new module)
2. agent/command_handler.py           — Add handler method (import + async def)
3. bot/command_router.py              — Add elif branch
4. ai_module/fallback_parser.py       — Add !command → name mapping (+ aliases)
5. config/allowed_commands.yaml       — Add to safe_commands whitelist
6. ai_module/prompt_templates.py      — Add to SYSTEM_PROMPT
7. tests/test_<feature>.py            — Unit tests
8. tests/test_e2e.py                  — Extend E2E tests for critical features
```

### 2.2 Handler Method Pattern (agent/command_handler.py)

```python
async def handle_<feature>(self, args: list[str]) -> str | dict:
    """Description."""
    try:
        # Logic here
        # Use await asyncio.to_thread() for blocking ops
        # Use logger for key events
        return "Result string"
    except Exception as e:
        logger.error(f"<Feature> error: {e}")
        return f"Error: {e}"
```

### 2.3 Router Pattern (bot/command_router.py)

```python
elif command_name == "<feature>":
    result = await self.handler.handle_<feature>(args)
    self.auditor.log_event(user_id, "<FEATURE_UPPER>", " ".join(args)[:50])
    return result
```

### 2.4 Response Type Guidelines

| Type | Return from handler | Router handling |
|---|---|---|
| Text | `str` | `return result` |
| Photo | `{"type": "photo", "data": bytes}` | Auto-converted in `agent/main.py` |
| Document | `{"filename": ..., "data": ..., "mimetype": ...}` | Auto-converted |
| Video | `{"type": "video", "data": ..., "filename": ...}` | Auto-converted |

### 2.5 New Files to Create

```
agent/
  focus.py                    — PHASE 1: Focus mode
  workspace.py                — PHASE 1: Workspace manager
  calendar_client.py          — PHASE 1: Google Calendar API client
  quicknote.py                — PHASE 1: Quick notes
  browser_controller.py       — PHASE 1: Browser automation
  reminder.py                 — PHASE 1: Reminder system
  task_sync.py                — PHASE 1: External task sync
  meeting_mode.py             — PHASE 1: Meeting mode
  custom_aliases.py           — PHASE 1: Custom command aliases
  ai_productivity.py          — PHASE 2: AI productivity tools
  macro_recorder.py           — PHASE 2: Macro recording
  insight_engine.py           — PHASE 2: AI daily/weekly insights
  sync_manager.py             — PHASE 3: Sync service (rclone)
  file_converter.py           — PHASE 3: File conversion
  backup_manager.py           — PHASE 3: Backup system
  file_organizer.py           — PHASE 3: File organization
  file_watcher.py             — PHASE 3: File change watcher
  local_version.py            — PHASE 3: Local versioning
  system_cleaner.py           — PHASE 3: Disk cleaner
  power_manager.py            — PHASE 4: Power profiles
  multi_monitor.py            — PHASE 4: Multi-monitor
  sleep_manager.py            — PHASE 4: Sleep/wake RTC
  hotkey_manager.py           — PHASE 4: Global hotkeys
  time_tracker.py             — PHASE 5: Time tracking
  session_manager.py          — PHASE 5: Session handoff
  screen_share.py             — PHASE 5: Screen sharing
  profile_manager.py          — PHASE 5: Profiles
  dashboard.py                — PHASE 5: Dashboard
  vpn_manager.py              — PHASE 5: VPN control
  tunnel_manager.py           — PHASE 5: Reverse tunnel
  ai_autonomous.py            — PHASE 5: Autonomous AI agent
config/
  focus_sites.yaml            — Blocked sites list for focus mode
```

### 2.6 Required New Python Dependencies (to add to requirements.txt)

```txt
# PHASE 1
google-api-python-client>=2.0.0     # !calendar
google-auth-httplib2>=0.1.0         # !calendar
google-auth-oauthlib>=1.0.0         # !calendar
pyautogui>=0.9.54                   # !browser (mouse control)
pynput>=1.7.6                       # !browser, !macro
keyboard>=0.13.5                    # !hotkey

# PHASE 3
python-magic>=0.4.27                # !convert (MIME detection)
send2trash>=1.8.2                   # !clean (safe delete)

# PHASE 4
screen-brightness-control>=0.16.0   # Already handled via brightnessctl

# PHASE 5
speedtest-cli>=2.1.3                # Already exists via speedtest-cli binary
```

---

## 3. PHASE 1: Core Productivity Foundation (PRIORITY: HIGH)

### 3.1 Focus Mode (`!focus`)

**New file:** `agent/focus.py`

```python
"""
Focus Mode — blocks distractions, runs Pomodoro timer, silences notifications.
"""
import asyncio
import subprocess
import time
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

FOCUS_SITES_FILE = Path(__file__).parent.parent / "config" / "focus_sites.yaml"

class FocusManager:
    def __init__(self):
        self.active = False
        self.timer_task = None
        self.start_time = None
        self.duration_minutes = 25  # Default Pomodoro
        self.blocked_sites = self._load_sites()

    def _load_sites(self) -> list[str]:
        try:
            import yaml
            with open(FOCUS_SITES_FILE) as f:
                data = yaml.safe_load(f)
                return data.get("blocked_sites", [])
        except Exception:
            return ["facebook.com", "twitter.com", "instagram.com", "reddit.com", "youtube.com", "tiktok.com"]

    def _block_sites(self):
        """Append to /etc/hosts to block sites (requires /etc/hosts writable or sudo)."""
        # Alternative: use nftables or /etc/hosts
        hosts_path = "/etc/hosts"
        if not os.access(hosts_path, os.W_OK):
            logger.warning("Cannot block sites: /etc/hosts not writable")
            return False
        try:
            with open(hosts_path, "a") as f:
                for site in self.blocked_sites:
                    f.write(f"0.0.0.0 {site}\n")
                    f.write(f"0.0.0.0 www.{site}\n")
            return True
        except Exception as e:
            logger.error(f"Failed to block sites: {e}")
            return False

    def _unblock_sites(self):
        hosts_path = "/etc/hosts"
        if not os.access(hosts_path, os.W_OK):
            return
        try:
            with open(hosts_path, "r") as f:
                lines = f.readlines()
            with open(hosts_path, "w") as f:
                for line in lines:
                    if not any(site in line for site in self.blocked_sites):
                        f.write(line)
        except Exception as e:
            logger.error(f"Failed to unblock sites: {e}")

    def _mute_notifications(self, mute: bool):
        """Mute D-Bus notifications on Linux."""
        try:
            if mute:
                subprocess.run(["notify-send", "RAV-SPY", "Focus Mode: Notifications silenced"], timeout=3)
                subprocess.run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false"], capture_output=True)
            else:
                subprocess.run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "true"], capture_output=True)
        except Exception:
            pass

    def start(self, minutes: int = 25):
        if self.active:
            return "Focus Mode sudah aktif."
        self.active = True
        self.duration_minutes = minutes
        self.start_time = time.time()
        self._mute_notifications(True)
        self._block_sites()
        # Start timer (handled via background task in command_handler)
        return f"Focus Mode AKTIF selama {minutes} menit. Notifikasi dimatikan, situs diblokir."

    def stop(self):
        if not self.active:
            return "Focus Mode tidak aktif."
        self.active = False
        self.start_time = None
        self._mute_notifications(False)
        self._unblock_sites()
        return "Focus Mode DINONAKTIFKAN. Notifikasi dikembalikan, situs dibuka."

    def get_remaining(self) -> str:
        if not self.active or not self.start_time:
            return "Focus Mode tidak aktif."
        elapsed = time.time() - self.start_time
        remaining = max(0, self.duration_minutes * 60 - elapsed)
        mins, secs = divmod(int(remaining), 60)
        return f"Sisa: {mins}:{secs:02d}"

focus_manager = FocusManager()
```

**Changes by file:**

| File | Change |
|---|---|
| `agent/focus.py` | Create new module |
| `agent/command_handler.py` | Add `handle_focus(self, args)` method |
| `bot/command_router.py` | Add `elif command_name == "focus":` before `else:` |
| `ai_module/fallback_parser.py` | Add `"!focus": "focus"` to COMMAND_MAP |
| `config/allowed_commands.yaml` | Add `focus:` entry |
| `ai_module/prompt_templates.py` | Add `!focus on/off <menit>` to SYSTEM_PROMPT |
| `config/focus_sites.yaml` | New file with default blocked sites |

**Handler method:**

```python
async def handle_focus(self, args: list[str]) -> str:
    from agent.focus import focus_manager
    if not args:
        return focus_manager.get_remaining()
    subcmd = args[0].lower()
    if subcmd == "on":
        minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 25
        return focus_manager.start(minutes)
    elif subcmd == "off":
        return focus_manager.stop()
    return 'Gunakan: !focus [on|off] [menit]'
```

---

### 3.2 Workspace Manager (`!workspace`)

**New file:** `agent/workspace.py`

Save/restore state:
- Open windows (`wmctrl -l` / `xdotool` on Linux)
- Browser tabs (via browser extension or `chrome://json` endpoint)
- VSCode workspace state
- Shell sessions, terminal directories
- Stored as JSON in `~/.config/rav-spy/workspaces/<name>.json`

```python
"""
Workspace Manager — save/restore entire work sessions.
"""
import json
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from loguru import logger

WORKSPACE_DIR = Path.home() / ".config" / "rav-spy" / "workspaces"

class WorkspaceManager:
    def __init__(self):
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    def _capture_state(self) -> dict:
        """Capture current desktop state."""
        state = {
            "timestamp": datetime.now().isoformat(),
            "windows": [],
            "env": {}
        }
        # Capture open windows (Linux wmctrl)
        if shutil.which("wmctrl"):
            try:
                res = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5)
                for line in res.stdout.strip().split("\n"):
                    if line:
                        state["windows"].append(line)
            except Exception:
                pass
        return state

    def save(self, name: str) -> str:
        state = self._capture_state()
        filepath = WORKSPACE_DIR / f"{name}.json"
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
        return f"Workspace '{name}' tersimpan ({len(state['windows'])} window terdeteksi)."

    def load(self, name: str) -> str:
        filepath = WORKSPACE_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Workspace '{name}' tidak ditemukan."
        return f"Workspace '{name}' dimuat. (Implementation: restore windows & apps)"

    def list(self) -> str:
        files = list(WORKSPACE_DIR.glob("*.json"))
        if not files:
            return "Belum ada workspace tersimpan."
        lines = ["Daftar Workspace:"]
        for f in sorted(files):
            lines.append(f"  {f.stem}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        filepath = WORKSPACE_DIR / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return f"Workspace '{name}' dihapus."
        return f"Workspace '{name}' tidak ditemukan."

workspace_manager = WorkspaceManager()
```

**Router branch:**
```python
elif command_name == "workspace":
    if not args:
        return "Gunakan: !workspace [save|load|list|delete] <nama>"
    subcmd = args[0].lower()
    ws_name = " ".join(args[1:]) if len(args) > 1 else ""
    from agent.workspace import workspace_manager
    if subcmd == "save":
        result = workspace_manager.save(ws_name or "default")
    elif subcmd == "load":
        result = workspace_manager.load(ws_name or "default")
    elif subcmd == "list":
        result = workspace_manager.list()
    elif subcmd == "delete":
        result = workspace_manager.delete(ws_name)
    else:
        result = "Subperintah tidak dikenal."
    self.auditor.log_event(user_id, "WORKSPACE", f"{subcmd} {ws_name}")
    return result
```

---

### 3.3 Calendar (`!calendar`)

**New file:** `agent/calendar_client.py`

- Google Calendar API with OAuth2
- Token stored in `~/.config/rav-spy/calendar_token.json`
- Commands: `today`, `next`, `list`, `join`, `create`
- `join` extracts Meet/Zoom link from event and opens it via `!open`

**Dependencies:** `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

### 3.4 Quick Note (`!quicknote`)

**New file:** `agent/quicknote.py`

```python
from pathlib import Path
from datetime import datetime

NOTES_DIR = Path.home() / "Documents" / "RAV-Notes"

def create_note(title: str, content: str = "") -> str:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{title.replace(' ', '_')}.md"
    filepath = NOTES_DIR / filename
    with open(filepath, "w") as f:
        f.write(f"# {title}\n\nDate: {datetime.now().isoformat()}\n\n{content}\n")
    return f"Catatan tersimpan: {filepath}"
```

### 3.5 Browser Control (`!browser`)

**New file:** `agent/browser_controller.py`

Uses D-Bus (Chromium/Chrome remote debugging port) and/or `xdotool`:
- `new <url>` — Open new tab
- `list` — List tabs (via chrome.debugger API or wmctrl)
- `close <N>` — Close tab by index
- `scroll <up|down>` — Simulate scroll via xdotool
- `refresh` — Reload current tab
- `search <query>` — Open search in new tab

**Note:** Full browser control without an extension requires Chrome's remote debugging protocol. For initial implementation, use `xdotool`/`ydotool` simulation.

### 3.6 Daily Report (`!daily report`)

**New file:** `agent/daily_report.py`

Aggregates data from:
- `~/.local/share/activitywatch/` (if ActivityWatch installed)
- psutil process logs (sampled every 5 min by background task)
- File modification timestamps in tracked directories
- Output: Focus time, top apps, files edited, system status

Implementation: Lightweight version using psutil logging to JSON, no external dependency.

### 3.7 Reminder (`!reminder`)

**New file:** `agent/reminder.py`

```python
"""
Reminder system — desktop + Telegram notification at scheduled time.
"""
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

REMINDER_FILE = Path.home() / ".config" / "rav-spy" / "reminders.json"

class ReminderManager:
    def __init__(self):
        self.reminders = self._load()
        self._task = None

    def _load(self) -> list:
        if REMINDER_FILE.exists():
            try:
                with open(REMINDER_FILE) as f:
                    return json.load(f)
            except: pass
        return []

    def _save(self):
        REMINDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REMINDER_FILE, "w") as f:
            json.dump(self.reminders, f, indent=2)

    def add(self, text: str, time_str: str) -> str:
        # Parse: "3jam" → +3h, "14:30" → today at 14:30
        now = datetime.now()
        target = None
        try:
            if "jam" in time_str or "h" in time_str:
                hours = int(time_str.replace("jam", "").replace("h", "").strip())
                target = now + timedelta(hours=hours)
            elif "menit" in time_str or "m" in time_str and "jam" not in time_str:
                minutes = int(time_str.replace("menit", "").replace("m", "").strip())
                target = now + timedelta(minutes=minutes)
            elif ":" in time_str:
                parts = time_str.split(":")
                target = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0)
                if target < now:
                    target += timedelta(days=1)
        except: pass
        if not target:
            return "Format waktu tidak dikenal. Gunakan: '30m', '2jam', '14:30'"
        self.reminders.append({"text": text, "time": target.isoformat(), "done": False})
        self._save()
        return f"Pengingat: '{text}' pada {target.strftime('%H:%M %d/%m/%Y')}"

    async def check_loop(self, notify_func):
        """Background loop — checks every 30 seconds."""
        while True:
            now = datetime.now()
            for r in self.reminders:
                if not r.get("done"):
                    try:
                        t = datetime.fromisoformat(r["time"])
                        if now >= t:
                            r["done"] = True
                            self._save()
                            await notify_func(r["text"])
                    except: pass
            await asyncio.sleep(30)
```

### 3.8 Task Sync (`!task sync`)

**New file:** `agent/task_sync.py`

Extends existing `!todo` with external service sync:
- `!task sync add "task" deadline tomorrow` — Sync to Todoist/MS To Do/Google Tasks
- `!task sync list` — Pull from external service
- `!task sync done <id>` — Mark complete everywhere

Initially supports local JSON (reuses `todo.json`). External API sync is optional.

### 3.9 Meeting Mode (`!meeting mode`)

**New file:** `agent/meeting_mode.py`

```python
def prepare_meeting(name: str = "Meeting") -> str:
    # 1. Launch Zoom/Teams/Google Meet
    # 2. Mute notifications
    # 3. Set volume to appropriate level
    # 4. Open shared documents
    return f"Meeting '{name}' siap. Aplikasi dibuka, notifikasi dimatikan."
```

Reuses `!focus` for notification muting and `!launch` for app opening.

### 3.10 Custom Alias (`!custom alias`)

**New file:** `agent/custom_aliases.py`

```python
"""
Custom command aliases — user-defined shortcuts.
"""
import json
from pathlib import Path

ALIAS_FILE = Path.home() / ".config" / "rav-spy" / "aliases.json"

class AliasManager:
    def __init__(self):
        self.aliases = self._load()

    def _load(self) -> dict:
        if ALIAS_FILE.exists():
            try:
                with open(ALIAS_FILE) as f:
                    return json.load(f)
            except: pass
        return {}

    def _save(self):
        ALIAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ALIAS_FILE, "w") as f:
            json.dump(self.aliases, f, indent=2)

    def set(self, name: str, command: str) -> str:
        self.aliases[name.lower()] = command
        self._save()
        return f"Alias '!{name}' dibuat -> {command}"

    def get(self, name: str) -> str | None:
        return self.aliases.get(name.lower())

    def list(self) -> str:
        if not self.aliases:
            return "Belum ada alias."
        lines = ["Daftar Alias:"]
        for name, cmd in self.aliases.items():
            lines.append(f"  !{name} -> {cmd}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        if name.lower() in self.aliases:
            del self.aliases[name.lower()]
            self._save()
            return f"Alias '{name}' dihapus."
        return f"Alias '{name}' tidak ditemukan."
```

**Integration in `command_router.py`:**
Before the main routing, check if `!command_name` matches an alias and expand it.

---

## 4. PHASE 2: AI & Automation Intelligence (PRIORITY: HIGH)

### 4.1 AI Work (`!ai work`)
- Routes natural language commands to NVIDIA NIM for productivity tasks
- Extends existing `CommandInterpreter` with a new "work" mode
- **No new file needed** — extend `ai_module/nim_client.py` with work-specific system prompt

### 4.2 AI Write (`!ai write`)
- Uses NVIDIA NIM to generate email/docs/notes
- Saves output to file and opens it
- **New file:** `agent/ai_productivity.py`

### 4.3 AI Automate (`!ai automate`)
- Natural language → cron/scheduled task
- Uses existing `!schedule` infrastructure
- **New file:** `agent/ai_productivity.py`

### 4.4 AI Summarize (`!ai summarize`)
- Recursive file reader + AI summarization
- Use NVIDIA NIM to summarize file/folder content
- **New file:** `agent/ai_productivity.py`

### 4.5 AI Research (`!ai research`)
- Web search + AI summarization
- Reuses `!web` search + NVIDIA NIM
- **New file:** `agent/ai_productivity.py`

### 4.6 Smart Clipboard (`!smart clipboard`)
- **NOT A NEW FEATURE** — `!clip sync` already exists
- Extend: Add clipboard type detection (text/image/file) with smart actions

### 4.7 Macro Recorder (`!macro`)

**New file:** `agent/macro_recorder.py`

Record/playback mouse + keyboard actions using `pynput`:
- `!macro record <name>` — Start recording (timeout 60s)
- `!macro stop` — Stop recording
- `!macro play <name>` — Replay recorded sequence
- `!macro list` — Show saved macros
- `!macro delete <name>` — Remove macro

```python
"""
Macro Recorder — record and replay mouse/keyboard sequences.
"""
import json
import time
import threading
from pathlib import Path
from loguru import logger

MACRO_DIR = Path.home() / ".config" / "rav-spy" / "macros"

class MacroRecorder:
    def __init__(self):
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        self.recording = False
        self.events = []
        self._thread = None

    def start_recording(self, name: str) -> str:
        if self.recording:
            return "Sudah merekam. Stop dulu."
        self.recording = True
        self.events = []
        # Start pynput listener in thread
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return f"Rekam macro '{name}' dimulai."

    def stop_recording(self, name: str) -> str:
        self.recording = False
        filepath = MACRO_DIR / f"{name}.json"
        with open(filepath, "w") as f:
            json.dump(self.events, f, indent=2)
        return f"Macro '{name}' tersimpan ({len(self.events)} events)."

    def play(self, name: str) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Macro '{name}' tidak ditemukan."
        with open(filepath) as f:
            events = json.load(f)
        # Replay in thread
        threading.Thread(target=self._replay, args=(events,), daemon=True).start()
        return f"Memutar macro '{name}' ({len(events)} events)..."

    def _listen(self):
        try:
            from pynput import mouse, keyboard
        except ImportError:
            logger.error("pynput not installed")
            self.recording = False
            return
        # Mouse listener
        def on_click(x, y, button, pressed):
            if self.recording:
                self.events.append({
                    "type": "click", "x": x, "y": y,
                    "button": str(button), "pressed": pressed,
                    "delay": time.time()
                })
        # Keyboard listener
        def on_press(key):
            if self.recording:
                self.events.append({
                    "type": "key", "key": str(key),
                    "pressed": True, "delay": time.time()
                })
        with mouse.Listener(on_click=on_click) as ml, keyboard.Listener(on_press=on_press) as kl:
            while self.recording:
                time.sleep(0.1)
            ml.stop()
            kl.stop()

    def _replay(self, events: list):
        import pyautogui
        last_time = None
        for ev in events:
            if last_time and ev.get("delay"):
                pyautogui.sleep(ev["delay"] - last_time)
            last_time = ev.get("delay", time.time())
            if ev["type"] == "click" and ev["pressed"]:
                pyautogui.click(ev["x"], ev["y"])
            elif ev["type"] == "key" and ev["pressed"]:
                pyautogui.press(ev["key"].replace("Key.", "").lower())
```

**Note:** Depends on `pynput` (add to requirements.txt).

### 4.8 Extended Schedule (`!schedule`)

**Extend existing** `!schedule` (already in `bot/telegram_bot.py:352-375`):
- Support cron-like syntax: `!schedule every weekday 08:00 !focus on`
- Store schedules persistently in JSON file
- Background scheduler loop

**New file:** `agent/scheduler.py` (persistent scheduler)

### 4.9 AI Insight (`!ai insight`)

**New file:** `agent/insight_engine.py`

- `!ai insight daily` — Summarizes today's activity log
- `!ai insight weekly` — Weekly patterns analysis
- `!ai insight monthly` — Monthly productivity report
- Uses existing audit log + NVIDIA NIM for analysis

### 4.10 Voice Command Toggle (`!voice cmd`)

**NOT A NEW FEATURE** — Voice handling via `filters.VOICE` in `telegram_bot.py` already exists.
Extend: Add toggle to enable/disable voice processing.

Add handler in `telegram_bot.py`:
```python
_voice_enabled: dict[str, bool] = {}
# !voice cmd on/off toggles per-user voice processing
```

---

## 5. PHASE 3: File, Sync & Data Management (PRIORITY: MEDIUM)

### 5.1 Sync (`!sync`)

**New file:** `agent/sync_manager.py`

- `!sync <folder> <service>` — Sync folder with Google Drive / OneDrive / local backup
- Uses `rclone` if installed, or `rsync` for local
- Configuration stored in `~/.config/rav-spy/sync.json`

### 5.2 Quick Upload (`!quick upload`)

**NOT A NEW FEATURE** — Already works via `Document.ALL` handler in `telegram_bot.py`.

### 5.3 Recent Files (`!recent files`)

**Extend** `!find` or add new handler listing recent files:
```python
async def handle_recent(self, args: list[str]) -> str:
    import os
    from pathlib import Path
    num = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    cmd = "find ~ -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -{}".format(num)
    proc = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.PIPE)
    stdout, _ = await proc.communicate()
    lines = stdout.decode().strip().split("\n")
    # Format output
    return "\n".join(f"  {Path(l.split(' ', 1)[1]).name} - {l.split(' ', 1)[1]}" for l in lines[:num])
```

### 5.4 File Content Search (`!search content`)

**Extend** `!find` — Add `grep -r` content search when `!search content` is used:
```python
# In handle_find: if args and args[0] == "content", use grep instead of rglob
```

### 5.5 Convert (`!convert`)

**New file:** `agent/file_converter.py`
- Uses `ffmpeg` for media, `libreoffice --headless` for documents, `pandoc` for markup
- `!convert <file> <to_format>` — Convert and send back

### 5.6 Backup (`!backup`)

**New file:** `agent/backup_manager.py`
- `!backup <folder> quick` — rsync to backup location
- `!backup <folder> full` — tar.gz archive with timestamp
- Config: `~/.config/rav-spy/backup.json`

### 5.7 Organize (`!organize`)

**New file:** `agent/file_organizer.py`
- `!organize <folder> by type` — Group by extension
- `!organize <folder> by date` — Group by YYYY-MM

### 5.8 File Watcher (`!file watcher`)

**New file:** `agent/file_watcher.py`
- Uses `inotify` (Linux) via `watchdog` Python library
- `!file watcher <folder> on` — Monitor for changes
- `!file watcher <folder> off` — Stop monitoring
- Alerts sent via heartbeat system

### 5.9 Version (`!version`)

**New file:** `agent/local_version.py`
- `!version status <file>` — Show version history
- `!version commit <file> "message"` — Save snapshot to `~/.config/rav-spy/versions/`
- `!version history <file>` — List versions
- `!version revert <file> <N>` — Restore version
- Simple copy-based versioning (no git dependency)

### 5.10 Clean (`!clean`)

**New file:** `agent/system_cleaner.py`
- `!clean temp` — Remove `/tmp` files older than 24h
- `!clean cache` — Clear `~/.cache/`, pip cache, apt cache
- `!clean duplicates` — Find duplicate files (by hash) in Downloads
- `!clean all` — Do all above + report freed space

---

## 6. PHASE 4: System Enhancement & Convenience (PRIORITY: MEDIUM)

### 6.1 Volume Control (`!volume`)

**NOT A NEW FEATURE** — Already exists as `!volume`, `!mute`, `!alarm`.
Extend with `!volume <app> <level>` for per-app volume using PulseAudio (`pactl`).
New method in `command_handler.py`:
```python
async def handle_volume_app(self, app: str, level: int) -> str:
    # pactl list-sink-inputs | grep -i <app>
    # pactl set-sink-input-volume <N> <level>%
```

### 6.2 Power Profile (`!power`)

**New file:** `agent/power_manager.py`
- `!power performance` — Set CPU governor to `performance`
- `!power balanced` — Set to `ondemand` / `schedutil`
- `!power saver` — Set to `powersave`, dim screen
- Requires `cpupower` or writing to `/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`

### 6.3 Multi Monitor (`!multi monitor`)

**New file:** `agent/multi_monitor.py`
- `!multi monitor list` — Show connected displays
- `!multi monitor switch` — Cycle primary display
- `!multi monitor arrange <grid|extend|mirror>` — Change layout
- Uses `xrandr` / `wlr-randr`

### 6.4 Sleep/Wake (`!sleep` / `!wake`)

**New file:** `agent/sleep_manager.py`
- `!sleep <delay>` — Sleep after delay (uses `systemctl suspend`)
- `!wake <time>` — Set RTC wake alarm (uses `rtcwake`)
- Requires `/sys/class/rtc/rtc0/wakealarm` or `rtcwake`

### 6.5 Quick App (`!quick app`)

**NOT A NEW FEATURE** — Use existing `!launch`.
Optionally add `!quick app` as alias for `!launch` in `fallback_parser.py`.

### 6.6 Battery Health (`!battery health`)

**NOT A NEW FEATURE** — `!battery` already shows health percentage.
Extend with historical tracking (store health data to JSON).

### 6.7 Night Mode (`!night mode`)

**New file:** `agent/night_mode.py`
- `!night mode on` — Enable `gnome-settings-daemon` night light / `redshift` / `gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled true`
- `!night mode off` — Disable
- Also toggle dark mode: `gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'`

### 6.8 Window Management Extended (`!window`)

**Extend** existing `!win` handler. Currently supports `minimize`/`close`.
Add:
- `!window arrange <cascade|tile|grid>` — Window tiling (requires `wmctrl` or `xdotool`)
- `!window snap <left|right>` — Snap to half screen
- `!window minimize all` — Minimize all windows (show desktop)
- `!window close all` — Close all windows of active app

### 6.9 Hotkey (`!hotkey`)

**New file:** `agent/hotkey_manager.py`
- `!hotkey create <name> "<key_combination>"` — Register global hotkey
- `!hotkey list` — Show registered hotkeys
- `!hotkey delete <name>` — Remove hotkey
- Uses `keyboard` library (add to requirements.txt) or `xdotool` for simulation only (listening is keyboard-dependent)

**Note:** Global hotkey listening may not work over SSH. This feature primarily lets users define hotkeys that the bot can simulate pressing.

### 6.10 Launch Advanced (`!launch advanced`)

**Extend** existing `!launch` to accept additional arguments:
```python
# Change handle_launch_app to accept extra args
async def handle_launch_app(self, app_name: str, extra_args: list = None) -> str:
    # existing logic + append extra_args
```

---

## 7. PHASE 5: Advanced & Power User Features (PRIORITY: LOW)

### 7.1 Time Tracker (`!time track`)

**New file:** `agent/time_tracker.py`

```python
"""
Time tracking — per-project time logging.
"""
import json
import time
from pathlib import Path
from datetime import datetime

TRACKER_FILE = Path.home() / ".config" / "rav-spy" / "time_tracker.json"

class TimeTracker:
    def __init__(self):
        self.data = self._load()
        self.active_session = None

    def _load(self) -> dict:
        if TRACKER_FILE.exists():
            try:
                with open(TRACKER_FILE) as f:
                    return json.load(f)
            except: pass
        return {"projects": {}, "sessions": []}

    def _save(self):
        TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def start(self, project: str) -> str:
        if self.active_session:
            return f"Session aktif: {self.active_session['project']}. Stop dulu."
        self.active_session = {"project": project, "start": time.time()}
        return f"Tracking dimulai untuk project '{project}'."

    def stop(self) -> str:
        if not self.active_session:
            return "Tidak ada session aktif."
        elapsed = time.time() - self.active_session["start"]
        project = self.active_session["project"]
        self.data["sessions"].append({
            "project": project,
            "start": datetime.fromtimestamp(self.active_session["start"]).isoformat(),
            "end": datetime.now().isoformat(),
            "duration_seconds": int(elapsed)
        })
        if project not in self.data["projects"]:
            self.data["projects"][project] = 0
        self.data["projects"][project] += int(elapsed)
        self._save()
        self.active_session = None
        return f"Project '{project}' selesai. Durasi: {int(elapsed // 60)}m {int(elapsed % 60)}s"

    def report(self, project: str = None) -> str:
        if project:
            seconds = self.data["projects"].get(project, 0)
            hours = seconds / 3600
            return f"Project '{project}': {hours:.1f} jam"
        lines = ["Time Tracking Report:"]
        for proj, secs in self.data["projects"].items():
            lines.append(f"  {proj}: {secs // 60}m")
        return "\n".join(lines) if len(lines) > 1 else "Belum ada data tracking."

time_tracker = TimeTracker()
```

### 7.2 Session Handoff (`!session handoff`)

**New file:** `agent/session_manager.py`
- Save current terminal sessions, clipboard, CWD to JSON
- `!session handoff` — Package state for transfer
- `!session receive <data>` — Restore on another instance
- Uses agent_registry for multi-device awareness

### 7.3 Share Screen (`!share screen`)

**New file:** `agent/screen_share.py`
- Uses ffmpeg to create a snapshot/video with temporary URL
- Uploads to a file sharing service (e.g., 0x0.st, file.io)
- Sends link back to user
- `!share screen 30m` — Share for 30 minutes

### 7.4 Multi Device (`!multi device`)

**Extend** agent_registry system:
- `!multi device list` — Show registered agents
- `!multi device switch <name>` — Already exists via `!select <agent_id>`
- `!multi device status` — Heartbeat status of all devices
- Reuses existing `agent_registry.py`, `!agents`, `!select` commands

### 7.5 Profile (`!profile`)

**New file:** `agent/profile_manager.py`
- `!profile create <name>` — Save current config (workspace, focus settings, power profile, night mode, etc.)
- `!profile load <name>` — Apply a saved profile
- `!profile list` — List profiles
- `!profile delete <name>` — Remove profile
- Orchestrates workspace_manager, power_manager, night_mode, focus_manager

### 7.6 Dashboard (`!dash`)

**New file:** `agent/dashboard.py`
- Aggregated view: battery, system info, weather (optional), top processes, next calendar event, active focus, time tracking today, recent notes
- Output as formatted text

### 7.7 Activity Log (`!activity log`)

**New file:** `agent/activity_log.py`
- `!activity log export <period>` — Export audit log to file
- `!activity log filter <type>` — Filter by event type
- `!activity log clear` — Clear log (with confirmation)
- Reuses existing audit log infrastructure

### 7.8 VPN (`!vpn`)

**New file:** `agent/vpn_manager.py`
- `!vpn connect <name>` — Connect via NetworkManager (`nmcli connection up <name>`)
- `!vpn disconnect` — Disconnect
- `!vpn status` — Show connection status
- `!vpn auto` — Set auto-connect

### 7.9 Tunnel (`!tunnel`)

**New file:** `agent/tunnel_manager.py`
- `!tunnel create <port>` — Create reverse tunnel via `ssh -R`
- `!tunnel list` — Show active tunnels
- `!tunnel close <port>` — Close tunnel
- Uses `subprocess` to manage `ssh` processes

### 7.10 AI Agent (`!ai agent`)

**New file:** `agent/ai_autonomous.py`
- `!ai agent on "instruksi"` — Start autonomous AI agent
- Runs continuous loop: monitor folder → summarize → report
- Uses NVIDIA NIM for reasoning
- Reports findings via heartbeat alerts
- `!ai agent off` — Stop agent
- `!ai agent status` — Show agent state

---

## 8. DEPENDENCY MAP (requirements.txt additions)

```txt
# PHASE 1: Productivity Foundation
google-api-python-client>=2.0.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0

# PHASE 2: AI & Automation
pynput>=1.7.6          # Macro recording

# PHASE 3: File Management
watchdog>=4.0.0        # File watcher (inotify)

# PHASE 4: System Controls
# (mostly uses existing binaries: xrandr, rtcwake, cpupower, nmcli)

# PHASE 5: Power User
# (mostly uses existing: ssh, nmcli, ffmpeg)
```

---

## 9. IMPLEMENTATION ORDER & DEPENDENCIES

```
Phase 1 ─────────────────────────────────────────────
  ├── !quicknote ─────── (no deps, simple file write)
  ├── !custom alias ──── (no deps, JSON file storage)
  ├── !reminder ──────── (no deps, async loop)
  ├── !focus ─────────── (system utilities only)
  ├── !workspace ─────── (wmctrl/xdotool)
  ├── !daily report ──── (no deps, psutil + JSON)
  ├── !meeting mode ──── (combines !focus + !launch)
  ├── !browser ───────── (xdotool + chrome remote debug)
  ├── !task sync ─────── (extends !todo)
  ├── !calendar ──────── (google API, OAuth)
  └── !schedule extend ─ (persistent scheduler)

Phase 2 ─────────────────────────────────────────────
  ├── !voice cmd extend ─ (toggle in telegram_bot.py)
  ├── !smart clipboard ── (extend !clip)
  ├── !ai work/write ──── (NVIDIA NIM integration)
  ├── !ai summarize ───── (NVIDIA NIM + file reader)
  ├── !ai research ────── (NVIDIA NIM + web search)
  ├── !ai automate ────── (NVIDIA NIM + schedule)
  ├── !ai insight ─────── (audit log + NVIDIA NIM)
  ├── !macro ──────────── (pynput dependency)
  └── !schedule extend ── (cron-like persistence)

Phase 3 ─────────────────────────────────────────────
  ├── !recent ─────────── (extend !find)
  ├── !search content ─── (extend !find)
  ├── !clean ──────────── (system utilities)
  ├── !organize ───────── (shutil + pathlib)
  ├── !version ────────── (file copy + JSON)
  ├── !convert ────────── (ffmpeg/libreoffice)
  ├── !backup ─────────── (rsync/tar)
  ├── !sync ───────────── (rclone wrapper)
  └── !file watcher ───── (watchdog library)

Phase 4 ─────────────────────────────────────────────
  ├── !volume extend ──── (pactl per-app)
  ├── !quick app ──────── (alias !launch)
  ├── !battery extend ─── (historical tracking)
  ├── !window extend ──── (arrange/tile)
  ├── !power ──────────── (cpupower)
  ├── !multi monitor ──── (xrandr)
  ├── !night mode ─────── (gsettings)
  ├── !sleep/wake ─────── (rtcwake)
  ├── !launch extend ──── (extra args)
  └── !hotkey ─────────── (keyboard library)

Phase 5 ─────────────────────────────────────────────
  ├── !time track ─────── (JSON + time)
  ├── !activity log ───── (audit log filter)
  ├── !multi device ───── (extend agent_registry)
  ├── !dash ───────────── (aggregator, no deps)
  ├── !profile ────────── (orchestrator)
  ├── !session handoff ── (JSON export/import)
  ├── !share screen ───── (ffmpeg + file upload)
  ├── !vpn ────────────── (nmcli)
  ├── !tunnel ─────────── (ssh subprocess)
  └── !ai agent ───────── (NVIDIA NIM + loop)
```

---

## 10. TESTING STRATEGY

### Unit Tests (`tests/test_<feature>.py`)
- Each new feature module gets its own test file
- Mock external dependencies (subprocess, API calls, file I/O)
- Test: happy path, error cases, edge cases (empty args, invalid input)

```python
# Example: tests/test_focus.py
class TestFocus(unittest.TestCase):
    def setUp(self):
        from agent.focus import FocusManager
        self.focus = FocusManager()

    def test_start_stop(self):
        result = self.focus.start(25)
        self.assertIn("AKTIF", result)
        self.assertTrue(self.focus.active)
        result = self.focus.stop()
        self.assertIn("NONAKTIF", result)
        self.assertFalse(self.focus.active)

    def test_get_remaining_when_inactive(self):
        result = self.focus.get_remaining()
        self.assertIn("tidak aktif", result)
```

### E2E Tests (`tests/test_e2e.py`)
- Add test cases for critical Phase 1 features (focus, workspace, custom alias)
- Test the full flow: Update creation → router → handler → response

### Regression Testing
- Before each phase release: `python -m unittest discover tests`
- Ensure test_commands.py, test_e2e.py, test_security.py, test_auth.py all pass

---

## 11. VERIFICATION CHECKLIST (per feature)

Before marking any feature as complete:

- [ ] `agent/<feature_module>.py` created with documented class/functions
- [ ] `agent/command_handler.py` has `async def handle_<feature>` method
- [ ] `bot/command_router.py` has `elif command_name == "<feature>"` branch
- [ ] `ai_module/fallback_parser.py` has `"!<cmd>": "<feature>"` entry
- [ ] `config/allowed_commands.yaml` has `<feature>:` entry
- [ ] `ai_module/prompt_templates.py` has the command in SYSTEM_PROMPT
- [ ] Handler uses `asyncio.to_thread()` for blocking operations
- [ ] Handler calls `logger` for key events
- [ ] `auditor.log_event()` called in router branch
- [ ] Tests exist in `tests/test_<feature>.py`
- [ ] All existing tests still pass
- [ ] Error handling covers: invalid args, system errors, timeouts

---

## 12. RISK & MITIGATION

| Risk | Mitigation |
|---|---|
| Google Calendar API OAuth complexity | Use offline token storage; prompt user to auth once via setup flow |
| Browser control version-dependent | Use xdotool as fallback for all Chromium-based browsers |
| Macro recording security risk (keylog) | Clearly communicate to user; store recordings locally only |
| File watcher CPU usage on large dirs | Limit to specific directory depth; max 1000 files |
| VPN/tunnel requires sudo | Document required sudoers config; use `polkit` when possible |
| AI autonomous loop consumes API credits | Hard limit on iterations; user confirmation for >5 cycles |
| rtcwake requires root | Document sudoers setup for specific commands |
