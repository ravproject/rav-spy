# 📘 Standar Pengembangan & Rekayasa Perangkat Lunak (Enterprise Engineering Standards)

Dokumen ini adalah **"Kitab Suci"** arsitektur dan panduan rekayasa untuk proyek **rav-spy**. 
Karena aplikasi ini bertindak sebagai *Remote Access Trojan (RAT)* yang dilegalkan (memberikan akses kontrol penuh ke Host OS), standar pengembangannya harus memenuhi kualifikasi **Enterprise/Industry Standard**.

Setiap *Engineer* (Manusia maupun AI Agent) yang berkontribusi pada proyek ini WAJIB mematuhi panduan ini tanpa terkecuali. Mengabaikan dokumen ini sama dengan memasukkan celah keamanan yang fatal.

---

## 🧠 1. Pola Pikir Arsitek (The Architect's Mindset)

Dalam membangun sistem berskala besar, kode yang berfungsi saja tidak cukup. Kode harus dapat dipelihara (*Maintainable*), aman (*Secure*), dan terukur (*Scalable*).

1.  **Zero Trust Architecture:** Asumsikan setiap input adalah senjata. Tidak ada asumsi bahwa "hanya user yang valid yang akan mengirim ini." *Defense in Depth* harus diterapkan di setiap lapisan (Bot -> Router -> Agent -> OS).
2.  **Graceful Degradation & Resiliency:** Sistem eksternal (API NVIDIA, Telegram, Kamera Laptop, Modul OS) **pasti** akan gagal suatu saat. Desain sistem Anda agar tidak pernah *Crash*. Tangkap *exception*, gunakan mekanisme *fallback*, dan beri tahu user dengan status yang jelas.
3.  **Concurrency First (Asynchronous by Default):** Telegram bot beroperasi secara *real-time*. Semua operasi I/O (Jaringan, Baca/Tulis File, Pemrosesan Video) **HARUS** bersifat Non-Blocking (menggunakan `asyncio`, `aiofiles`, atau `Threading/Background Tasks`). Jangan pernah memblokir *Event Loop* utama.
4.  **Idempotency:** Rancang endpoint API (`agent/main.py`) sedemikian rupa sehingga jika suatu permintaan (*request*) dieksekusi berkali-kali secara bersamaan, efek sampingnya tetap sama dan tidak merusak *state* sistem.

---

## 🏗️ 2. Standar Arsitektur (Architectural Patterns)

### A. Separation of Concerns (Pemisahan Perhatian)
Jangan mencampuradukkan logika antarmuka (Bot) dengan logika bisnis (Agent/OS).
*   **Layer Bot (`bot/`):** Hanya bertanggung jawab untuk komunikasi dengan API (Telegram/WhatsApp), memvalidasi autentikasi awal, dan meneruskan perintah.
*   **Layer Middleware (`security/`, `ai_module/`):** Bertugas menyaring input, mentranskripsi teks, dan melakukan validasi keamanan independen.
*   **Layer Agent (`agent/`):** Berinteraksi langsung dengan OS. Tidak boleh peduli darimana asal perintah (apakah dari Telegram atau Terminal), ia hanya merespons HTTP request yang divalidasi.

### B. Dependency Injection & Interfaces
*   Hindari *Hardcoding* dependensi eksternal di dalam fungsi inti.
*   Gunakan *Abstract Base Classes* (ABC) jika akan menambahkan dukungan platform baru (Misal: interface dasar `SystemMonitor` yang kemudian diimplementasikan oleh `LinuxMonitor` dan `WindowsMonitor`).

---

## 🛡️ 3. Pedoman Keamanan Ketat (Strict Security Guidelines)

Setiap *Pull Request* (PR) yang berhubungan dengan input atau eksekusi perintah WAJIB memenuhi kriteria ini:

