# RAV-SPY Feature Reference

> Dokumen ini adalah **single source of truth** untuk semua fitur RAV-SPY.
> Setiap penambahan fitur BARU WAJIB update dokumen ini di **3 tempat**:
> 1. `docs/FEATURES.md` — Daftar fitur (file ini)
> 2. `ai_module/prompt_templates.py` — Biar AI tau tools yang tersedia
> 3. `config/allowed_commands.yaml` — Whitelist keamanan

---

## Arsitektur Command Flow

```
User (Natural Language / !command)
        │
        ▼
┌──────────────────────────────┐
│  CommandInterpreter.interpret │  ← ai_module/nim_client.py
│  ┌─ NIMClient (AI) ───────┐  │
│  │  Natural language →     │  │
│  │  command_name + args    │  │
│  └─────────────────────────┘  │
│  ┌─ FallbackParser ────────┐  │
│  │  !command →              │  │
│  │  command_name + args    │  │
│  └─────────────────────────┘  │
└──────────────┬───────────────┘
               │ command_name + args
               ▼
┌──────────────────────────────┐
│       CommandRouter.route     │  ← bot/command_router.py
│  Validasi whitelist           │
│  Routing ke handler           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      CommandHandler.handle_*  │  ← agent/command_handler.py
│  Eksekusi perintah            │
└──────────────────────────────┘
```

### Cara Menambahkan Fitur Baru

```python
# 1. Handler — agent/command_handler.py
async def handle_fitur_baru(self, args: list[str]) -> str:
    ...

# 2. Router — bot/command_router.py
elif command_name == "fitur_baru":
    result = await self.handler.handle_fitur_baru(args)

# 3. Fallback parser — ai_module/fallback_parser.py
COMMAND_MAP = {
    ...
    "!fitur_baru": "fitur_baru",
    "!alias_bahasa": "fitur_baru",  # alias Indonesia
}

# 4. Prompt templates — ai_module/prompt_templates.py
# Tambah ke SYSTEM_PROMPT bagian yang sesuai
"   - !fitur_baru <args> (Deskripsi fitur)"

# 5. Whitelist — config/allowed_commands.yaml
safe_commands:
  fitur_baru:
    description: "Deskripsi"
    requires_confirmation: false
    sandbox_required: false

# 6. Docs — docs/FEATURES.md (file ini)
# Tambah ke kategori yang sesuai
```

---

## Daftar Lengkap Fitur

### 1. 🔒 System & Security

| Perintah | Alias Indonesia | Handler | Fungsi |
|----------|----------------|---------|--------|
| `!lock_screen` | `!kunci` | `handle_lock_screen` | Kunci layar laptop |
| `!unlock` | `!buka` | `handle_unlock_screen` | Buka kunci layar |
| `!reboot` | — | `handle_reboot` | Restart laptop (⚠️confirm) |
| `!logout` | — | `handle_logout` | Keluar sesi |
| `!guard` | — | `handle_guard` | Deteksi gerakan via webcam |
| `!sleep` | `!tidur` | `handle_sleep` | Tidurkan laptop |
| `!wake` | `!bangun` | `handle_wake` | Jadwal bangunkan |
| `!lock` | — | `handle_lock_screen` | Alias lock |

### 2. 📸 Media & Capture

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!screenshot` | `!ss` | `handle_screenshot` | Screenshot layar |
| `!video` | — | `handle_video` | Rekam layar (max 30s) |
| `!webcam` | — | `handle_webcam` | Foto webcam |
| `!webcamvid` | `!camvid` | `handle_webcam_video` | Rekam video webcam |

### 3. 🖱️ Input Simulation

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!click` | — | `handle_click` | Klik mouse kiri |
| `!rightclick` | `!clickkanan` | `handle_rightclick` | Klik kanan |
| `!doubleclick` | `!dobelklik` | `handle_doubleclick` | Double klik |
| `!type` | — | `handle_type` | Ketik teks |
| `!press` | — | `handle_press` | Tekan tombol keyboard |
| `!scroll` | `!gulir` | `handle_scroll` | Scroll |
| `!drag` | — | `handle_drag` | Drag & drop |
| `!clickimage` | `!clickimg` | `handle_clickimage` | Klik berdasarkan gambar |
| `!waitimage` | `!waitimg` | `handle_waitimage` | Tunggu gambar muncul |

