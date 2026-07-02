import json
import os
import subprocess
import shutil
import re
import time
from pathlib import Path
from datetime import datetime
from loguru import logger

from agent.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS, has_tool, run_cmd

WORKSPACE_DIR = Path.home() / ".config" / "rav-spy" / "workspaces"

KNOWN_GUI_APPS = {
    "nautilus", "org.gnome.Nautilus",
    "gnome-terminal", "kgx", "ptyxis", "gnome-console",
    "firefox", "firefox-esr", "thorium", "chromium", "chromium-browser",
    "google-chrome", "google-chrome-stable", "brave", "opera", "microsoft-edge",
    "code", "code-insiders", "codium", "sublime_text", "atom", "zed",
    "gedit", "gnome-text-editor", "org.gnome.TextEditor",
    "gimp", "inkscape", "blender", "krita",
    "vlc", "mpv", "rhythmbox", "spotify",
    "thunderbird", "evolution", "geary", "mail",
    "slack", "discord", "telegram-desktop", "signal-desktop", "whatsapp",
    "libreoffice", "soffice.bin",
    "evince", "org.gnome.Evince",
    "eog", "org.gnome.Loupe",
    "gnome-calculator", "gnome-calendar", "gnome-characters",
    "gnome-software", "snap-store",
    "qbittorrent", "transmission-gtk", "deluge",
    "obs", "obs-studio",
    "remmina", "org.remmina.Remmina",
    "steam", "steam-native", "lutris",
    "alacritty", "kitty", "wezterm", "terminator", "tilix", "ghostty",
    "org.wezfurlong.wezterm",
    "gnome-system-monitor", "org.gnome.SystemMonitor",
    "baobab", "org.gnome.baobab",
    "pavucontrol",
    "nm-connection-editor",
    "gparted",
    "org.gnome.Extensions",
    "dconf-editor",
    "calculator", "terminal", "finder", "safari", "notes", "calendar",
}

SYSTEM_SERVICE_PREFIXES = (
    "gsd-", "goa-", "evolution-", "ibus", "gjs", "gnome-session",
    "gnome-settings-", "gnome-shell", "mutter-", "Xwayland",
    "update-notifier", "snapd", "packagekit", "fwupd", "rtkit",
    "kernel", "kworker", "systemd", "dbus", "accounts-daemon",
    "avahi", "colord", "cups", "gdm", "haveged", "lightdm",
    "polkit", "pulseaudio", "systemd-", "udisks", "upower",
    "wpa_supplicant", "NetworkManager",
)

# Binary names of subprocesses/helpers that should be deduped
SUB_PROCESS_NAMES = {
    "chrome_crashpad", "crashpad_handler", "language_server", "language_server_linux_x64",
    "speech-dispatcher", "speech-dispatch", "snap", "user-session-helper",
    "gnome-software", "gnome-software-service",
    "gmain", "gdbus", "dconf-service", "at-spi-bus-launcher",
    "at-spi2-registryd", "xdg-permission-store", "xdg-dbus-proxy",
    "mission-control", "obexd", "goa-identity-service",
    "tracker-miner-fs", "tracker-extract", "tracker-store",
    "whoopsie", "apport-gtk", "zeitgeist-daemon",
    "MainThread",
}

# Process name → clean app name mapping for display/dedup
APP_ALIASES = {
    "brave": "brave-browser",
    "brave-browser": "brave-browser",
    "firefox": "firefox",
    "google-chrome": "google-chrome",
    "chromium": "chromium",
    "chromium-browser": "chromium",
    "code": "code",
    "code-insiders": "code-insiders",
    "ptyxis": "ptyxis",
    "gnome-terminal-server": "gnome-terminal",
    "nautilus": "nautilus",
    "antigravity": "antigravity",
}


def _get_user_uid() -> int | None:
    if not IS_LINUX:
        return None
    try:
        return os.getuid()
    except Exception:
        return None


