import os
import json
import time
import httpx
from loguru import logger
from agent.memory.manager import memory_manager


class ProactiveSuggester:
    def __init__(self):
        self.nim_api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
        self.nim_base = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

    async def suggest(self, context: str = "") -> str:
        if not context:
            context = await self._gather_context()

        suggestions = await self._analyze_usage(context)

        if suggestions:
            return suggestions
        return "Belum cukup data untuk saran. Gunakan lebih banyak fitur RAV-SPY!"

    async def _gather_context(self) -> str:
        try:
            recent = memory_manager.search("recent activity", n_results=5)
            context_parts = ["Aktivitas pengguna:"]
            if recent and len(recent.get("documents", [])) > 0:
                for doc in recent["documents"]:
                    if doc:
                        context_parts.append(f"- {str(doc)[:200]}")
            return "\n".join(context_parts) if len(context_parts) > 1 else "Belum ada aktivitas."
        except Exception:
            return "Memory tidak tersedia."

    async def _analyze_usage(self, context: str) -> str:
        if not self.nim_api_key:
            return f"📊 *Pola Penggunaan:*\n{context[:1000]}"

        prompt = f"""Kamu adalah asisten yang menganalisis pola penggunaan fitur RAV-SPY.

Data penggunaan:
{context}

Tugasmu:
1. Analisis fitur apa yang paling sering digunakan
2. Identifikasi pola atau kebiasaan user
3. Rekomendasikan 2-3 fitur RAV-SPY yang relevan
4. Jelaskan mengapa fitur itu berguna untuk user
5. Gunakan bahasa Indonesia

Daftar fitur yang tersedia:
- !screenshot — Ambil screenshot
- !record — Rekam layar
- !lock — Kunci laptop jarak jauh
- !web — Cari internet
- !scrape — Ambil konten web
- !memory — Simpan/ingat informasi
- !internet_brain — Q&A dengan pengetahuan internet
- !live_web — Pencarian real-time
- !research — Riset komprehensif
- !news_digest — Ringkasan berita
- !trend_hunter — Identifikasi tren
- !comparator — Bandingkan item
- !qna — Tanya jawab mendalam
- !explain — Penjelasan konsep
- !translate — Terjemahan
- !vpn — Kontrol VPN
- !focus — Mode fokus
- !power — Manajemen daya
- !scheduler — Jadwal otomatis

Format:
💡 *Saran Proaktif*
Berdasarkan aktivitas terakhir kamu...

🔍 *Pola Terdeteksi:*
• [pola 1]
• [pola 2]

🎯 *Rekomendasi:*
• **[fitur 1]** — [alasan]
• **[fitur 2]** — [alasan]
• **[fitur 3]** — [alasan]
"""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.nim_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.nim_api_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct"),
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1024,
                        "temperature": 0.6,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"ProactiveSuggest error: {e}")
            return f"📊 *Aktivitas Terbaru:*\n{context[:1000]}"


proactive_suggester = ProactiveSuggester()
