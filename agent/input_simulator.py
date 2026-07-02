import subprocess
import shutil
import os
from loguru import logger

from agent.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS, has_tool, has_python_module

pyautogui = None

_PYAUTOGUI_BLACKLIST = IS_LINUX and not os.environ.get("DISPLAY")

def _ensure_pyautogui():
    global pyautogui
    if _PYAUTOGUI_BLACKLIST:
        return False
    if pyautogui is None:
        try:
            import pyautogui as pg
            pyautogui = pg
            return True
        except Exception:
            return False
    return True


def simulate_click(x: int, y: int) -> str:
    if _ensure_pyautogui():
        try:
            pyautogui.click(x, y)
            return f"Berhasil klik mouse pada ({x}, {y})."
        except Exception as e:
            logger.warning(f"PyAutoGUI click failed: {e}")

    if IS_LINUX:
        if has_tool("xdotool"):
            try:
                r = subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"],
                                   capture_output=True, timeout=5)
                if r.returncode == 0:
                    return f"Berhasil klik mouse pada ({x}, {y})."
            except Exception:
                pass
        if has_tool("ydotool"):
            try:
                subprocess.run(["ydotool", "mousemove", "-a", str(x), str(y)], capture_output=True, timeout=5)
                subprocess.run(["ydotool", "click", "0x110"], capture_output=True, timeout=5)
                return f"Berhasil klik mouse pada ({x}, {y})."
            except Exception:
                pass
        return "Gagal klik. Install pyautogui atau xdotool."

    if IS_MACOS:
        try:
            cmd = f"osascript -e 'tell application \"System Events\" to click at {{{x}, {y}}}'"
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
            return f"Berhasil klik mouse pada ({x}, {y})."
        except Exception:
            return "Gagal klik. Install pyautogui."

    if IS_WINDOWS:
        return "Gagal klik. Install pyautogui."

    return f"Klik belum didukung di OS ini." if not pyautogui else f"Klik gagal."


def simulate_type(text: str) -> str:
    if _ensure_pyautogui():
        try:
            pyautogui.write(text, interval=0.01)
            return f"Berhasil mengetik teks."
        except Exception as e:
            logger.warning(f"PyAutoGUI type failed: {e}")

    if IS_LINUX:
        if has_tool("xdotool"):
            try:
                subprocess.run(["xdotool", "type", text], capture_output=True, timeout=5)
                return f"Berhasil mengetik teks."
            except Exception:
                pass
        if has_tool("ydotool"):
            try:
                subprocess.run(["ydotool", "type", text], capture_output=True, timeout=5)
                return f"Berhasil mengetik teks."
            except Exception:
                pass
        return "Gagal ngetik. Install pyautogui atau xdotool."

    if IS_MACOS:
        try:
            escaped = text.replace('"', '\\"')
            subprocess.run(
                f'osascript -e \'tell application "System Events" to keystroke "{escaped}"\'',
                shell=True, capture_output=True, timeout=5
            )
            return f"Berhasil mengetik teks."
        except Exception:
            return "Gagal ngetik. Install pyautogui."

    if IS_WINDOWS:
        return "Gagal ngetik. Install pyautogui."

    return f"Mengetik belum didukung."


KEYS_YDOOTOOL = {
    "esc": 1, "escape": 1,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "minus": 12, "equal": 13, "backspace": 14, "tab": 15,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
    "leftbrace": 26, "rightbrace": 27, "enter": 28, "return": 28,
    "leftctrl": 29, "ctrl": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38,
    "semicolon": 39, "apostrophe": 40, "grave": 41,
    "leftshift": 42, "shift": 42,
    "backslash": 43,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "comma": 51, "dot": 52, "slash": 53,
    "rightshift": 54,
    "kp_multiply": 55,
    "leftalt": 56, "alt": 56,
    "space": 57,
    "capslock": 58,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 69, "f12": 70,
    "numlock": 69,
    "scrolllock": 70,
    "home": 74, "up": 75, "pageup": 76,
    "left": 77, "right": 78,
    "end": 79, "down": 80, "pagedown": 81, "page_down": 81,
    "insert": 82, "delete": 83,
    "leftmeta": 125, "super": 125, "win": 125,
    "rightmeta": 126,
}

def _ydotool_key(key_name: str):
    code = KEYS_YDOOTOOL.get(key_name.lower())
    if code:
        return [str(code), "1", str(code), "0"]
    return None

def _ydotool_combo(keys: list[str]):
    cmds = []
    for k in keys:
        code = KEYS_YDOOTOOL.get(k.lower())
        if code:
            cmds.append(f"{code}:1")
    for k in reversed(keys):
        code = KEYS_YDOOTOOL.get(k.lower())
        if code:
            cmds.append(f"{code}:0")
    return cmds if cmds else None

KEY_MAP_MAC = {
    "enter": "36", "return": "36",
    "space": "49",
    "escape": "53", "esc": "53",
    "tab": "48",
    "backspace": "51",
    "delete": "117",
    "up": "126", "down": "125", "left": "123", "right": "124",
    "home": "115", "end": "119",
    "pageup": "116", "pagedown": "121",
    "f1": "122", "f2": "120", "f3": "99", "f4": "118",
    "f5": "96", "f6": "97", "f7": "98", "f8": "100",
    "command": "55", "cmd": "55",
    "shift": "56", "control": "59", "ctrl": "59",
    "option": "58", "alt": "58",
}


def simulate_press(key: str) -> str:
    keys = [k.strip() for k in key.split("+")] if "+" in key else [key]
    is_combo = len(keys) > 1

    if _ensure_pyautogui():
        try:
            if is_combo:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)
            return f"Berhasil tekan tombol '{key}'."
        except Exception as e:
            logger.warning(f"PyAutoGUI press failed: {e}")

    if IS_LINUX:
        if has_tool("xdotool"):
            try:
                sep = "+" if is_combo else ""
                xdo_key = "+".join(keys) if is_combo else key
                subprocess.run(["xdotool", "key", xdo_key], capture_output=True, timeout=5)
                return f"Berhasil tekan tombol '{key}'."
            except Exception:
                pass
        if has_tool("ydotool"):
            try:
                combo_cmds = _ydotool_combo(keys)
                if combo_cmds:
                    subprocess.run(["ydotool", "key"] + combo_cmds, capture_output=True, timeout=5)
                    return f"Berhasil tekan tombol '{key}' via ydotool."
            except Exception:
                pass
        if has_tool("wtype"):
            try:
                wtype_args = []
                for k in keys:
                    wtype_args.extend(["-k", k])
                subprocess.run(["wtype"] + wtype_args, capture_output=True, timeout=5)
                return f"Berhasil tekan tombol '{key}' via wtype."
            except Exception:
                pass
        return f"Gagal tekan '{key}'. Install pyautogui atau xdotool."

    if IS_MACOS:
        try:
            key_lower = key.lower()
            if key_lower in KEY_MAP_MAC:
                code = KEY_MAP_MAC[key_lower]
                subprocess.run(
                    f'osascript -e \'tell application "System Events" to key code {code}\'',
                    shell=True, capture_output=True, timeout=5
                )
            else:
                subprocess.run(
                    f'osascript -e \'tell application "System Events" to keystroke "{key}"\'',
                    shell=True, capture_output=True, timeout=5
                )
            return f"Berhasil tekan tombol '{key}'."
        except Exception:
            return f"Gagal tekan '{key}'. Install pyautogui."

    if IS_WINDOWS:
        return f"Gagal tekan '{key}'. Install pyautogui."

    return f"Tekan tombol belum didukung."