### 4. 📁 File & Navigation

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!ls` | `!list_files` | `handle_list_files` | List direktori |
| `!cd` | — | `handle_cd` | Pindah direktori |
| `!get` | `!get_file` | `handle_get_file` | Download file (⚠️confirm) |
| `!find` | — | `handle_find_files` | Cari file rekursif |
| `!search_content` | `!cari` | `handle_search_content` | Cari teks dalam file |
| `!recent` | — | `handle_recent` | File/folder terbaru |
| `!organize` | `!rapikan` | `handle_organize` | Organisir file |
| `!backup` | — | `handle_backup` | Backup folder |
| `!convert` | `!converter` | `handle_convert` | Konversi format file |
| `!clean` | `!bersihkan` | `handle_clean` | Bersihkan sampah disk |
| `!file_watcher` | `!watcher` | `handle_file_watcher` | Pantau folder |
| `!version` | `!versi` | `handle_version` | Versioning file lokal |

### 5. 📋 Clipboard

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!clip read` | `!read` | `handle_clip_read` | Baca clipboard |
| `!clip write` | `!write` | `handle_clip_write` | Tulis clipboard |
| `!clip sync` | — | `handle_clip_sync` | Sinkron otomatis |
| `!smart_clip` | `!smart` | `handle_smart_clip` | Smart clipboard |

### 6. 💻 System Info & Control

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!sysinfo` | `!info` | `handle_sysinfo` | Info CPU/RAM/Disk |
| `!battery` | — | `handle_battery` | Status & kesehatan baterai |
| `!brightness` | — | `handle_brightness` | Kecerahan layar |
| `!volume` | — | `handle_volume` | Volume global/per-app |
| `!power` | `!daya` | `handle_power` | Profil daya |
| `!media` | — | `handle_media` | Kontrol media player |
| `!notif` | — | `handle_notif` | Desktop notification |
| `!tts` | — | `handle_tts_speak` | Text-to-Speech |
| `!process` | — | `handle_process` | Manajemen proses |
| `!top` | — | `handle_top` | Task manager |
| `!kill` | — | `handle_kill` | Matikan proses |
| `!ports` | — | `handle_active_ports` | Port listening |
| `!wifi` | — | `handle_wifi_scan` | Scan Wi-Fi |
| `!ping` | — | `handle_ping` | Ping host |
| `!speedtest` | — | `handle_speedtest` | Test internet |
| `!alarm` | — | `handle_alarm` | Alarm pencari laptop |
| `!active` | — | `handle_active_window` | Jendela aktif |
| `!run` | `!run_script` | `handle_run_script` | Jalankan script (⚠️confirm) |
| `!listen` | `!audio` | `handle_listen` | Rekam suara |
| `!mute` | — | `handle_audio_control` | Mute toggle |

### 7. 🌐 Network & Connectivity

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!web` | `!google` | `handle_web_search` | Cari web |
| `!scrape` | `!scrap` | `handle_scrape` | Scrape konten web |
| `!open` | — | `handle_open_url` | Buka URL di browser |
| `!vpn` | — | `handle_vpn` | Kontrol VPN |
| `!tunnel` | `!ssh` | `handle_tunnel` | SSH tunnel |

