"""
Macro Recorder — record, save, and replay keyboard/mouse actions.
"""
import json
import time
import subprocess
import shutil
import webbrowser
import pyperclip
from pathlib import Path
from datetime import datetime
from loguru import logger
from agent.input_simulator import simulate_click, simulate_type, simulate_press

MACRO_DIR = Path.home() / ".config" / "rav-spy" / "macros"

class MacroManager:
    def __init__(self):
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        self.recording = False
        self.current_macro = []
        self.start_time = None
        self.onerror = "continue"

    def record(self, name: str) -> str:
        if self.recording:
            return "Sudah merekam. Stop dulu sebelum record baru."
        self.recording = True
        self.current_macro = []
        self.start_time = time.time()
        return f"🎬 Merekam macro '{name}'... Kirim !macro stop saat selesai."

    def stop(self) -> str:
        if not self.recording:
            return "Tidak ada rekaman aktif."
        self.recording = False
        return f"⏹️ Rekaman dihentikan ({len(self.current_macro)} aksi terekam)."

    def add_action(self, action: dict):
        if self.recording:
            ts = time.time() - (self.start_time or time.time())
            action["timestamp"] = round(ts, 2)
            self.current_macro.append(action)

    def add_actions(self, actions: list[dict]):
        for a in actions:
            self.add_action(a)

    def save(self, name: str) -> str:
        if not self.current_macro:
            return "Tidak ada aksi untuk disimpan."
        filepath = MACRO_DIR / f"{name}.json"
        data = {
            "name": name,
            "created": datetime.now().isoformat(),
            "actions": self.current_macro
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return f"💾 Macro '{name}' tersimpan ({len(self.current_macro)} aksi)."

    def show(self, name: str) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Macro '{name}' tidak ditemukan."
        try:
            with open(filepath) as f:
                data = json.load(f)
            actions = data.get("actions", [])
            if not actions:
                return f"Macro '{name}' kosong."
            lines = [f"📋 Macro: {name} ({len(actions)} aksi)"]
            for i, a in enumerate(actions, 1):
                act = a.get("action", "?")
                ts = a.get("timestamp", 0)
                desc = _describe_action(a)
                lines.append(f"  {i}. [{ts:.1f}s] {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Gagal membaca macro '{name}': {e}"

    def remove_action(self, name: str, index: int) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Macro '{name}' tidak ditemukan."
        try:
            with open(filepath) as f:
                data = json.load(f)
            actions = data.get("actions", [])
            if index < 1 or index > len(actions):
                return f"Indeks {index} tidak valid. Total {len(actions)} aksi."
            removed = actions.pop(index - 1)
            data["actions"] = actions
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return f"Hapus aksi #{index} ({removed.get('action', '?')}) dari macro '{name}'."
        except Exception as e:
            return f"Gagal: {e}"

    def insert_action(self, name: str, index: int, action: dict) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Macro '{name}' tidak ditemukan."
        try:
            with open(filepath) as f:
                data = json.load(f)
            actions = data.get("actions", [])
            if index < 1 or index > len(actions) + 1:
                return f"Indeks {index} tidak valid."
            actions.insert(index - 1, action)
            data["actions"] = actions
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return f"Sisipkan aksi di posisi #{index} macro '{name}'."
        except Exception as e:
            return f"Gagal: {e}"

    def config(self, key: str, value: str) -> str:
        if key == "onerror" and value in ("abort", "continue", "retry"):
            self.onerror = value
            return f"⚙️ onerror = {value}"
        return "Gunakan: !macro config onerror [abort|continue|retry]"

    def _resolve_vars(self, text: str) -> str:
        now = datetime.now()
        text = text.replace("{{date}}", now.strftime("%Y-%m-%d"))
        text = text.replace("{{time}}", now.strftime("%H:%M"))
        text = text.replace("{{datetime}}", now.strftime("%Y-%m-%d %H:%M:%S"))
        if "{{clipboard}}" in text:
            try:
                clip = pyperclip.paste()
                text = text.replace("{{clipboard}}", clip)
            except Exception:
                pass
        return text

    def _execute_action(self, action: dict) -> str:
        act = action.get("action", "")
        logger.info(f"Macro executing: {act} -> {action}")
        try:
            if act == "click":
                simulate_click(action.get("x", 0), action.get("y", 0))

            elif act == "rightclick":
                x, y = action.get("x", 0), action.get("y", 0)
                if shutil.which("xdotool"):
                    subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "3"],
                                   capture_output=True, timeout=3)
                else:
                    from agent.input_simulator import _ensure_pyautogui
                    if _ensure_pyautogui():
                        import pyautogui
                        pyautogui.click(x, y, button="right")

            elif act == "doubleclick":
                x, y = action.get("x", 0), action.get("y", 0)
                from agent.input_simulator import _ensure_pyautogui
                if _ensure_pyautogui():
                    import pyautogui
                    pyautogui.doubleClick(x, y)
                elif shutil.which("xdotool"):
                    subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "1"],
                                   capture_output=True, timeout=3)

            elif act == "drag":
                x1, y1 = action.get("x1", 0), action.get("y1", 0)
                x2, y2 = action.get("x2", 0), action.get("y2", 0)
                from agent.input_simulator import _ensure_pyautogui
                if _ensure_pyautogui():
                    import pyautogui
                    pyautogui.moveTo(x1, y1)
                    pyautogui.drag(x2 - x1, y2 - y1, duration=0.3)

            elif act == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 3)
                from agent.input_simulator import _ensure_pyautogui
                if _ensure_pyautogui():
                    import pyautogui
                    pyautogui.scroll(-amount if direction == "down" else amount)

            elif act == "type":
                text = self._resolve_vars(action.get("text", ""))
                simulate_type(text)

            elif act == "key":
                key = action.get("key", "")
                if key.startswith("media_"):
                    media_key = key.replace("media_", "")
                    media_map = {"play": "playpause", "pause": "playpause",
                                 "next": "nexttrack", "prev": "prevtrack"}
                    simulate_press(media_map.get(media_key, media_key))
                elif key.startswith("window_"):
                    wa = key.replace("window_", "")
                    if wa == "minimize":
                        simulate_press("ctrl+alt+d")
                    elif wa == "close":
                        simulate_press("alt+f4")
                elif key.startswith("page"):
                    xdo_key = "Page_Down" if "down" in key else "Page_Up"
                    simulate_press(xdo_key)
                elif key.startswith("browser_close"):
                    from agent.browser_controller import browser_close
                    browser_close()
                else:
                    simulate_press(key)

            elif act == "open_url":
                url = action.get("url", "")
                if not url.startswith("http"):
                    url = "https://" + url
                webbrowser.open(url)

            elif act == "click_image":
                from agent.vision import click_image as ci
                result = ci(action.get("template", ""), action.get("confidence", 0.8))
                if result is None:
                    return "not_found"

            elif act == "wait_image":
                from agent.vision import wait_for_image
                result = wait_for_image(
                    action.get("template", ""),
                    action.get("timeout", 10),
                    action.get("confidence", 0.8)
                )
                if result is None:
                    return "timeout"

            elif act == "run":
                cmd = action.get("command", "")
                subprocess.run(cmd, shell=True, capture_output=True, timeout=30)

            elif act == "clipboard_copy":
                import pyperclip
                text = action.get("text", "")
                pyperclip.copy(text)

            elif act == "clipboard_paste":
                import pyperclip
                text = pyperclip.paste()
                simulate_type(text)

            elif act == "sleep":
                time.sleep(action.get("duration", 0.5))

            elif act == "loop":
                count = action.get("count", 1)
                sub_actions = action.get("actions", [])
                for _ in range(count):
                    for sa in sub_actions:
                        result = self._execute_action(sa)
                        if result in ("not_found", "timeout") and self.onerror == "abort":
                            return result
                        time.sleep(action.get("delay", 0.3))

            return "ok"
        except Exception as e:
            logger.error(f"Macro action failed: {act} - {e}")
            if self.onerror == "abort":
                return "error"
            return "ok"

    def play(self, name: str) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return f"Macro '{name}' tidak ditemukan."
        try:
            with open(filepath) as f:
                data = json.load(f)
            actions = data.get("actions", [])
            if not actions:
                return f"Macro '{name}' kosong."
            total = len(actions)
            for i, action in enumerate(actions, 1):
                result = self._execute_action(action)
                if result == "not_found":
                    return f"⏹️ Macro '{name}' berhenti di aksi #{i}: gambar tidak ditemukan."
                if result == "timeout":
                    return f"⏹️ Macro '{name}' berhenti di aksi #{i}: timeout menunggu gambar."
                if result == "error":
                    return f"⏹️ Macro '{name}' berhenti di aksi #{i}: error."
                delay = action.get("delay", 0.3)
                if action.get("action") == "open_url":
                    delay = max(delay, 3)
                elif action.get("action") == "click_image":
                    delay = max(delay, 1)
                elif action.get("action") == "wait_image":
                    delay = 0.5
                time.sleep(delay)
            return f"▶️ Macro '{name}' selesai ({total} aksi)."
        except Exception as e:
            return f"Gagal memutar macro '{name}': {e}"

    def list_macros(self) -> str:
        files = sorted(MACRO_DIR.glob("*.json"))
        if not files:
            return "Belum ada macro tersimpan."
        lines = ["Daftar Macro:"]
        for f in files:
            try:
                with open(f) as fh:
                    data = json.load(fh)
                count = len(data.get("actions", []))
                created = data.get("created", "")[:16] if data.get("created") else ""
                lines.append(f"  {f.stem} ({count} aksi, {created})")
            except Exception:
                lines.append(f"  {f.stem}")
        return "\n".join(lines)

    def delete(self, name: str) -> str:
        filepath = MACRO_DIR / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return f"Macro '{name}' dihapus."
        return f"Macro '{name}' tidak ditemukan."