class WorkspaceManager:
    def __init__(self):
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    def _capture_windows(self) -> list:
        if IS_LINUX:
            return self._capture_linux()
        if IS_MACOS:
            return self._capture_macos()
        if IS_WINDOWS:
            return self._capture_windows_os()
        return []

    def _capture_linux(self) -> list:
        x11 = self._capture_x11()
        if x11:
            return x11
        return self._detect_gui_processes()

    def _capture_x11(self) -> list:
        windows = []
        if not has_tool("wmctrl"):
            return windows
        try:
            res = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5)
            for line in res.stdout.strip().split("\n"):
                if line:
                    windows.append(line)
        except Exception:
            pass
        return windows

    def _detect_gui_processes(self) -> list:
        if not IS_LINUX:
            return []
        my_uid = _get_user_uid()
        candidates = {}

        for pid_str in os.listdir("/proc"):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            if pid < 1000:
                continue

            try:
                with open(f"/proc/{pid}/comm") as f:
                    comm = f.read().strip()
            except (OSError, IOError):
                continue

            if not comm or comm.startswith(SYSTEM_SERVICE_PREFIXES):
                continue
            if comm in SUB_PROCESS_NAMES:
                continue

            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    raw = f.read().replace(b"\x00", b" ").decode("latin-1").strip()
            except (OSError, IOError):
                continue

            if not raw:
                continue

            try:
                with open(f"/proc/{pid}/environ", "rb") as f:
                    env = f.read().decode("latin-1")
            except (OSError, IOError):
                continue

            has_display = "DISPLAY=" in env or "WAYLAND_DISPLAY=" in env
            if not has_display:
                continue

            if my_uid:
                try:
                    uid = os.stat(f"/proc/{pid}").st_uid
                    if uid != my_uid:
                        continue
                except (OSError, IOError):
                    continue

            if comm in ("sh", "bash", "zsh", "fish", "dash"):
                continue

            if "rav-spy" in raw.lower() or "venv/bin/python" in raw.lower():
                continue
            if "run.js" in raw.lower() and "/rav-spy" in raw.lower():
                continue

            if raw.startswith("/usr/libexec/"):
                continue
            if raw.startswith("/snap/") and ("/usr/" in raw or "/bin/" in raw):
                continue
            if "--gapplication-service" in raw and comm not in ("ptyxis",):
                continue

            app_name = APP_ALIASES.get(comm, comm)
            if comm in KNOWN_GUI_APPS or app_name in KNOWN_GUI_APPS:
                candidates[app_name] = {"type": "process", "comm": app_name, "cmdline": raw}
                continue

            raw_lower = raw.lower()
            allowed_paths = ("/usr/bin/", "/snap/", "/app/", "/applications",
                            "/usr/share/", "/opt/", "/home/")
            contains_known_path = any(p in raw_lower for p in allowed_paths)
            if not contains_known_path and not comm.endswith("-browser"):
                continue

            candidates[app_name] = {"type": "process", "comm": app_name, "cmdline": raw}

        return list(candidates.values())

    def _capture_macos(self) -> list:
        apps = []
        try:
            res = subprocess.run(
                "osascript -e 'tell application \"System Events\" to get name of every process whose background only is false'",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                for name in res.stdout.strip().split(", "):
                    name = name.strip()
                    if name and name not in ("System Events", "Finder", "Dock"):
                        apps.append({"type": "process", "comm": name, "cmdline": name})
        except Exception:
            pass
        return apps

    def _capture_windows_os(self) -> list:
        import psutil
        apps = []
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                pinfo = proc.info
                if pinfo["create_time"] and pinfo["create_time"] > time.time() - 7200:
                    apps.append({"type": "process", "comm": pinfo["name"], "cmdline": pinfo["name"]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return apps[:20]

    def _restore_windows(self, windows: list):
        if not windows:
            return
        for entry in windows:
            if isinstance(entry, dict) and entry.get("type") == "process":
                cmd = entry.get("cmdline", entry.get("comm", ""))
                if cmd:
                    try:
                        if IS_LINUX:
                            subprocess.Popen(cmd, shell=True,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        elif IS_MACOS:
                            subprocess.Popen(["open", "-a", cmd],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        elif IS_WINDOWS:
                            subprocess.Popen(["cmd", "/c", "start", "", cmd],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass
            elif isinstance(entry, str):
                parts = entry.split(None, 3)
                if len(parts) >= 4:
                    cmd = parts[3] if parts[3].startswith("/") else parts[3].lower()
                    try:
                        subprocess.Popen(cmd, shell=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass

    def save(self, name: str) -> str:
        windows = self._capture_windows()
        state = {
            "timestamp": datetime.now().isoformat(),
            "windows": windows,
            "cwd": os.getcwd(),
            "os": IS_LINUX and "linux" or IS_MACOS and "macos" or "windows",
        }
        filepath = WORKSPACE_DIR / f"{name}.json"
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
        count = len(windows)
        names = [w["comm"] if isinstance(w, dict) else w.split(None, 3)[-1].split("/")[-1] if len(w.split(None, 3)) >= 4 else w.split()[0] for w in windows]
        apps_str = ", ".join(names[:10])
        if count > 10:
            apps_str += f" +{count - 10} lainnya"
        return f"Workspace '{name}' tersimpan ({count} app): {apps_str}"

    def load(self, name: str) -> str:
        filepath = WORKSPACE_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Workspace '{name}' tidak ditemukan."
        try:
            with open(filepath) as f:
                state = json.load(f)
            windows = state.get("windows", [])
            self._restore_windows(windows)
            return f"Workspace '{name}' dimuat ({len(windows)} app dipulihkan)."
        except Exception as e:
            return f"Gagal memuat workspace '{name}': {e}"

    def list_workspaces(self) -> str:
        files = sorted(WORKSPACE_DIR.glob("*.json"))
        if not files:
            return "Belum ada workspace tersimpan."
        lines = ["Daftar Workspace:"]
        for f in files:
            try:
                with open(f) as fh:
                    data = json.load(fh)
                ts = data.get("timestamp", "unknown")[:16]
                st = data.get("os", "?")
                n = len(data.get("windows", []))
                lines.append(f"  {f.stem} ({ts}, {st}, {n} app)")
            except Exception:
                lines.append(f"  {f.stem}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        filepath = WORKSPACE_DIR / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return f"Workspace '{name}' dihapus."
        return f"Workspace '{name}' tidak ditemukan."


workspace_manager = WorkspaceManager()
