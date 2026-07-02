"""
MemoryStore — ChromaDB persistent vector store.
Lokasi: ~/.config/rav-spy/memory/chroma/
"""
import os
import json
import hashlib
import uuid
import chromadb
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from loguru import logger

CHROMA_DIR = Path.home() / ".config" / "rav-spy" / "memory" / "chroma"
INDEX_FILE = CHROMA_DIR.parent / "index.json"
COLLECTION_NAME = "rav_memory"


class MemoryStore:
    def __init__(self, embedding_fn):
        self.embedding_fn = embedding_fn
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 100,
                "hnsw:M": 16,
            },
        )
        self._load_index()

    def _load_index(self):
        if INDEX_FILE.exists():
            with open(INDEX_FILE) as f:
                self.index = json.load(f)
        else:
            self.index = {"entries": 0, "topics": {}}

    def _save_index(self):
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_FILE, "w") as f:
            json.dump(self.index, f, indent=2)

    def _make_id(self, text: str) -> str:
        raw = f"{text[:80]}{datetime.now(timezone.utc).isoformat()}{uuid.uuid4().hex[:8]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def add(self, text: str, metadata: dict):
        if not text or len(text.strip()) < 10:
            return
        doc_id = self._make_id(text)
        self.collection.add(
            ids=[doc_id],
            documents=[text.strip()[:2048]],
            metadatas=[{
                **metadata,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        )
        self.index["entries"] += 1
        topic = metadata.get("topic", "general")
        self.index["topics"][topic] = self.index["topics"].get(topic, 0) + 1
        self._save_index()

    def search(self, query: str, k: int = 5, where_filter: Optional[dict] = None) -> list[dict]:
        kwargs = {
            "query_texts": [query],
            "n_results": k,
        }
        if where_filter:
            kwargs["where"] = where_filter
        results = self.collection.query(**kwargs)
        output = []
        if not results["ids"] or not results["ids"][0]:
            return output
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })
        return output

    def delete(self, doc_id: str):
        self.collection.delete(ids=[doc_id])
        self.index["entries"] = max(0, self.index["entries"] - 1)
        self._save_index()

    def delete_by_filter(self, where_filter: dict):
        self.collection.delete(where=where_filter)

    def count(self) -> int:
        return self.collection.count()

    def stats(self) -> dict:
        return {
            "total_entries": self.index["entries"],
            "topics": self.index["topics"],
            "chroma_count": self.collection.count(),
        }

    def get_all_entries(self, limit: int = 100) -> list[dict]:
        results = self.collection.get(limit=limit)
        output = []
        if not results["ids"]:
            return output
        for i in range(len(results["ids"])):
            output.append({
                "id": results["ids"][i],
                "text": results["documents"][i],
                "metadata": results["metadatas"][i],
            })
        return output