def _describe_action(action: dict) -> str:
    act = action.get("action", "?")
    if act == "click":
        return f"🖱️ Klik di ({action.get('x', 0)}, {action.get('y', 0)})"
    elif act == "rightclick":
        return f"🖱️ Klik kanan di ({action.get('x', 0)}, {action.get('y', 0)})"
    elif act == "doubleclick":
        return f"🖱️ Dobel klik di ({action.get('x', 0)}, {action.get('y', 0)})"
    elif act == "drag":
        return f"🖱️ Drag ({action.get('x1', 0)},{action.get('y1', 0)}) → ({action.get('x2', 0)},{action.get('y2', 0)})"
    elif act == "scroll":
        return f"🖱️ Scroll {action.get('direction', 'down')} x{action.get('amount', 3)}"
    elif act == "type":
        return f"⌨️ Ketik: \"{action.get('text', '')}\""
    elif act == "key":
        return f"⌨️ Tekan: {action.get('key', '')}"
    elif act == "open_url":
        return f"🌐 Buka: {action.get('url', '')}"
    elif act == "click_image":
        return f"🔍 Cari + klik: {Path(action.get('template', '')).name} (confidence {action.get('confidence', 0.8)})"
    elif act == "wait_image":
        return f"⏳ Tunggu gambar: {Path(action.get('template', '')).name} (timeout {action.get('timeout', 10)}s)"
    elif act == "run":
        return f"⚡ Run: {action.get('command', '')}"
    elif act == "clipboard_copy":
        return f"📋 Copy: \"{action.get('text', '')}\""
    elif act == "clipboard_paste":
        return f"📋 Paste"
    elif act == "sleep":
        return f"⏳ Tidur {action.get('duration', 0.5)}s"
    elif act == "loop":
        return f"🔁 Ulang {action.get('count', 1)}x ({len(action.get('actions', []))} aksi)"
    return str(action)


macro_manager = MacroManager()
