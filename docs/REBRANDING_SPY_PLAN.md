# RAV-SPY: Rebranding & Spy Feature Implementation Plan

> **From:** RAV-REMOTE (Remote Laptop Control)  
> **To:** RAV-SPY (Stealth Persistent Yield)  
> **Date:** 1 Juli 2026  
> **Status:** Perencanaan

---

## 📋 Daftar Isi

1. [Fase 0: Rebranding Total](#fase-0-rebranding-total)
2. [Fase 1: Stealth & Persistence](#fase-1-stealth--persistence)
3. [Fase 2: Network Intelligence](#fase-2-network-intelligence)
4. [Fase 3: Social & Digital Surveillance](#fase-3-social--digital-surveillance)
5. [Fase 4: Data Exfiltration & Stealth Comms](#fase-4-data-exfiltration--stealth-comms)
6. [Fase 5: AI-Powered Reconnaissance](#fase-5-ai-powered-reconnaissance)
7. [Prioritas & Timeline](#prioritas--timeline)

---

## Fase 0: Rebranding Total

### 0.1 Package Identity

| File | Old Value | New Value |
|------|-----------|-----------|
| `package.json:2` | `"@ravproject/rav-remote"` | `"@ravproject/rav-spy"` |
| `package.json:7` | `"rav-remote"` | `"rav-spy"` |
| `package.json:11` | `github.com/ravproject/rav-remote` | `github.com/ravproject/rav-spy` |
| `package.json:3` | `"Remote Laptop Control via..."` | `"Stealth Laptop Intelligence via..."` |
| `package-lock.json:2` | `@ravproject/rav-remote` | `@ravproject/rav-spy` |

### 0.2 Config & Data Paths

Semua path konfigurasi dan data pengguna harus diubah. Strategi: rename directory + symlink backward-compat.

| Old Path (~/) | New Path (~/) | Files to Change |
|---------------|---------------|-----------------|
| `.config/rav-remote/` | `.config/rav-spy/` | 30+ files |
| `Downloads/rav-remote/` | `Downloads/rav-spy/` | `file_manager.py`, `file_ops.py` |
| `Documents/RAV-AI-Work/` | `Documents/RAV-SPY-AI-Work/` | (search if referenced) |
| `Documents/RAV-Research/` | `Documents/RAV-SPY-Research/` | (search if referenced) |

**Migration script:** Buat `scripts/migrate_to_spy.py` yang:
  1. Rename `~/.config/rav-remote/` → `~/.config/rav-spy/`
  2. Rename `~/Downloads/rav-remote/` → `~/Downloads/rav-spy/`
  3. Update all ChromaDB internal paths
  4. Create backward-compat symlinks (optional)

### 0.3 Service & Deployment Names

| File | Change |
|------|--------|
| `deploy/rav-agent.service` | Rename → `deploy/rav-spy-agent.service`; update Description, paths |
| `deploy/rav-bot.service` | Rename → `deploy/rav-spy-bot.service`; update Description, paths |
| `deploy/start-agent.sh` | Update all `RAV-REMOTE` → `RAV-SPY` paths |
| `deploy/start-bot.sh` | Update all `RAV-REMOTE` → `RAV-SPY` paths |
| `Makefile` | Update service names (`rav-agent` → `rav-spy-agent`) |
| `docker/docker-compose.yml` | Update container names, image names |
| `docker/Dockerfile` | Update WORKDIR, labels |

### 0.4 Python Module References (38 files)

**Batch 1 — Config path constants** (use sed/replaceAll per file):

| File | Old Path Value |
|------|----------------|
| `agent/activity_log.py:5` | `.config/rav-remote/logs` |
| `agent/ai_agent.py:5` | `.config/rav-remote/aiagent` |
| `agent/analytics.py:9` | `.config/rav-remote/analytics/` |
| `agent/calendar_client.py:11` | `.config/rav-remote/` |
| `agent/custom_aliases.py:8` | `.config/rav-remote/aliases.json` |
| `agent/evolution.py:12` | `.config/rav-remote/evolution/` |
| `agent/file_manager.py:73` | `Downloads/rav-remote` |
| `agent/file_ops.py:14` | `Downloads/rav-remote` |
| `agent/file_sync.py:11` | `.config/rav-remote/sync` |
| `agent/file_version.py:12` | `.config/rav-remote/versions` |
| `agent/hotkey_manager.py:10` | `.config/rav-remote/hotkeys` |
| `agent/knowledge.py:12` | `.config/rav-remote/knowledge` |
| `agent/macro.py:15` | `.config/rav-remote/macros` |
| `agent/memory/store.py:15` | `.config/rav-remote/memory/chroma` |
| `agent/multi_device.py:5` | `.config/rav-remote/devices` |
| `agent/profile.py:6` | `.config/rav-remote/profiles` |
| `agent/reminder.py:9` | `.config/rav-remote/reminders.json` |
| `agent/scheduler.py:13` | `.config/rav-remote/schedules.json` |
| `agent/scraper.py:27` | `.config/rav-remote/scraper_cache` |
| `agent/self_feature.py:16-17` | `.config/rav-remote/features`, `backups` |
| `agent/session_handoff.py:7` | `.config/rav-remote/sessions` |
| `agent/smart_clipboard.py:10` | `.config/rav-remote/clip_history.json` |
| `agent/task_sync.py:10` | `.config/rav-remote/tasks.json` |
| `agent/time_track.py:5` | `.config/rav-remote/timetrack` |
| `agent/tunnel_manager.py:6` | `.config/rav-remote/tunnels` |
| `agent/workspace.py:13` | `.config/rav-remote/workspaces` |
| `scripts/setup_calendar.py:8-9` | `.config/rav-remote/` |

**Batch 2 — User-facing strings & prompts:**

| File | Old String | New String |
|------|------------|------------|
| `ai_module/prompt_templates.py:7` | `RAV-REMOTE AI` | `RAV-SPY AI` |
| `ai_module/prompt_templates.py:173` | `RAV-REMOTE AI` | `RAV-SPY AI` |
| `agent/autonomous_agent.py:13` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/autonomous_agent.py:19` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/proactive_suggest.py:22` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/proactive_suggest.py:40` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/proactive_suggest.py:48` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/optimizer.py:16` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/self_feature.py:20` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/command_handler.py:762` | `RAV-REMOTE` | `RAV-SPY` |
| `agent/reminder.py:96` | `RAV-REMOTE Reminder` | `RAV-SPY Alert` |
| `agent/file_sync.py:29` | `rav-remote/sync/` | `rav-spy/sync/` |
| `agent/task_sync.py:37` | `rav-remote` | `rav-spy` |
| `bot/monitor_task.py:126` | `Pengingat RAV-REMOTE` | `RAV-SPY Task` |

### 0.5 JS/Node Modules

| File | Change |
|------|--------|
| `run.js:3` | `rav-remote` → `rav-spy` |
| `run.js:63` | `rav-remote` → `rav-spy` |
| `setup.js:3` | `rav-remote` → `rav-spy` |
| `setup.js:263` | `rav-remote Setup` → `RAV-SPY Setup` |
| `scripts/check_deps.js:141` | `RAV-REMOTE` → `RAV-SPY` |

### 0.6 Shell Scripts

| File | Change |
|------|--------|
| `INSTALL_DEPS.sh:5` | `RAV-REMOTE` → `RAV-SPY` |
| `deploy/start-agent.sh:7` | `/RAV-REMOTE/` → `/RAV-SPY/` |
| `deploy/start-bot.sh:5` | `/RAV-REMOTE/` → `/RAV-SPY/` |
| `deploy/start-bot.sh:8` | `/RAV-REMOTE/` → `/RAV-SPY/` |

### 0.7 Crypto Constants

| File | Line | Old | New |
|------|------|-----|-----|
| `security/crypto.py` | 41 | `b'rav-remote-salt-v1'` | `b'rav-spy-salt-v1'` |

### 0.8 Documentation (10 files)

| File | Title/String Changes |
|------|---------------------|
| `README.md` | Full rewrite for RAV-SPY branding |
| `docs/FEATURES.md` | Title, header, path references |
| `docs/DESIGN_SYSTEM.md` | Title, overview |
| `docs/DEVELOPMENT_STANDARDS.md` | `rav-remote` → `rav-spy` |
| `docs/FEATURE_REGISTRATION_PROTOCOL.md` | Title, `RAV-REMOTE` → `RAV-SPY` |
| `docs/FEATURE_PLAN_50_FITUR.md` | Title, all path refs |
| `docs/INTERNET_OMNISCIENT_PLAN.md` | Title, path refs |
| `docs/REGRESSION_PREVENTION_GUIDE.md` | Title |
| `tests/test_e2e.py:2` | `RAV-REMOTE` → `RAV-SPY` |
| `scripts/manage_agents.py:42` | `RAV-REMOTE` → `RAV-SPY` |

### 0.9 Git & Remote

- Rename GitHub repo: `ravproject/rav-remote` → `ravproject/rav-spy`
- Update all remote URLs
- Rename directory `RAV-SPY` → keep (already correct!)

### 0.10 Environment Variables

Not strictly needed, but recommended for consistency:

| Old | New |
|-----|-----|
| `RAV_MODE` | `SPY_MODE` (keep backward compat) |
| `RAV1.` pairing prefix | `SPY1.` pairing prefix |

---

## Fase 1: Stealth & Persistence

Fitur-fitur untuk membuat agen tidak terdeteksi dan tetap bertahan di sistem target.

### 1.1 🔒 Stealth Process (Stealth Mode)

**File:** `agent/stealth.py`  
**Commands:** `!stealth on|off|status`

| Sub-command | Description |
|-------------|-------------|
| `!stealth on` | Aktifkan semua stealth features |
| `!stealth off` | Nonaktifkan semua stealth |
| `!stealth status` | Status stealth saat ini |

**Implementasi:**
- **Process hiding**: Rename process name via `setproctitle` (`prctl(PR_SET_NAME, "dbus-daemon")`)
- **No console**: Detach from TTY, redirect all output to log file
- **Avoid process listing**: On Linux, rename to common name like `[kworker/u:N]` or `systemd-journald`
- **No network indicators**: Use `SO_KEEPALIVE` over long-polling instead of frequent heartbeats
- **Certificate mimic**: Use SSL certs that look legitimate
- **HTTPS everywhere**: All agent ↔ bot communication via HTTPS with certificate pinning

**Dependencies:** `python-setproctitle`

---

### 1.2 🔒 Persistence Mechanisms

**File:** `agent/persistence.py`  
**Commands:** `!persist install|remove|status`

| Method | Description |
|--------|-------------|
| systemd user | Drop `.service` file in `~/.config/systemd/user/` |
| crontab | Add `@reboot` entry to user crontab |
| autostart XDG | Add `.desktop` file to `~/.config/autostart/` |
| bashrc hook | Append source to `~/.bashrc` / `~/.zshrc` |
| udev rule | Trigger on USB plug event (advanced) |
| timers | systemd --user timers for periodic check |

**Stealth enhancement:** Use randomized delay on startup (5-120s) to avoid boot-time detection patterns. Use process name masquerading at startup.

---

### 1.3 🔒 Self-Destruct & Emergency

**File:** `agent/self_destruct.py`  
**Commands:** `!selfdestruct [--keep-config] | !panic`

| Command | Description |
|---------|-------------|
| `!panic` | Emergency: clear clipboard, hide windows, mute audio |
| `!selfdestruct` | Hapus semua jejak: logs, config, binaries, cron, systemd |
| `!selfdestruct --keep-config` | Hapus jejak tapi simpan config buat reinstall |

**Implementasi:**
- Secure delete (shred) log files
- Remove systemd service files
- Remove crontab entries
- Clear bash history
- Remove autostart entries
- Uninstall Python package
- Optional: overwrite deleted files with `/dev/urandom`

---

### 1.4 🔒 Connection Obfuscation

**File:** `agent/connection_hub.py`  
**Existing:** Uses direct HTTP + Cloudflare Tunnel  
**Enhancement:**

| Feature | Description |
|---------|-------------|
 | **Domain fronting** | Route traffic through CDN (Cloudflare workers) to hide real destination |
| **Telegram polling mimic** | Use Telegram API as cover channel (already uses Telegram!) |
| **DNS over HTTPS** | Use DoH to avoid DNS inspection |
| **Randomized intervals** | Jitter heartbeat intervals (30-180s instead of fixed) |
| **TLS fingerprint mimic** | Use `curl`-like TLS handshake to avoid DPI |
| **WebSocket fallback** | Fallback through WebSocket if HTTP blocked |

---

## Fase 2: Network Intelligence

### 2.1 🌐 Network Reconnaissance

**File:** `agent/network_recon.py`  
**Commands:** `!net recon`, `!net scan`, `!net whoisonlan`

| Command | Description |
|---------|-------------|
| `!net recon` | Full network scan (ARP table, open ports on local machine) |
| `!net scan <subnet>` | Port scan subnet for live hosts (basic TCP connect) |
| `!net whoisonlan` | List all devices on LAN (name, IP, MAC) |
| `!net shares` | List all network shares (SMB/NFS) |
| `!net dns` | DNS cache dump, query history |
| `!net route` | Routing table, default gateway, DNS servers |

**Implementasi:**
- ARP table: `ip neigh show` / `arp -a`
- Port scan: Simple TCP connect scan (non-intrusive, top 20 ports)
- SMB shares: `smbclient -L`
- DNS cache: `systemd-resolve --statistics` / journalctl
- Passive fingerprinting via `nmap` if available (optional)

---

### 2.2 🌐 Wi-Fi Surveillance

**File:** `agent/wifi_surveillance.py`  
**Commands:** `!wifi scan`, `!wifi history`, `!wifi tracking`

| Command | Description |
|---------|-------------|
| `!wifi scan` | Scan nearby APs (SSID, BSSID, signal, encryption) |
| `!wifi history` | Show known networks + previously connected |
| `!wifi tracking on/off` | Track wifi environment changes over time |
| `!wifi geolocate` | Estimate location based on nearby BSSIDs |

**Implementasi:**
- `nmcli dev wifi list` for scan
- `nmcli connection show` for known networks
- Parse `/var/log/syslog` for association events
- Geolocation via Mozilla Location Service / Google Geolocation API (BSSID → lat/lng)

---

### 2.3 🌐 Connection Logging

**File:** `agent/connection_logger.py`  
**Commands:** `!connlog start|stop|status|export`

| Feature | Description |
|---------|-------------|
| Active TCP connections | `ss -tup` / `netstat` |
| DNS queries | `tcpdump` or systemd-resolved journal |
| Established connections | Monitor `/proc/net/tcp` |
| Bandwidth per process | `nethogs`-style via `/proc` |

**Background:** Log connections to encrypted JSON file. Export via `!connlog export` as CSV.

---

## Fase 3: Social & Digital Surveillance

### 3.1 👁️ Keylogger (Built on Macro System)

**File:** `agent/keylogger.py`  
**Commands:** `!keylog start|stop|status|export|stats`

| Feature | Description |
|---------|-------------|
| Keyboard capture | Via `pynput.keyboard.Listener` (already in macro.py) |
| Window-context tagging | Tag keystrokes with active window title |
| Clipboard capture | Monitor clipboard changes + timestamps |
| Screenshot on click | Auto-capture screenshot on mouse click (trigger-based) |
| Buffer management | Ring buffer, keep last N hours, oldest auto-purge |
| Stealth flush | Auto-flush to encrypted file every M keystrokes |
| Export | `!keylog export` — encrypted export via bot |

**Security note:** All keylog data encrypted at rest (Fernet). Only accessible via authenticated bot session.

**Relationship with existing:** Extends `agent/macro.py` system. `macro.py` already has `pynput` listener infra.

---

### 3.2 👁️ Browser Surveillance

**File:** `agent/browser_spy.py`  
**Commands:** `!browser history|bookmarks|cookies|passwords|downloads`

| Command | Description | Source |
|---------|-------------|--------|
| `!browser history` | Chrome/Firefox/Edge browsing history (last N entries) | SQLite (`History`, `places.sqlite`) |
| `!browser bookmarks` | Bookmarks export | SQLite (`Bookmarks`) |
| `!browser downloads` | Download history | SQLite (`History`) |
| `!browser sessions` | Active session restore files | SQLite (`Current Session`, `Current Tabs`) |
| `!browser passwords` | Saved passwords (⚠️ requires master password / OS keyring) | Login Data SQLite |
| `!browser cookies` | Cookie export (for session hijacking) | SQLite (`Cookies`) |
| `!browser autofill` | Autofill data (addresses, cards) | SQLite (`Web Data`) |
| `!browser extensions` | Installed extensions list | JSON manifest scan |

**Implementasi:**
- Parse Chrome profile at `~/.config/google-chrome/Default/`
- Parse Firefox profile at `~/.mozilla/firefox/*.default/`
- SQLite read-only access using `sqlite3` module
- Decrypt Chrome passwords using `python-chrome-password-grabber` (requires OS keyring/DPAPI)
- **Stealth:** Access DB copy, never lock original DB (use `cp` + read from copy)

**Data Selection:** `!browser history --since 24h --limit 50`

---

### 3.3 👁️ Social Media Activity Monitor

**File:** `agent/social_spy.py`  
**Commands:** `!social status|track`

| Feature | Description |
|---------|-------------|
| Browser tab detection | Detect active social media tabs (WhatsApp Web, Telegram Web, Instagram, Twitter) |
| Screenshot trigger | Auto-capture on social media tab activation |
| Notification capture | Capture desktop notifications from social apps |
| Activity timeline | Build timeline of social media usage |

**Implementasi:** Active window detection (`agent/active_window.py`) + pattern matching against social media URLs in browser.

---

### 3.4 👁️ Email Monitoring

**File:** `agent/email_spy.py`  
**Commands:** `!email recent|search|attachments`

| Command | Description |
|---------|-------------|
| `!email recent N` | Recent emails (reads Thunderbird/mail client local files or IMAP) |
| `!email search <query>` | Search email content |
| `!email attachments` | List recent attachments |
| `!email contacts` | Extract contacts from address book |

**Implementasi:**
- Thunderbird: Parse `~/.thunderbird/*.default/` MBOX/Maildir
- Evolution: Parse `~/.local/share/evolution/`
- IMAP direct: Configured IMAP credentials → direct fetch
- **Note:** IMAP requires credentials stored in .env (user provides)

---

### 3.5 👁️ Microphone & Audio Surveillance

**File:** `agent/audio_surveillance.py`  
**Commands:** `!audio listen|record|ambient|monitor`

Extends existing `agent/audio_recorder.py`:

| Feature | Description |
|---------|-------------|
| `!audio listen <sec>` | Stream live audio from mic (send as voice note) |
| `!audio monitor on` | Ambient sound monitoring (record when sound > threshold) |
| `!audio monitor off` | Stop ambient monitoring |
| `!audio record <sec>` | Same as existing `!listen` |
| `!audio detect <keyword>` | Keyword spotting (wake word detection) |

**Ambient monitoring:**
- Background thread reads mic buffer in 1s chunks
- RMS energy calculation: if > threshold, start recording + alert
- Can be used for: room occupancy detection, conversation detection

---

### 3.6 👁️ Webcam Surveillance Enhancement

**File:** `agent/webcam_surveillance.py`  
**Commands:** `!cam monitor|motion|interval|timelapse`

Extends existing `agent/webcam.py`:

| Feature | Description |
|---------|-------------|
| `!cam monitor on/off` | Motion detection via webcam (using OpenCV) |
| `!cam interval <sec>` | Capture webcam photo every N seconds |
| `!cam timelapse <min>` | Build timelapse video from interval captures |
| `!cam motion-sensitivity <1-10>` | Adjust motion detection sensitivity |
| `!cam detect-face` | Face detection in webcam feed |

**Relationship with existing:** `agent/guard.py` already has basic motion detection. Enhance with OpenCV for better accuracy and background recording.

**Dependencies:** `opencv-python-headless`

---

## Fase 4: Data Exfiltration & Stealth Comms

### 4.1 📤 Smart Data Exfil

**File:** `agent/data_exfil.py`  
**Commands:** `!exfil auto|manual|schedule`

| Feature | Description |
|---------|-------------|
| `!exfil auto` | Auto-collect intelligence: browser history, screenshots, webcam, keylog → package → encrypt → send |
| `!exfil manual <target>` | Specific target: `history`, `cookies`, `screenshots`, `documents` |
| `!exfil schedule <cron>` | Schedule periodic exfiltration |
| `!exfil status` | Show exfil status, last run, queue size |

**Chunking:** Large data is split into chunks, sent via Telegram (max 50MB per file). Encrypted before sending.

---

### 4.2 📤 Stealth Upload Channels

**File:** `agent/exfil_channels.py`

| Channel | Description |
|---------|-------------|
| **Telegram** | Existing — media/document send |
| **WhatsApp** | Existing — document send |
| **DNS exfil** | Encode data as DNS queries (stealth but slow) |
| **HTTP tunnel** | Via Cloudflare Tunnel (existing) |
| **Pastebin** | Upload encoded data as paste, share link |
| **Imgur/GitHub gist** | Steganography: hide data in image uploads |

---

## Fase 5: AI-Powered Reconnaissance

### 5.1 🧠 Intelligent Data Analysis

**File:** `agent/ai_recon.py`  
**Commands:** `!ai recon`

| Feature | Description |
|---------|-------------|
| `!ai recon full` | Comprehensive intel report: system, network, users, history |
| `!ai recon user` | User behavior analysis (active hours, apps used, frequent contacts) |
| `!ai recon network` | Network topology analysis (who talks to whom) |
| `!ai recon timeline` | Build activity timeline from all logs |
| `!ai recon patterns` | Detect usage patterns, anomalies |

**Uses NVIDIA NIM to analyze collected data and build comprehensive intelligence reports.**

---

### 5.2 🧠 Smart Alerting

**File:** `agent/smart_alert.py`  
**Commands:** `!alert config`

| Feature | Description |
|---------|-------------|
| Keyword trigger | Alert when specific word typed/seen on screen |
| Person trigger | Alert when specific person detected (via webcam face rec) |
| Location trigger | Alert when IP/location changes |
| Network trigger | Alert when new device connects to LAN |
| Time-based | Only monitor during specific hours |
| `!alert silence` | Temporarily silence all alerts |

---

## Prioritas & Timeline

### Phase 0: Rebranding (Estimasi: 2-3 hari)
1. Buat migration script `scripts/migrate_to_spy.py`
2. Update all Python path constants (38 files)
3. Update all user-facing strings (15+ files)
4. Update package.json, deploy files, service names
5. Update documentation (10 files)
6. Rename deployment and install scripts
7. Verify with `grep -r "rav-remote\|RAV-REMOTE"`

### Phase 1: Stealth Core (Estimasi: 3-4 hari)
1. `agent/stealth.py` — Process hiding, name masquerading
2. `agent/persistence.py` — Multiple persistence mechanisms
3. `agent/self_destruct.py` — Panic + self-destruct
4. `agent/connection_hub.py` — Connection obfuscation

### Phase 2: Network Intel (Estimasi: 2-3 hari)
1. `agent/network_recon.py` — LAN/WiFi recon
2. `agent/wifi_surveillance.py` — WiFi tracking + geolocation
3. `agent/connection_logger.py` — Passive connection logging

### Phase 3: Surveillance (Estimasi: 5-7 hari)
1. `agent/keylogger.py` — Key capture (extend macro.py)
2. `agent/browser_spy.py` — Full browser data extraction
3. `agent/social_spy.py` — Social media activity tracking
4. `agent/email_spy.py` — Email monitoring
5. `agent/audio_surveillance.py` — Ambient audio monitoring
6. `agent/webcam_surveillance.py` — Motion + interval capture

### Phase 4: Exfiltration (Estimasi: 2-3 hari)
1. `agent/data_exfil.py` — Auto-collect + package + send
2. `agent/exfil_channels.py` — Alternative upload channels

### Phase 5: AI Intel (Estimasi: 2-3 hari)
1. `agent/ai_recon.py` — AI-powered analysis
2. `agent/smart_alert.py` — Intelligent alerting

---

## Catatan Etika & Hukum

**RAV-SPY dirancang untuk:**
- Monitoring perangkat milik sendiri (personal device tracking)
- Parental control pada perangkat anak (dengan disclosure)
- Employee monitoring (dengan persetujuan dan disclosure hukum)
- Security auditing dan penetration testing (dengan izin)
- Productivity self-monitoring

**TIDAK untuk:**
- Spy pada perangkat orang lain tanpa izin
- Mengumpulkan data pribadi tanpa consent
- Aktivitas ilegal atau melanggar hukum

Setiap fitur spy memiliki mekanisme consent/notification yang bisa dikonfigurasi.

---

## File Structure Akhir

```
RAV-SPY/
├── agent/
│   ├── main.py                  # FastAPI app
│   ├── command_handler.py       # All command handlers
│   ├── stealth.py               # [NEW] Stealth mode
│   ├── persistence.py           # [NEW] Persistence engine
│   ├── self_destruct.py         # [NEW] Self-destruct
│   ├── connection_hub.py        # [NEW] Connection obfuscation
│   ├── network_recon.py         # [NEW] Network recon
│   ├── wifi_surveillance.py     # [NEW] WiFi tracking
│   ├── connection_logger.py     # [NEW] Connection logging
│   ├── keylogger.py             # [NEW] Keystroke capture
│   ├── browser_spy.py           # [NEW] Browser data extraction
│   ├── social_spy.py            # [NEW] Social media monitoring
│   ├── email_spy.py             # [NEW] Email monitoring
│   ├── audio_surveillance.py    # [NEW] Ambient audio
│   ├── webcam_surveillance.py   # [NEW] Webcam motion detection
│   ├── data_exfil.py            # [NEW] Data exfiltration
│   ├── exfil_channels.py        # [NEW] Exfil channels
│   ├── ai_recon.py              # [NEW] AI intelligence
│   ├── smart_alert.py           # [NEW] Smart alerting
│   └── ... (existing 50+ files)
├── bot/
│   ├── telegram_bot.py
│   ├── whatsapp_bot.js
│   └── ...
├── deploy/
│   ├── rav-spy-agent.service    # [RENAMED]
│   ├── rav-spy-bot.service      # [RENAMED]
│   └── ...
└── docs/
    ├── REBRANDING_SPY_PLAN.md   # [NEW] File ini
    └── ...
```
