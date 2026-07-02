# Protokol Pendaftaran Fitur Baru (RAV-SPY)

## 1. Tujuan
Dokumen ini dibuat untuk memastikan setiap fitur baru yang ditambahkan ke **RAV-SPY** terdaftar secara resmi di seluruh lapisan sistem. Hal ini mencegah terjadinya error "Input Tidak Valid" atau "Command Blocked" karena sistem keamanan (Sanitizer) tidak mengenali perintah tersebut.

## 2. Alur Wajib Penambahan Fitur
Setiap kali menambahkan atau mengubah perintah (command), pengembang (AI/Manusia) **WAJIB** mengikuti checklist berikut:

### Langkah 1: Pendaftaran di Whitelist (Security)
Daftarkan perintah di file `config/allowed_commands.yaml`. 
*   Tambahkan nama perintah utama.
*   Tambahkan alias (jika ada).
*   Tentukan apakah butuh konfirmasi (`requires_confirmation`).
*   Tentukan apakah wajib di sandbox (`sandbox_required`).

**Contoh:**
```yaml
  nama_fitur:
    description: "Deskripsi singkat fitur"
    requires_confirmation: false
    sandbox_required: false
```

### Langkah 2: Implementasi Handler (Agent)
Pastikan fungsi eksekusi sudah tersedia di `agent/command_handler.py` dan didelegasikan ke modul yang sesuai (misal: `agent/video_recorder.py`).

### Langkah 3: Registrasi Router (Bot)
Pastikan perintah tersebut sudah dikenali oleh `bot/command_router.py` agar bot tahu harus memanggil fungsi handler yang mana.

### Langkah 4: Validasi Sanitizer
Uji apakah `security/sanitizer.py` membiarkan perintah tersebut lewat. Sanitizer akan memblokir apa pun yang tidak ada di `allowed_commands.yaml`.

### Langkah 5: Sinkronisasi Bot (Telegram & WhatsApp)
Pastikan respons dan format media sudah ditangani dengan cara yang sama di:
*   `bot/telegram_bot.py`
*   `bot/whatsapp_bot.js`

## 3. Checklist Verifikasi Akhir
Sebelum dianggap selesai, fitur harus lulus uji berikut:
- [ ] Perintah terdaftar di `config/allowed_commands.yaml`.
- [ ] Perintah bisa dipanggil dengan prefix `!` (Explicit Mode).
- [ ] Perintah bisa dipanggil dengan bahasa natural (AI Mode).
- [ ] Indikator "typing..." muncul saat proses berjalan.
- [ ] Pesan error spesifik muncul jika gagal (bukan error generik).
- [ ] Lolos uji di file `tests/test_e2e.py`.

---
*Dokumen ini bersifat foundational dan wajib diikuti untuk menjaga integritas sistem.*