1.  **Sanitasi Berlapis (Layered Sanitization):** 
    *   Setiap input teks (termasuk hasil dari AI/Speech-to-Text) harus melewati `security/sanitizer.py`.
    *   Wajib menolak karakter shell (*Pipes `|`, Semicolons `;`, Backticks `` ` ``*).
2.  **Pencegahan Path Traversal:**
    *   Modul File Manager DILARANG menggunakan manipulasi string manual untuk *path file*. Wajib menggunakan objek `pathlib.Path` dan memeriksa `Path.resolve().is_relative_to(...)`.
3.  **Resource Limiting (Pembatasan Eksekusi):**
    *   **Max File Size:** Wajib ada batas atas untuk unggah/unduh (Mencegah *Disk Exhaustion Attack*).
    *   **Timeouts:** Semua subprocess atau panggilan API (*httpx*) WAJIB memiliki argumen `timeout`.
    *   **Zombie Reaper:** Proses terminal atau skrip yang berjalan lama harus memiliki daemon yang membersihkannya jika *idle* (seperti `_cleanup_loop`).
4.  **Sandboxing Mandatori:** Perintah kustom dari user (`!run`) WAJIB dieksekusi dalam environment terbatas (Firejail/Docker). Dilarang keras mengeksekusi *arbitrary code* secara langsung menggunakan `os.system` atau `subprocess.Popen(shell=True)`.

---

## 🧪 4. Standar Kualitas & Pengujian (QA & Testing)

Kode yang tidak diuji adalah kode warisan (*Legacy Code*) sejak hari pertama ditulis.

1.  **Unit Testing (Minimal 80% Coverage):** 
    *   Setiap fungsi baru harus memiliki pengujian terisolasi di `tests/`.
    *   Uji skenario normal (Happy Path) DAN skenario kegagalan (Unhappy Path / Edge Cases).
2.  **End-to-End (E2E) Testing:** 
    *   Alur penting (Login, Buka Terminal, Upload) harus diuji dari sudut pandang interaksi bot Telegram.
3.  **Mandatory Mocking:**
    *   Test DILARANG memanggil internet sungguhan, menyalakan kamera, atau mengubah file sistem yang sebenarnya di luar `/tmp`. Gunakan `unittest.mock.patch` (seperti `AsyncMock` untuk *httpx* dan *bot API*).
4.  **Static Analysis & Linting (Future CI/CD):**
    *   Pastikan kode mematuhi standar PEP-8 (Python).
    *   Jangan abaikan peringatan *Linter* tanpa alasan (komentar) yang jelas.

---

## 📈 5. Observabilitas & Kesiapan Operasional (Observability & Ops Readiness)

Aplikasi besar harus bisa "berbicara" ketika ia sedang sakit.

1.  **Structured Logging:** 
    *   DILARANG KERAS MENGGUNAKAN `print()`.
    *   Gunakan `loguru` (contoh: `logger.info`, `logger.error`, `logger.debug`).
    *   Sertakan konteks penting dalam log (Contoh BUKAN: `"Error terjadi"`, TAPI: `"Error reading file {filename} for user {user_id}: {exception}"`).
2.  **Audit Trail (Jejak Audit):**
    *   Semua aksi yang memodifikasi state sistem (Menghapus file, Membuka Terminal, Menjalankan skrip) WAJIB memanggil `auditor.log_event()`. Jejak ini penting untuk investigasi forensik jika sistem diretas.
3.  **State Synchronization:** 
    *   Hindari menyimpan *state* yang kompleks di memori lokal (RAM) tanpa sinkronisasi, karena jika *container*/aplikasi di-restart, *state* akan hilang. Simpan *state* krusial ke sistem file persisten (seperti `tg_sessions.json`).

---

## 🔄 6. Alur Kontribusi & Review Kode (Contribution Flow)

Jika Anda akan memodifikasi fitur inti (misalnya oleh Developer Baru atau AI Agent):

1.  **Pahami Dampaknya (Blast Radius):** Pikirkan modul apa saja yang terpengaruh. Apakah penambahan fitur bot akan merusak *rate limiter*? Apakah penambahan API mengubah format respons E2E Test?
2.  **Write Tests First (TDD disarankan):** Tulis bagaimana Anda akan menguji kegagalan fitur ini sebelum Anda menulis implementasi fiturnya.
3.  **Refactor Terisolasi:** Jangan mengubah 10 file sekaligus jika tidak perlu. Perubahan harus spesifik dan fokus pada satu tujuan (Surgical Update).
4.  **Verify & Run All Tests:**
    ```bash
    python3 -m unittest discover tests
    ```
    Jika ada 1 tes yang gagal, perbaiki MOCK atau kodenya. **DILARANG** menghapus tes lama hanya untuk meloloskan kode baru Anda.

> *"Kode Anda akan dibaca 100 kali lebih sering daripada ditulis. Tulislah untuk mereka yang membacanya."*
