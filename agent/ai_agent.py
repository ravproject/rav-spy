import json
import subprocess
from pathlib import Path

HISTORY_DIR = Path.home() / ".config/rav-spy/aiagent"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = HISTORY_DIR / "history.json"

def _load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def _save_history(h):
    HISTORY_FILE.write_text(json.dumps(h, indent=2, default=str))

async def run_agent(task: str) -> str:
    import httpx
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        return "NVIDIA_NIM_API_KEY tidak ditemukan di .env. AI Agent tidak bisa dijalankan."
    model = os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
    base_url = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Kamu adalah AI agent yang membantu mengerjakan tugas kompleks di Linux desktop. Berikan jawaban yang langsung bisa dijalankan sebagai perintah shell atau langkah-langkah konkret. Jawab dalam Bahasa Indonesia."},
                        {"role": "user", "content": task}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024
                }
            )
            resp.raise_for_status()
            data = resp.json()
            result = data["choices"][0]["message"]["content"]
            history = _load_history()
            history.append({"task": task, "result": result, "timestamp": __import__('datetime').datetime.now().isoformat()})
            _save_history(history)
            return f"🤖 **AI Agent:**\n{result}"
    except Exception as e:
        return f"AI Agent error: {e}"

def get_history(limit: int = 5) -> str:
    history = _load_history()
    if not history:
        return "Belum ada histori AI Agent."
    lines = ["📜 Histori AI Agent:"]
    for h in history[-limit:]:
        t = h.get("task", "?")[:60]
        r = h.get("result", "?")[:80]
        lines.append(f"  Task: {t}")
        lines.append(f"  → {r}")
    return "\n".join(lines)

def clear_history() -> str:
    HISTORY_FILE.unlink(missing_ok=True)
    return "Histori AI Agent dibersihkan."
