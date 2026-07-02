"""
RAV-SPY Agent — FastAPI server yang menerima perintah dari bot
Jalankan di laptop target
"""
import os
import base64
import asyncio
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from loguru import logger
from bot.command_router import CommandRouter
from security.audit_logger import AuditLogger
from security.sanitizer import InputSanitizer
from bot.auth import AuthManager
from .file_manager import save_file
from .battery_monitor import battery_monitor
from .system_monitor import sys_monitor
from security.watchdog import watchdog
from agent.fleet import FleetRegisterRequest, validate_fleet_key, register_agent_to_registry

AGENT_API_KEY = os.environ["AGENT_API_KEY"]
api_key_header = APIKeyHeader(name="X-API-Key")

router = CommandRouter()
auditor = AuditLogger()
sanitizer = InputSanitizer()


from .terminal_manager import terminal_manager

class CommandRequest(BaseModel):
    command: str
    user_id: str

class TerminalWriteRequest(BaseModel):
    user_id: str
    data: str

class TerminalRequest(BaseModel):
    user_id: str

class OTPRequest(BaseModel):
    user_id: str
    otp: str

import shutil
import platform

def check_system_dependencies():
    """Environment Health Check: Memastikan system dependencies tersedia."""
    missing = []
    current_os = platform.system()
    
    if current_os == "Linux":
        if not shutil.which("ffmpeg"):
            missing.append("ffmpeg (Dibutuhkan untuk perekaman video)")
        if not shutil.which("ydotool"):
            missing.append("ydotool (Dibutuhkan untuk fitur !unlock paksa)")
        if not shutil.which("wl-copy") and not shutil.which("xclip") and not shutil.which("xsel"):
            missing.append("wl-clipboard atau xclip (Dibutuhkan untuk sinkronisasi clipboard !clip)")
            
    if missing:
        logger.warning("⚠️ BEBERAPA DEPENDENSI SISTEM TIDAK DITEMUKAN:")
        for m in missing:
            logger.warning(f"  - {m}")
        if current_os == "Linux":
            logger.info("💡 Saran perbaikan: sudo apt-get install ffmpeg ydotool wl-clipboard xclip")
    else:
        logger.info("✅ Environment Health Check: Semua dependensi sistem terpenuhi.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Laptop Agent starting...")
    check_system_dependencies()

    # Warm up VisionAI model in background
    try:
        from ai_module.vision_ai import vision_ai
        if vision_ai.enabled:
            asyncio.create_task(vision_ai._warmup())
    except Exception:
        pass

    # Warmup memory system in background
    try:
        from agent.memory.manager import memory_manager
        asyncio.create_task(_warmup_memory())
    except Exception as e:
        logger.warning(f"Memory system init: {e}")

    # Start MCP Collector if was active
    try:
        from agent.memory.mcp_collector import mcp_collector
        asyncio.create_task(mcp_collector.start())
    except Exception:
        pass

    # Start Proactive Engine if was active
    try:
        from agent.proactive import proactive_engine
        asyncio.create_task(proactive_engine.start())
    except Exception:
        pass

    from agent.command_handler import clipboard_sync_loop
    sync_task = asyncio.create_task(clipboard_sync_loop())

    from agent.scheduler import scheduler
    async def run_scheduled(cmd: str):
        return await router.route(cmd, "scheduler")
    sched_task = asyncio.create_task(scheduler.check_loop(run_scheduled))

    if os.environ.get("RAV_MODE", "hub") == "agent":
        from agent.fleet import register_with_hub_loop
        asyncio.create_task(register_with_hub_loop())
    else:
        from agent.fleet import register_agent_to_registry
        host = os.environ.get("AGENT_HOST", "localhost")
        port = int(os.environ.get("AGENT_PORT", "8765"))
        api_key = os.environ.get("AGENT_API_KEY", "")
        agent_id = f"laptop-{host}"
        register_agent_to_registry(agent_id, host, port, api_key)

    yield
    sync_task.cancel()
    sched_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    try:
        await sched_task
    except asyncio.CancelledError:
        pass
    logger.info("Laptop Agent shutdown")

