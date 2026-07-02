# 🛡️ Panduan Pencegahan Regresi & Integritas Fitur (RAV-SPY)

Dokumen ini berfungsi sebagai panduan standar untuk memastikan setiap penambahan fitur baru atau modifikasi kode **tidak merusak fitur yang sudah ada** (Zero Regression Policy).

---

## 1. 🧪 Mandatori Pengujian Otomatis (Automated Testing)
Setiap kali ada perubahan kode sekecil apa pun:
1. **Wajib menjalankan test suite** menggunakan virtual environment:
   ```bash
   ./venv/bin/python3 -m unittest discover tests
   ```
2. **Kriteria Kelulusan:** Semua test harus berstatus `OK` (45+ test pass).
3. **Mencegah Kerusakan Mock:** Jika Anda mengubah response format atau behavior handler, pastikan mock yang ada di `tests/test_commands.py` dan `tests/test_e2e.py` disesuaikan tanpa menghapus test case yang sudah ada.

---

## 2. 🧱 Prinsip Isolasi & Mocking Terbimbing
Untuk mencegah pengujian merusak sistem host atau bergantung pada kondisi eksternal:
* **Dilarang memanggil OS API secara langsung dalam test:** Gunakan `unittest.mock.patch` untuk mensimulasikan `subprocess.run`, `subprocess.Popen`, atau library seperti `pyperclip`, `webbrowser`, dan `psutil`.
* **Dilarang memanggil API eksternal secara nyata:** Pastikan panggilan ke NVIDIA NIM API dibungkus dengan mock.
* **Isolasi File System:** Jangan membaca/menulis file asli di luar direktori `/tmp` saat menjalankan test.

---

## 3. 🚦 Protokol Kompatibilitas API (API Contract Integrity)
FastAPI Agent (`agent/main.py`) bertindak sebagai server dan Telegram/WhatsApp bot bertindak sebagai klien.
* **Jangan mengubah format JSON response yang sudah ada** secara sembarangan. 
  * Response tipe teks harus memiliki struktur: `{"type": "text", "content": "..."}`
  * Response tipe media harus memiliki struktur: `{"type": "image" | "video" | "document", "content": "..."}` (content dapat berupa string base64 atau dictionary berisi data base64, filename, dan mimetype).
* Jika Anda menambahkan field baru, pastikan field tersebut bersifat opsional (`Optional[...]` dengan default value) agar tidak memicu error `ValidationError` pada versi bot yang lama.

---

## 4. 🔒 Proteksi Konfigurasi & Environment
* **Gunakan Backup Otomatis:** Sebelum melakukan pengujian manual yang memodifikasi konfigurasi, buat cadangan file `.env`.
* **Keamanan Kunci Kriptografi:** Jangan pernah men-hardcode `ENCRYPTION_KEY`, `AGENT_API_KEY`, atau token bot ke dalam repositori. Pastikan file `.env` selalu masuk dalam `.gitignore`.

---

## 5. 🛠️ Checklist Sebelum Commit / Deploy
Sebelum menyatakan sebuah fitur selesai dan aman:
- [ ] `./venv/bin/python3 -m unittest discover tests` berjalan dengan sukses (0 error, 0 failure).
- [ ] Fitur baru telah didaftarkan di `config/allowed_commands.yaml`.
- [ ] Handler di `agent/command_handler.py` mengembalikan format yang kompatibel dengan parser bot di `bot/command_router.py`.
- [ ] Masukan/input dari user telah dibersihkan melewati `security/sanitizer.py`.
- [ ] File log (`logs/audit.log`) mencatat aktivitas baru tersebut dengan benar melalui `auditor.log_event()`.