### 8. 🚀 Application & Window

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!launch` | — | `handle_launch_app` | Buka aplikasi |
| `!apps` | — | `handle_list_apps` | Daftar aplikasi |
| `!quick_app` | `!quickapp` | `handle_quick_app` | Buka app cepat |
| `!window_control` | `!win` | `handle_window_control` | Kontrol jendela |
| `!window` | `!jendela` | `handle_window_arrange` | Atur semua jendela |
| `!multi_monitor` | `!monitor` | `handle_multi_monitor` | Kelola monitor ganda |
| `!night_mode` | `!malam` | `handle_night_mode` | Mode malam |
| `!hotkey` | `!hotkeys` | `handle_hotkey` | Hotkey global |

### 9. 📝 Productivity

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!focus` | `!pomodoro` | `handle_focus` | Mode fokus + Pomodoro |
| `!workspace` | `!ws` | `handle_workspace` | Simpan/muat sesi kerja |
| `!quicknote` | `!note` | `handle_quicknote` | Catatan cepat |
| `!browser` | `!chrome` | `handle_browser` | Kontrol browser remote |
| `!daily` | `!report` | `handle_daily` | Laporan aktivitas |
| `!reminder` | `!remind` | `handle_reminder` | Pengingat |
| `!todo` | — | `handle_todo` | Daftar tugas |
| `!task` | `!todoist` | `handle_task` | Manajemen tugas |
| `!meeting` | `!meet` | `handle_meeting` | Mode meeting |
| `!custom` | `!alias` | `handle_custom` | Alias kustom |
| `!schedule` | `!jadwal` | `handle_schedule` | Jadwal perintah |
| `!macro` | — | `handle_macro` | Rekam/putar aksi |
| `!voice_cmd` | `!suara` | `handle_voice_cmd` | Voice command dari HP |

### 10. 🤖 AI & Automation

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!ai work` | — | `handle_ai_work` | AI produktivitas |
| `!ai write` | — | `handle_ai_write` | Draft dokumen via AI |
| `!ai automate` | — | `handle_ai_automate` | Automation script |
| `!ai summarize` | — | `handle_ai_summarize` | Ringkasan file |
| `!ai research` | — | `handle_ai_research` | Riset topik |
| `!ai insight` | — | `handle_ai_insight` | Analisis pola |
| `!opencode` | — | `handle_opencode` | AI coding agent |
| `!agy` | — | `handle_agy` | Antigravity CLI |
| `!testai` | `!test-ai` | `handle_test_ai` | Test koneksi AI |
| `!ai_agent` | `!aiagent` | `handle_ai_agent` | AI agent tugas kompleks |

### 11. 🧠 AI Advanced Intelligence (NEW)

| Perintah | Alias Indonesia | Handler | Fungsi |
|----------|----------------|---------|--------|
| `!memory` | `!ingat` | `handle_memory` | Long-term memory RAG (search/summarize/forget/stats/sync) |
| `!mcp` | — | `handle_mcp` | Memory Context Provider (on/off/status/query) |
| `!companion` | `!teman` | `handle_companion` | Personal AI companion |
| `!solve` | `!atasi` | `handle_solve` | Problem solver + web search |
| `!create_feature` | `!buat` | `handle_create_feature` | Self-feature generation (⚠️confirm) |
| `!self_evolve` | `!evolve` | `handle_self_evolve` | Auto evolution engine |
| `!optimize_me` | `!optimize` | `handle_optimize_me` | Usage optimization |
| `!proactive` | `!proaktif` | `handle_proactive` | Proactive awareness |
| `!learn` | `!belajar` | `handle_learn` | Knowledge enrichment |
| `!agent_mode` | — | `handle_agent_mode` | Autonomous agent mode |

### 12. 🔄 Data Management

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!sync` | — | `handle_sync` | Sinkron folder ke cloud |
| `!quick_upload` | `!upload` | `handle_quick_upload` | Upload dari HP |
| `!quick` | — | `handle_quick` | Dispatcher quick |

