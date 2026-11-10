# SkillBridge API (FastAPI) — Project Praktikum

API backend e-learning: register/login, katalog kursus, enrollment, pembayaran
(dengan callback payment gateway), dan progress belajar. Mengikuti
*Panduan Implementasi API SkillBridge*, dengan stack FastAPI + PostgreSQL.

## Prasyarat
- Python 3.10 atau lebih baru (`python --version`)
- Docker Desktop (untuk PostgreSQL) **atau** PostgreSQL lokal
- Insomnia (https://insomnia.rest)

## Menjalankan (Windows / Mac / Linux)

```bash
# 1) Database
docker compose up -d

# 2) Virtual environment
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell

# 3) Dependency + konfigurasi
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env

# 4) Tabel + seed + server
python -m app.create_tables
python -m app.seed
uvicorn app.main:app --reload
```

- Swagger UI : http://localhost:8000/docs
- OpenAPI    : http://localhost:8000/openapi.json

## Akun seed
| Role       | Email                     | Password       |
|------------|---------------------------|----------------|
| admin      | admin@skillbridge.id      | Admin123!      |
| instructor | instructor@skillbridge.id | Instruktur123! |

Student dibuat sendiri lewat `POST /auth/register`.

## Insomnia
Import `insomnia/SkillBridge.insomnia.json` (Application → Import).
Alternatif: Import → From URL → `http://localhost:8000/openapi.json`.
Nilai env (`token`, `course_id`, dst.) disalin manual dari response sebelumnya.
Untuk latihan mandiri halaman 14, callback menggunakan `X-Callback-Signature` (HMAC-SHA256 atas **raw body**), bukan lagi `X-Callback-Token`. Lihat petunjuk signature di bawah.

## Uji otomatis (untuk instruktur / cek mandiri)
```bash
pip install -r requirements-dev.txt
pytest -v
```
Tes memerlukan database yang sudah di-seed.

## Reset database
```bash
docker compose down -v && docker compose up -d
python -m app.create_tables && python -m app.seed
```

## Struktur
```
app/
  config.py  database.py  models.py  schemas.py  security.py  deps.py
  create_tables.py  seed.py  main.py
  routers/  auth.py  courses.py  enrollments.py  payments.py
tests/test_flow.py
insomnia/SkillBridge.insomnia.json
```


## Lanjutan latihan mandiri Meet 7 (halaman 14)

1. `GET /courses/{course_id}/modules` — modul terurut berdasarkan `position`.
2. `GET /payments/{payment_id}` — status pembayaran hanya terlihat oleh student pemilik (student lain menerima 404).
3. `PATCH /courses/{course_id}` — instructor hanya mengedit kursus miliknya, admin boleh semua. Body dapat berisi `title`, `description`, atau `price`.
4. Kolom `invoices.expired_at` (default 24 jam dari pembuatan) — callback `paid` setelah kedaluwarsa ditolak 409.
5. Callback sekarang menggunakan HMAC-SHA256 atas *raw HTTP request body*.
6. `tests/test_flow.py` memuat pengujian tambahan untuk modul/otorisasi, kepemilikan pembayaran, dan invoice kedaluwarsa.

### Memperbarui database lama (tanpa menghapus data)

Setelah mengaktifkan virtual environment, jalankan:

```powershell
python -m app.create_tables
```

Perintah ini membuat tabel jika belum ada, lalu menambahkan `invoices.expired_at` pada database lama secara idempotent. Invoice lama yang belum memiliki masa berlaku akan memperoleh batas waktu `issued_at + 24 hours`. **Tidak perlu** menjalankan `docker compose down -v` karena perintah tersebut menghapus volume dan data database.

### Menyiapkan callback di Insomnia

Request `POST /payments/callback` memerlukan header:

```text
Content-Type: application/json
X-Callback-Signature: sha256=<64-digit-hex>
```

Nilai tanda tangan tergantung pada **setiap byte** body JSON. Contoh body yang disimpan persis ke file `callback.json`:

```json
{"external_ref":"SB-GANTI_DENGAN_REF","status":"paid","amount":"150000.00"}
```

Gunakan `external_ref` dari response `POST /payments`. Untuk mendapatkan header tanda tangan, pada PowerShell:

```powershell
python scripts/sign_callback.py callback.json --secret "nilai-PAYMENT_CALLBACK_SECRET-di-env"
```

Salin nilai `X-Callback-Signature` yang dihasilkan ke Insomnia; kirim body JSON **persis seperti isi file** (termasuk spasi, urutan key, dan newline). Jangan memakai token/signature lama dari modul dasar. Jangan mengunggah file secret atau `.env` ke repository publik.

### Menguji implementasi

```powershell
python -m app.create_tables
python -m app.seed
python -m pytest -v
```

Uji juga Insomnia: login student, enrollment, pembayaran, callback valid/invalid, lalu lihat perubahan status dan query SQL sesuai PDF. GitHub Actions di branch latihan menjalankan pytest dengan service PostgreSQL untuk pengecekan otomatis.
