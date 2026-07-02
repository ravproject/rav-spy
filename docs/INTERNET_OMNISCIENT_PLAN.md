# RAV-SPY Internet Omniscient — Implementation Plan

> **Fitur Kecerdasan Internet yang Mendalam**  
> Versi: 1.0 — 25 Juni 2026  

---

## 1. Visi

Menjadikan RAV-SPY AI sebagai **AI dengan pengetahuan hampir segalanya di internet** — mampu riset mendalam, verifikasi fakta, deteksi tren, dan eksekusi web action, semuanya terintegrasi dengan Long-Term Memory + remote control laptop.

---

## 2. Arsitektur

```
┌─────────────────────────────────────────────────────┐
│                   User (Natural Language)             │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│         AI Router (NIM → command_name + args)         │
│  prompt_templates.py udah tau semua tools internet    │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Internet Intelligence Layer               │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Research  │  │ Live Web │  │ Deep Scrape       │   │
│  │ Engine    │  │ Engine   │  │ Engine            │   │
│  └─────┬─────┘  └─────┬───┘  └────────┬─────────┘   │
│        │              │               │              │
│  ┌─────▼──────────────▼───────────────▼──────────┐   │
│  │           Web Searcher (existing scraper.py)     │  │
│  │  DDG │ Yahoo │ RSS │ HTTP Fetch + Cache         │  │
│  └────────────────────┬──────────────────────────┘   │
│                       │                              │
│  ┌────────────────────▼──────────────────────────┐   │
│  │         LLM Analyzer (NVIDIA NIM)               │  │
│  │  Summarize │ Compare │ Verify │ Extract         │  │
│  └────────────────────┬──────────────────────────┘   │
│                       │                              │
│  ┌────────────────────▼──────────────────────────┐   │
│  │         Memory Store (ChromaDB)                 │  │
│  │  Research results │ Knowledge │ Trends          │  │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Dependency Graph

```
                    ┌─────────────────┐
                    │ scraper.py       │ ← existing (DDG, Yahoo, RSS, HTTP, cache)
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                 ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ research.py  │ │ live_web.py  │ │ deep_scrape  │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┼────────────────┘
                            ▼
                  ┌──────────────────┐
                  │ nim_client.py    │ ← existing (LLM calls)
                  └────────┬─────────┘
                           │
                  ┌────────▼─────────┐
                  │ memory/manager   │ ← existing (ChromaDB)
                  └──────────────────┘