app = FastAPI(
    title="RAV-SPY Laptop Agent",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != AGENT_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


@app.post("/fleet/register")
async def fleet_register(request: FleetRegisterRequest):
    """Endpoint pairing — agent satellite mendaftar otomatis ke hub."""
    if os.environ.get("RAV_MODE", "hub") != "hub":
        raise HTTPException(status_code=403, detail="Fleet registration hanya tersedia di mode hub")

    if not validate_fleet_key(request.fleet_key):
        raise HTTPException(status_code=403, detail="Kode pairing fleet tidak valid")

    register_agent_to_registry(request.agent_id, request.host, request.port, request.api_key)
    logger.info(f"Fleet registered: {request.agent_id} -> {request.host}:{request.port}")
    return {"status": "ok", "agent_id": request.agent_id}


@app.get("/system/heartbeat")
async def heartbeat(_=Depends(verify_api_key)):
    """Heartbeat endpoint for Bot polling (Scenario C/VPN)."""
    metrics = sys_monitor.get_metrics()
    # Check for anomalies and battery
    anomalies = watchdog.check_system_anomalies(metrics["cpu"], metrics["ram"])
    battery = battery_monitor.get_alerts()
    
    from agent.command_handler import clipboard_alerts
    clip_alerts = list(clipboard_alerts)
    clipboard_alerts.clear()
    
    from agent.guard import guard_alerts
    g_alerts = list(guard_alerts)
    guard_alerts.clear()
    
    from agent.focus import focus_manager
    f_alerts = focus_manager.get_pending_alerts()
    
    from agent.reminder import reminder_alerts, check_reminders
    check_reminders()
    r_alerts = list(reminder_alerts)
    reminder_alerts.clear()

    from agent.scheduler import scheduled_alerts
    s_alerts = list(scheduled_alerts)
    scheduled_alerts.clear()

    from agent.proactive import proactive_alerts
    p_alerts = list(proactive_alerts)
    proactive_alerts.clear()
    
    return {
        "status": "ONLINE",
        "metrics": metrics,
        "alerts": anomalies + battery + clip_alerts + g_alerts + f_alerts + r_alerts + s_alerts + p_alerts
    }


@app.get("/system/scheduled-files")
async def get_scheduled_files(_=Depends(verify_api_key)):
    from agent.scheduler import scheduled_files
    files = list(scheduled_files)
    scheduled_files.clear()
    result = []
    for f in files:
        entry = {k: v for k, v in f.items() if k != "data"}
        entry["data"] = base64.b64encode(f["data"]).decode()
        result.append(entry)
    return {"files": result}


@app.get("/system/voice-cmd-status")
async def get_voice_cmd_status(_=Depends(verify_api_key)):
    from agent.voice_cmd import voice_cmd_manager
    return {"active": voice_cmd_manager.active}


@app.get("/system/file-watcher-changes")
async def get_file_watcher_changes(folder: str = None, _=Depends(verify_api_key)):
    from agent.file_watcher import file_watcher
    changes = file_watcher.get_pending_notifications(folder)
    for c in changes:
        file_watcher.acknowledge_notifications(c["folder"], len(c["changes"]))
    return {"changes": changes}


@app.get("/system/alerts")
async def get_alerts(_=Depends(verify_api_key)):
    # Combine battery alerts with watchdog anomalies
    metrics = sys_monitor.get_metrics()
    anomalies = watchdog.check_system_anomalies(metrics["cpu"], metrics["ram"])
    battery = battery_monitor.get_alerts()
    
    from agent.command_handler import clipboard_alerts
    clip_alerts = list(clipboard_alerts)
    clipboard_alerts.clear()
    
    from agent.guard import guard_alerts
    g_alerts = list(guard_alerts)
    guard_alerts.clear()
    
    from agent.reminder import reminder_alerts, check_reminders
    check_reminders()
    r_alerts = list(reminder_alerts)
    reminder_alerts.clear()
    
    return {"alerts": anomalies + battery + clip_alerts + g_alerts + r_alerts}


@app.post("/auth/verify-otp")
async def verify_otp(request: OTPRequest, _=Depends(verify_api_key)):
    if AuthManager.verify_otp(request.otp):
        token = AuthManager.generate_session_token(request.user_id)
        return {"token": token}
    else:
        # Record failure for watchdog
        is_brute = watchdog.record_otp_failure(request.user_id)
        if is_brute:
             logger.critical(f"Suspicious activity: Excessive OTP failures for {request.user_id}")
        raise HTTPException(status_code=401, detail="Invalid OTP")


@app.post("/terminal/start")
async def terminal_start(request: TerminalRequest, authorization: str = Header(...), _=Depends(verify_api_key)):
    token = authorization.replace("Bearer ", "")
    if AuthManager.verify_session_token(token) == request.user_id:
        if terminal_manager.start_session(request.user_id):
            return {"status": "success"}
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/terminal/write")
async def terminal_write(request: TerminalWriteRequest, authorization: str = Header(...), _=Depends(verify_api_key)):
    token = authorization.replace("Bearer ", "")
    if AuthManager.verify_session_token(token) == request.user_id:
        terminal_manager.write_to_session(request.user_id, request.data)
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/terminal/read/{user_id}")
async def terminal_read(user_id: str, authorization: str = Header(...), _=Depends(verify_api_key)):
    token = authorization.replace("Bearer ", "")
    if AuthManager.verify_session_token(token) == user_id:
        output = terminal_manager.read_from_session(user_id)
        return {"output": output or ""}
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/terminal/stop")
async def terminal_stop(request: TerminalRequest, authorization: str = Header(...), _=Depends(verify_api_key)):
    token = authorization.replace("Bearer ", "")
    if AuthManager.verify_session_token(token) == request.user_id:
        terminal_manager.stop_session(request.user_id)
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/file/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    authorization: str = Header(...),
    _=Depends(verify_api_key)
):
    token = authorization.replace("Bearer ", "")
    if AuthManager.verify_session_token(token) == user_id:
        content = await file.read()
        result = save_file(file.filename, content)
        return {"status": "success", "message": result}
    raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/command")
