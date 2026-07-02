# RAV-SPY — Remote Laptop Intelligence via Telegram

**RAV-SPY v2.0** is a stealth laptop intelligence and remote control system that operates through Telegram. Control, monitor, and gather intelligence from your laptop remotely using chat commands.

Bahasa Indonesia-first interface, 150+ commands, fully self-hosted.

---

## Features

### 5-Layer Architecture

```
[HP Kamu] --Telegram--> [Bot Layer] --HTTP API--> [Agent Layer] --OS--> [Laptop]
                            |                            |
                      [AI Interpreter]             [Command Handler]
                      (NVIDIA NIM)                 (3300+ baris kode)
                            |                            |
                      [Security Layer]             [Memory System]
                      (5 modul)                    (ChromaDB, ONNX)
```

### System Control & Monitoring
- `!screenshot` / `!ss` — Screenshot layar (bisa region)
- `!video <detik>` — Rekam layar (ffmpeg, max 30s)
- `!webcam` / `!cam` — Foto webcam
- `!webcamvid` / `!camvid` — Video webcam
- `!sysinfo` / `!info` — CPU, RAM, disk, OS
- `!battery` / `!bat` — Status baterai + alert <20%
- `!process` / `!proses` — List/kill proses
- `!top` — Proses paling boros resource
- `!volume`, `!mute` — Kontrol volume
- `!brightness` — Kecerahan layar
- `!media` — Media playback (play/pause/next/prev)
- `!power` / `!daya` — Power profile
- `!active` — Window aktif sekarang
- `!window` / `!win` — Atur jendela

### Input Simulation
- `!click`, `!rightclick`, `!doubleclick` — Klik mouse
- `!type` / `!ketik` — Ketik teks
- `!press` / `!tekan` — Tekan tombol keyboard
- `!scroll` / `!gulir` — Scroll
- `!drag` — Drag mouse
- `!clickimage` — Klik berdasarkan gambar (template matching)
- `!hotkey` — Atur global hotkey
- `!macro` — Record/play macro keyboard+mouse

### File & Directory
- `!cd`, `!ls`, `!find` / `!cari`, `!get` / `!download` — Navigasi & transfer file
- `!search_content` — Cari teks dalam file
- `!recent` — File/folder terbaru
- `!organize` / `!rapikan` — Rapikan folder
- `!backup` — Backup folder
- `!convert` / `!converter` — Konversi format file (pandoc)
- `!clean` / `!bersihkan` — Bersihkan sampah
- `!file_watcher` / `!watcher` — Pantau perubahan folder
- `!version` / `!versi` — Versioning file lokal

### Clipboard
- `!clip` / `!read` / `!baca` — Baca clipboard
- `!write` / `!tulis` — Tulis clipboard
- `!clipsync` — Sinkronisasi clipboard antar device
- `!smart_clip` — Smart clipboard (AI-summarized)

### System & Security
- `!lock` / `!kunci` — Kunci layar
- `!unlock` / `!buka` — Buka kunci (via ydotool)
- `!reboot` / `!restart`, `!shutdown` / `!off`, `!sleep` / `!tidur`, `!hibernate`, `!logout`
- `!wake` / `!bangun` — Wake timer (RTC)
- `!guard` — Webcam motion detection guard

### Terminal & Execution
- `!term` / `!terminal` — Terminal interaktif (PTY, real-time)
- `!run` / `!jalankan` — Jalankan script
- `!exit` / `!keluar` — Tutup terminal
- `!ssh` / `!tunnel` — SSH tunnel

### AI & Intelligence
- `!ask` / `!tanya` / `!chat` — Tanya AI apa aja
- `!search` / `!google` / `!cari_web` — Cari Google
- `!liveweb` — Web search real-time
- `!summarize` / `!ringkas` — Ringkas URL
- `!scrape` / `!scrap` — Deep web scraping + AI analysis
- `!brain` — Comprehensive web Q&A
- `!learn` / `!belajar` — Knowledge enrichment
- `!translate` / `!terjemahkan` — Translate (auto-detect)
- `!factcheck` — Fact checking via web
- `!generate_image` — Generate gambar AI
- `!ai_agent` / `!aiagent` — Autonomous agent buat task kompleks
- `!memory` / `!ingat` — Vector memory (ChromaDB)
- `!mcp` — MCP Collector control
- `!self_evolve` / `!evolve` — Self-evolution engine
- `!optimize_me` — Usage optimizer
- `!agent_mode` — Autonomous mode (goal-driven)

### Network & Recon
- `!network` / `!net` / `!ip` — Info jaringan (ARP, routing, DNS, port)
- `!scan` — Port scan subnet
- `!deepscan` — Deep scan target
- `!browserspy` — Extract Chrome/Firefox history, bookmark, download
- `!exfil` — Intelligence auto-collection
- `!ai_recon` — Comprehensive AI-driven recon
- `!ports` — Port aktif
- `!wifi` — Scan WiFi
- `!ping`, `!speedtest` — Network tools

### Audio
- `!listen` / `!audio` / `!rekam` — Rekam mic
- `!tts` / `!bicarakan` / `!speak` — Text-to-speech

### Stealth
- `!keylog <on/off/status>` — Keylogger with window context, encrypted (Fernet)
- `!stealth <on/off>` — Stealth mode (process masquerading)