### 13. 📊 Analytics & Monitoring

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!time_track` | `!track` | `handle_time_track` | Lacak waktu kerja |
| `!session` | `!handoff` | `handle_session` | Simpan session aplikasi |
| `!share_screen` | `!share` | `handle_share_screen` | Screenshot |
| `!multi_device` | `!device` | `handle_multi_device` | Multi perangkat |
| `!profile` | `!profil` | `handle_profile` | Profile pengguna |
| `!dash` | `!dashboard` | `handle_dash` | Dashboard sistem |
| `!activity_log` | `!log` | `handle_activity_log` | Log aktivitas |
| `!help` | — | `handle_help` | Bantuan |

### 14. ⚙️ Terminal

| Perintah | Alias | Handler | Fungsi |
|----------|-------|---------|--------|
| `!term` | `!terminal` | `handle_terminal` | Terminal interaktif |

---

## Fitur Otomatis (Background Tasks)

| Fitur | File | Interval | Fungsi |
|-------|------|----------|--------|
| **MCP Collector** | `agent/memory/mcp_collector.py` | 30 detik | Snapshot aktivitas (jendela aktif, project, file, sistem) → ChromaDB |
| **Proactive Engine** | `agent/proactive.py` | 5 menit | Analisis konteks, kirim alert proaktif |
| **Clipboard Sync** | `agent/command_handler.py` | Real-time | Sinkron clipboard laptop ↔ HP |
| **Scheduler** | `agent/scheduler.py` | 1 menit | Eksekusi perintah terjadwal |
| **File Watcher** | `agent/file_watcher.py` | Real-time | Pantau perubahan folder |
| **Guard Mode** | `agent/guard.py` | Real-time | Deteksi gerakan webcam |
| **System Monitor** | `agent/system_monitor.py` | Per heartbeat | CPU/RAM/Disk monitoring |
| **Battery Monitor** | `agent/battery_monitor.py` | Per heartbeat | Alert baterai rendah |

---

## Arsitektur File

```
rav-spy/
├── agent/
│   ├── main.py                      # FastAPI app, lifespan (start background tasks)
│   ├── command_handler.py           # Semua handler (2799 baris)
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── embeddings.py            # ONNX embedding (384-d, via ChromaDB)
│   │   ├── store.py                 # ChromaDB persistent store
│   │   ├── manager.py               # Memory orchestrator
│   │   ├── mcp_collector.py         # Background context collector
│   │   └── sync.py                  # Cross-device encryption sync
│   ├── companion.py                 # AI companion
│   ├── solver.py                    # Problem solver
│   ├── self_feature.py              # Self-feature generation
│   ├── evolution.py                 # Self-evolution engine
│   ├── optimizer.py                 # Usage optimizer
│   ├── proactive.py                 # Proactive engine
│   ├── knowledge.py                 # Knowledge enrichment
│   ├── autonomous_agent.py          # Autonomous agent mode
│   └── ... berbagai module lain
├── bot/
│   ├── telegram_bot.py              # Telegram polling
│   ├── command_router.py            # Router (880 baris)
│   └── auth.py                      # JWT + OTP auth
├── ai_module/
│   ├── nim_client.py                # NIM AI client + interpreter
│   ├── fallback_parser.py           # !command parser (232 baris, 190+ entries)
│   └── prompt_templates.py          # AI system prompt
├── config/
│   └── allowed_commands.yaml        # Whitelist (171 entries)
├── security/
│   ├── sanitizer.py                 # Input sanitizer (auto-reload YAML)
│   └── audit_logger.py             # Audit logging
└── docs/
    └── FEATURES.md                  # File ini
```

---

## Konvensi Penamaan

| Komponen | Konvensi | Contoh |
|----------|----------|--------|
| Handler method | `handle_<nama>` | `handle_memory` |
| Command name | `snake_case` | `create_feature` |
| Alias Indonesia | Satu kata | `!ingat`, `!teman` |
| Fallback parser key | `!<nama>` | `!ingat` |
| YAML entry | Sama dengan command name | `memory:`, `ingat:` |
| Router elif | `command_name == "<nama>"` | `command_name == "memory"` |

### Aturan Alias Indonesia
- Setiap fitur punya **minimal 1 alias Indonesia** di fallback parser
- Alias ditambah ke **YAML whitelist** sebagai entri terpisah
- Alias ditambah ke **prompt_templates.py** (opsional, biar AI tau)
- Gunakan kata yang natural dan mudah diingat

---

## Testing Checklist untuk Fitur Baru

- [ ] Handler: `py_compile` lolos
- [ ] Import handler dari command_handler.py tidak error
- [ ] Fallback parser mapping benar
- [ ] YAML whitelist entry ada (termasuk alias Indonesia)
- [ ] Router `elif` ditambahkan
- [ ] Prompt templates diupdate
- [ ] FEATURES.md diupdate
- [ ] Sanitizer menerima perintah (test manual `!fitur_baru`)
- [ ] Router route test (test `!fitur_baru -> expected`)
- [ ] Service restart (karena Python hot-reload terbatas)