async def execute_command(
    request: CommandRequest,
    authorization: str = Header(...),
    _=Depends(verify_api_key),
):
    """Endpoint utama untuk eksekusi perintah."""
    # Verifikasi JWT dari bot
    token = authorization.replace("Bearer ", "")
    verified_user = AuthManager.verify_session_token(token)
    if not verified_user or verified_user != request.user_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Resolve custom alias before sanitization
    resolved = request.command
    if resolved.startswith("!"):
        try:
            from agent.custom_aliases import alias_manager
            alias_name = resolved.split()[0][1:].lower()
            alias_cmd = alias_manager.get(alias_name)
            if alias_cmd:
                resolved = alias_cmd
        except Exception:
            pass

    # Sanitasi input
    clean_input = sanitizer.sanitize_command(resolved)
    if not clean_input:
        auditor.log_security_alert(request.user_id, "INJECTION_ATTEMPT", request.command)
        raise HTTPException(status_code=400, detail="Input tidak valid atau berbahaya")

    result = await router.route(clean_input, request.user_id)

    if isinstance(result, bytes): # Legacy fallback
        return {"type": "image", "content": base64.b64encode(result).decode()}
    elif isinstance(result, dict):
        res_type = result.get("type")
        if res_type == "photo":
            resp = {"type": "image", "content": base64.b64encode(result["data"]).decode()}
            if "caption" in result:
                resp["caption"] = result["caption"]
            return resp
        elif res_type == "video":
            return {"type": "video", "content": {
                "data": base64.b64encode(result["data"]).decode(),
                "filename": result.get("filename", "screen_record.mp4"),
                "mimetype": result.get("mimetype", "video/mp4"),
            }}
        elif res_type == "audio":
            return {"type": "audio", "content": {
                "data": base64.b64encode(result["data"]).decode(),
                "filename": result.get("filename", "audio.mp3"),
                "mimetype": result.get("mimetype", "audio/mpeg"),
            }}
        elif res_type == "document" or ("filename" in result and "data" in result):
            return {"type": "document", "content": {
                "data": base64.b64encode(result["data"]).decode(),
                "filename": result.get("filename", "file.dat"),
                "mimetype": result.get("mimetype", "application/octet-stream"),
            }}
        elif "error" in result:
             return {"type": "text", "content": f"❌ {result['error']}"}
        else:
            final_text = str(result)
            return {"type": "text", "content": final_text}
    else:
        # Check if result is the specific summary from sys_monitor
        final_text = str(result)
        if request.command.strip() == "!sysinfo":
             final_text = sys_monitor.get_system_summary()
        return {"type": "text", "content": final_text}


async def _warmup_memory():
    try:
        from agent.memory.manager import memory_manager
        memory_manager.ensure_loaded()
        logger.info("✅ Memory system ready (384-d embeddings via ChromaDB ONNX)")
    except Exception as e:
        logger.warning(f"Memory warmup: {e}")

def _resolve_bind_host() -> str:
    if os.environ.get("AGENT_BIND_HOST"):
        return os.environ["AGENT_BIND_HOST"]
    # Setup fleet (RAV_MODE) default ke 0.0.0.0 agar multi-komputer LAN/Tailscale jalan
    if os.environ.get("RAV_MODE"):
        return "0.0.0.0"
    return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn
    from pathlib import Path
    bind_host = _resolve_bind_host()
    try:
        uvicorn.run(
            app,
            host=bind_host,
            port=int(os.environ.get("AGENT_PORT", "8765")),
            ssl_keyfile=os.environ.get("SSL_KEYFILE"),
            ssl_certfile=os.environ.get("SSL_CERTFILE"),
            loop="asyncio",
        )
    except KeyboardInterrupt:
        logger.info("Laptop Agent stopped by user request.")