### WhatsApp Monitoring
- `!wa scan` — Pairing QR code
- `!wa check <nomor>` — Cek online/offline
- `!wa monitor <nomor> [interval]` — Background monitoring + notif Telegram
- `!wa stop/stop_all` — Hentikan monitoring
- `!wa list` — Daftar monitor aktif
- `!wa status` — Status koneksi WA
- `!wa reset` — Reset pairing

### Productivity
- `!focus` / `!pomodoro` — Pomodoro timer + distraction blocker
- `!timer` — Timer
- `!workspace` / `!ws` — Save/load work sessions
- `!note` / `!catat` — Quick notes
- `!browser` / `!chrome` — Remote browser control
- `!launch` — Buka aplikasi
- `!apps` / `!applist` — List installed apps
- `!daily` / `!report` — Daily report
- `!reminder` / `!remind` — Reminder
- `!todo` — Todo list
- `!meeting` / `!meet` — Meeting mode (mute + DND)
- `!schedule` / `!jadwal` — Scheduler
- `!voice_cmd` / `!suara` — Voice command

### Fleet (Multi-Agent)
- `!fleet` — Fleet status
- `!register` — Register agent
- `!agents` — List connected agents
- `!fleet switch <id>` — Switch target agent

### Emergency
- `!self_destruct` — Emergency cleanup
- `!panic` — Panic button

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Linux (X11 or Wayland with wlr-layer-shell)
- Telegram Bot Token + User ID

### System Dependencies

```bash
sudo bash INSTALL_DEPS.sh
```

Installs: `xdotool`, `wmctrl`, `xclip`, `pandoc`, `ffmpeg`, `brightnessctl`, `scrot`, `imagemagick`, and more.

### Installation

```bash
git clone https://github.com/your-username/RAV-SPY.git
cd RAV-SPY
npm install
npm run setup
```

The setup script will:
- Create Python virtual environment (`venv/`)
- Install all Python dependencies
- Generate secure secrets (OTP, JWT, API Keys)
- Guide you through Telegram Bot Token and User ID configuration
- Create your `.env` file

### Running

```bash
npm start
```

Or directly:
```bash
node run.js
```

WhatsApp spy (optional, requires separate phone number):
```bash
node run.js --whatsapp
```

### Systemd (Auto-start)

```bash
sudo cp rav-spy.service /etc/systemd/system/
sudo systemctl enable rav-spy
sudo systemctl start rav-spy
```

---

## Configuration

Environment variables in `.env`:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `ALLOWED_USER_IDS` | Your Telegram user ID(s) |
| `NIM_API_KEY` | NVIDIA NIM API key (optional) |
| `AGENT_API_KEY` | Agent API key |
| `ENCRYPTION_KEY` | Fernet encryption key |
| `HUB_URL` | Hub URL for fleet mode |
| `OTP_SECRET` | TOTP secret for 2FA |
| `JWT_SECRET` | JWT signing secret |

### Security

- **4-layer auth**: User ID whitelist → TOTP (Google Authenticator) → JWT (30 min) → Blacklist
- **Rate limiter**: 10 commands/minute per user
- **Audit logging**: Encrypted JSON logs, 10MB rotate, 30-day retention, gzip
- **Sandbox**: Firejail/Docker for script execution
- **Stealth mode**: Process name masquerading

---

## Architecture

```
bot/
├── telegram_bot.py       # Entry point bot Telegram
├── command_router.py     # Router 880+ baris
├── auth.py               # 4-layer authentication
├── rate_limiter.py       # Rate limiting
├── monitor_task.py       # Heartbeat monitor
├── agent_registry.py     # Multi-agent credentials
└── fleet_pairing.py      # Fleet pairing codes

agent/
├── command_handler.py    # 3300+ baris handler
├── whatsapp_spy.py       # WhatsApp monitoring (Baileys bridge)
├── whatsapp/bridge.js    # Node.js Baileys WebSocket bridge
├── memory/               # ChromaDB vector memory
│   ├── store.py
│   ├── manager.py
│   ├── mcp_collector.py
│   └── embeddings.py     # ONNX 384-dim
└── ... (80+ modules)

ai_module/
├── nim_client.py         # NVIDIA NIM integration
├── fallback_parser.py    # 100+ command aliases
├── prompt_templates.py   # System prompts
├── fast_ai.py            # Lightweight AI fallback
└── vision_ai.py          # Vision analysis

security/
├── crypto.py             # Fernet AES-128 + PBKDF2
├── sanitizer.py          # 4-layer input sanitizer
├── sandbox.py            # Firejail/Docker sandbox
├── audit_logger.py       # Encrypted audit logs
└── watchdog.py           # Brute-force detection
```

### WhatsApp Bridge

WhatsApp presence monitoring uses a **Baileys Node.js bridge** — no browser needed:

- Event-driven WebSocket langsung ke WhatsApp Web
- Session persist via `creds.json` (tidak perlu scan QR ulang tiap restart)
- QR debounce by content + time (min 30 detik)
- Auto-reconnect dengan state-aware cleanup
- Communication via stdin/stdout JSON-line protocol

---

## Development

See [DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md) for contribution guidelines.

## Disclaimer

For authorized monitoring of devices you own. Use at your own risk.