```

---

## 4. Implementation Phases

### Phase 1: Foundation (5 fitur inti)
| # | Fitur | File Baru | Dependensi |
|---|-------|-----------|------------|
| 1 | `!internet brain` | `agent/internet_brain.py` | scraper, nim_client, memory |
| 2 | `!live web` | `agent/live_web.py` | scraper, nim_client |
| 3 | `!deep scrape` | `agent/deep_scrape.py` | scraper, nim_client |
| 4 | `!research` | `agent/research.py` | scraper, nim_client, memory |
| 5 | `!verify fact` | `agent/fact_checker.py` | scraper, nim_client |

### Phase 2: Intelligence (3 fitur)
| # | Fitur | File Baru | Dependensi |
|---|-------|-----------|------------|
| 6 | `!news digest` | `agent/news_digest.py` | scraper (RSS), nim_client, memory |
| 7 | `!trend hunter` | `agent/trend_hunter.py` | scraper (multi-source), nim_client |
| 8 | `!compare` | `agent/comparator.py` | scraper, nim_client |

### Phase 3: Agentic (2 fitur)
| # | Fitur | File Baru | Dependensi |
|---|-------|-----------|------------|
| 9 | `!agent researcher` | `agent/researcher_agent.py` | semua phase 1+2, scheduler |
| 10 | `!knowledge update` | `agent/knowledge_updater.py` | semua phase 1, scheduler, memory |

### Phase 4: Ultra Advanced (Opsional)
| # | Fitur | File Baru | Dependensi |
|---|-------|-----------|------------|
| 11 | `!multi agent` | `agent/multi_agent_orch.py` | semua |
| 12 | `!auto learning daily` | `agent/auto_learner.py` | scheduler, memory |
| 13 | `!predict trend` | `agent/trend_predictor.py` | trend_hunter, nim_client |
| 14 | `!personal knowledge graph` | `agent/knowledge_graph.py` | memory |
| 15 | `!web action` | `agent/web_action.py` | scraper, playwright |

---

## 5. File Changes per Feature

Setiap fitur baru butuh perubahan di **6 file** (ikuti pola dari FEATURES.md):

```
agent/<feature>.py          → file baru: class + handler logic
agent/command_handler.py    → +1 method: handle_<feature>
bot/command_router.py       → +1 elif: routing
ai_module/fallback_parser.py → +2 entries: !<feature> + !<alias_id>
ai_module/prompt_templates.py → +1 baris: deskripsi tool
config/allowed_commands.yaml → +2 entries: fitur + alias
```

---

## 6. Detail Spesifikasi Fitur

### 6.1 `!internet brain [query]` — `agent/internet_brain.py`

**Handler**: `handle_internet_brain(self, args: list[str]) -> str`

**Flow**:
1. Ambil query dari args
2. Search web via scraper (DDG + Yahoo)
3. Scrape top 3 hasil
4. Feed content + query ke NIM untuk jawaban komprehensif
5. Simpan Q&A ke memory (topic="internet_brain")
6. Return jawaban + sumber

**Fallback**: "Maaf, tidak bisa mengakses internet saat ini."

**Alias**: `!omniscient`, `!otak_internet`

---

### 6.2 `!live web [query]` — `agent/live_web.py`

**Handler**: `handle_live_web(self, args: list[str]) -> str`

**Flow**:
1. Search web via scraper
2. Tampilkan hasil: judul, snippet, URL (max 5)
3. Simpan context query terakhir untuk follow-up (module-level var)
4. Follow-up: jika user tanya lanjutan tanpa `!`, AI detect dan panggil live_web lagi dengan konteks

**Alias**: `!web_langsung`, `!cari`

**Note**: Ini mirip `!web` yang sudah ada tapi lebih kaya — bedanya pake scraper multi-engine + bisa follow-up.

---

### 6.3 `!deep scrape [url] [task]` — `agent/deep_scrape.py`

**Handler**: `handle_deep_scrape(self, args: list[str]) -> str`

**Flow**:
1. Fetch URL via scraper HTTP adapter
2. Extract content (existing _extract_content)
3. Kirim content + task instruction ke NIM
4. NIM return analisis sesuai task (ekstrak data, ringkas, dll)
5. Simpan hasil ke memory

**Alias**: `!scrape_dalam`, `!analisis_url`

---

### 6.4 `!research [topik] [depth]` — `agent/research.py`

**Handler**: `handle_research(self, args: list[str]) -> str`

**Parameter**: `depth` = `light` | `medium` | `deep` (default: `medium`)

**Flow**:
- **light**: 3 search queries → 3 scrapes → 1 NIM summary (~30s)
- **medium**: 5 search queries → 5 scrapes → multi-prompt NIM analysis (~2m)
- **deep**: 10 search queries → 10 scrapes → multi-prompt analysis + rekomendasi (~5m)

**Output**: Laporan lengkap: ringkasan, poin utama, sumber, rekomendasi

**Alias**: `!riset`, `!teliti`

---

### 6.5 `!verify fact [pernyataan]` — `agent/fact_checker.py`

**Handler**: `handle_verify_fact(self, args: list[str]) -> str`

**Flow**:
1. Search web untuk pernyataan
2. Scrape 3-5 sumber yang relevan
3. NIM bandingkan klaim dengan bukti dari sumber
4. Return: ✅ Rating kepercayaan (0-100%) + penjelasan + sumber

**Alias**: `!cek_fakta`, `!verifikasi`

---

### 6.6 `!news digest [topik] [periode]` — `agent/news_digest.py`

**Handler**: `handle_news_digest(self, args: list[str]) -> str`

**Parameter**: `periode` = `today` | `week` | `month`

**Flow**:
1. Cari RSS feeds berdasarkan topik (gunakan list RSS default + DDG search)
2. Parse RSS feeds
3. NIM summarization dari artikel yang relevan
4. Simpan ke memory
5. Return digest

**Alias**: `!berita`, `!ringkasan_berita`

---

### 6.7 `!trend hunter [bidang]` — `agent/trend_hunter.py`

**Handler**: `handle_trend_hunter(self, args: list[str]) -> str`

**Sources**: Google Trends (via scrape), Reddit (via scrape), GitHub Trending, News RSS

**Flow**:
1. Multi-source search untuk topik
2. Extract trending keywords, frekuensi
3. NIM analisis tren
4. Return: daftar tren + insight

**Alias**: `!pemburu_tren`, `!tren`

---

### 6.8 `!compare [item1] vs [item2]` — `agent/comparator.py`

**Handler**: `handle_compare(self, args: list[str]) -> str`

**Flow**:
1. Parse args: cari " vs " atau " versus " separator
2. Search web untuk kedua item
3. Scrape review/comparison pages
4. NIM buat tabel perbandingan (spesifikasi, harga, pros/cons)
5. Return: tabel + rekomendasi

**Alias**: `!bandingkan`, `!vs`

---

### 6.9 `!agent researcher [goal] [duration]` — `agent/researcher_agent.py`

**Handler**: `handle_researcher_agent(self, args: list[str]) -> str`

**Parameter**: `duration` = `30m` | `1h` | `2h` | `4h` | (default: `30m`)

**Flow**:
1. Parse goal + durasi
2. Buat research plan (break down goal ke sub-questions)
3. Loop: search → scrape → analyze → save partial results
4. Setelah selesai: NIM kompilasi final report
5. Simpan ke memory

**Alias**: `!agent_riset`, `!riset_otonom`

---

### 6.10 `!knowledge update [topik]` — `agent/knowledge_updater.py`

**Handler**: `handle_knowledge_update(self, args: list[str]) -> str`

**Flow**:
1. Search topik
2. Scrape + NIM summarize top articles
3. Simpan ke ChromaDB sebagai knowledge entry (topic="knowledge")
4. Bisa dijadwalkan: `!schedule add "!knowledge update AI" daily at 08:00`

**Alias**: `!update_pengetahuan`, `!pelajari`

---

## 7. Indonesian Command Aliases

| English | Indonesia | Fallback Parser Entry |
|---------|-----------|----------------------|
| `!internet_brain` | `!otak_internet` | `"!otak_internet": "internet_brain"` |
| `!live_web` | `!web_langsung` | `"!web_langsung": "live_web"` |
| `!deep_scrape` | `!scrape_dalam` | `"!scrape_dalam": "deep_scrape"` |
| `!research` | `!riset` | `"!riset": "research"` |
| `!verify_fact` | `!cek_fakta` | `"!cek_fakta": "verify_fact"` |
| `!news_digest` | `!berita` | `"!berita": "news_digest"` |
| `!trend_hunter` | `!pemburu_tren` | `"!pemburu_tren": "trend_hunter"` |
| `!compare` | `!bandingkan` | `"!bandingkan": "compare"` |
| `!agent_researcher` | `!riset_otonom` | `"!riset_otonom": "agent_researcher"` |
| `!knowledge_update` | `!update_pengetahuan` | `"!update_pengetahuan": "knowledge_update"` |

---

## 8. Yang Perlu Ditambahkan ke `scraper.py`

| Fitur | Keterangan |
|-------|------------|
| **Google News RSS** | Tambah adapter Google News RSS |
| **Reddit scrape** | Ambil post + komentar dari Reddit |
| **GitHub trending** | Scrape GitHub trending page |
| **Multi-URL batch** | Fungsi untuk scrape beberapa URL sekaligus |
| **Search query generator** | Buat variasi query dari topik untuk coverage lebih luas |

---

## 9. Risk Matrix

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Web scraping diblokir | Tinggi | Multi-engine fallback + rotate UA + caching |
| NIM API timeout (deep research) | Sedang | Stream partial results, timeout handling |
| ChromaDB penuh | Rendah | Auto-cleanup based on TTL, topic-based eviction |
| User abuse (spam research) | Sedang | Rate limiting per user per jam |
| API key habis quota | Sedang | Graceful fallback + notifikasi user |

---

## 10. Perkiraan Beban

| Operasi | Search calls | Scrape calls | NIM calls | Waktu |
|---------|-------------|--------------|-----------|-------|
| `!internet_brain` | 1 | 3 | 1 | 10-20s |
| `!research light` | 3 | 3 | 1 | 20-40s |
| `!research medium` | 5 | 5 | 2-3 | 1-3m |
| `!research deep` | 10 | 10 | 3-5 | 3-8m |
| `!agent_researcher 1h` | 20-50 | 20-50 | 10-20 | 30-60m |
| `!news digest` | 0 | 3-5 RSS | 1 | 10-20s |
| `!trend hunter` | 5 | 5 | 1 | 20-40s |

---

## 11. File Structure (Final)

```
rav-spy/
├── agent/
│   ├── internet_brain.py       ← PHASE 1
│   ├── live_web.py             ← PHASE 1
│   ├── deep_scrape.py          ← PHASE 1
│   ├── research.py             ← PHASE 1
│   ├── fact_checker.py         ← PHASE 1
│   ├── news_digest.py          ← PHASE 2
│   ├── trend_hunter.py         ← PHASE 2
│   ├── comparator.py           ← PHASE 2
│   ├── researcher_agent.py     ← PHASE 3
│   ├── knowledge_updater.py    ← PHASE 3
│   └── scraper.py              ← modified (ditambah adapter)
├── docs/
│   └── INTERNET_OMNISCIENT_PLAN.md  ← file ini
```

---

## 12. Cara Memulai

```
Phase 1: !internet_brain + !live_web + !deep_scrape + !research + !verify_fact
  → 5 file baru, 5 handler, 5 router elif, 10 fallback entries, 10 YAML entries

Phase 2: !news_digest + !trend_hunter + !compare
  → 3 file baru, 3 handler, 3 router elif, 6 fallback entries, 6 YAML entries

Phase 3: !agent_researcher + !knowledge_update
  → 2 file baru, 2 handler, 2 router elif, 4 fallback entries, 4 YAML entries
```

Setiap phase butuh restart service (`systemctl --user restart rav-agent.service`).
