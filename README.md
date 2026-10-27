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
Header `X-Callback-Token` di request callback harus sama dengan `PAYMENT_CALLBACK_SECRET` di `.env`.

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
