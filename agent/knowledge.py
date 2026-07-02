"""
Continuous Knowledge Enrichment Engine.
"""
import os
import json
import httpx
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from agent.memory.manager import memory_manager

KNOWLEDGE_DIR = Path.home() / ".config" / "rav-spy" / "knowledge"


class KnowledgeEngine:
    def __init__(self):
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self.index_file = KNOWLEDGE_DIR / "index.json"
        self.nim_api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
        self.nim_base = os.environ.get(
            "NVIDIA_NIM_BASE_URL",
            "https://integrate.api.nvidia.com/v1",
        )
        self.nim_model = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")
        self._load_index()

    def _load_index(self):
        if self.index_file.exists():
            with open(self.index_file) as f:
                self.index = json.load(f)
        else:
            self.index = {"topics": {}, "total_articles": 0}

    def _save_index(self):
        with open(self.index_file, "w") as f:
            json.dump(self.index, f, indent=2)

    async def learn(self, topic: str) -> str:
        articles = await self._search_articles(topic)
        if not articles:
            return f"❌ Tidak menemukan artikel tentang '{topic}'."

        saved = []
        for i, article in enumerate(articles[:3]):
            summary = await self._summarize_article(article, topic)
            if summary:
                safe_name = topic.lower().replace(" ", "_")[:30]
                fname = KNOWLEDGE_DIR / f"{safe_name}_{i}.json"
                entry = {
                    "topic": topic,
                    "source": article.get("url", ""),
                    "title": article.get("title", ""),
                    "summary": summary,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
                with open(fname, "w") as f:
                    json.dump(entry, f, indent=2)
                saved.append(article.get("title", f"Article {i+1}"))

                try:
                    memory_manager.remember(
                        f"Knowledge: {topic} — {summary[:300]}",
                        source="knowledge",
                        topic=topic,
                        tags=["knowledge", "learned"],
                    )
                except Exception:
                    pass

        self.index["topics"][topic] = self.index["topics"].get(topic, 0) + len(saved)
        self.index["total_articles"] += len(saved)
        self._save_index()

        return (
            f"📚 *Knowledge Enriched: {topic}*\n"
            f"✅ {len(saved)} artikel disimpan:\n"
            + "\n".join(f"  • {s}" for s in saved)
            + f"\n\nTotal knowledge base: {self.index['total_articles']} articles"
        )

    async def _search_articles(self, topic: str) -> list[dict]:
        try:
            from agent.scraper import search_web
            return await search_web(topic, max_results=3)
        except Exception:
            return []

    async def _summarize_article(self, article: dict, topic: str) -> str | None:
        text = article.get("content", article.get("snippet", ""))[:3000]
        if not text:
            return None

        prompt = f"""Summarize the following article about '{topic}' in 3-5 bullet points in Indonesian.
Focus on key insights, trends, and actionable information.

Article: {text}"""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.nim_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.nim_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.nim_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 512,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Summarize error: {e}")
            return None

    def list_topics(self) -> str:
        if not self.index["topics"]:
            return "Knowledge base kosong. Gunakan `!learn <topik>` untuk mengisi."
        lines = ["📚 *Knowledge Base Topics:*"]
        for topic, count in sorted(self.index["topics"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {topic}: {count} artikel")
        return "\n".join(lines)


knowledge_engine = KnowledgeEngine()
