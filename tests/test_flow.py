"""Uji otomatis alur lengkap SkillBridge (mengulang urutan Insomnia).

Prasyarat: tabel sudah dibuat dan seed sudah dijalankan.
Jalankan  : pytest -v
"""
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Enrollment, Invoice, Order, Payment

import hashlib
import hmac
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


client = TestClient(app)


def signed_callback(payload: dict):
    # Ubah data menjadi JSON bytes
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    # Hitung signature HMAC-SHA256
    signature = hmac.new(
        settings.payment_callback_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # Kirim raw JSON dengan signature yang cocok
    return client.post(
        "/payments/callback",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Callback-Signature": signature,
        },
    )

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def student():
    email = f"siswa-{uuid.uuid4().hex[:8]}@mail.com"
    r = client.post(
        "/auth/register",
        json={"full_name": "Siswa Uji", "email": email, "password": "Rahasia123"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["role"] == "student"
    return {"email": email, "token": login(email, "Rahasia123")}


@pytest.fixture(scope="module")
def course():
    r = client.get(
        "/courses",
        params={"q": "REST API dengan FastAPI"},
    )
    assert r.status_code == 200
    cid = next(
        item["id"]
        for item in r.json()["data"]
        if item["title"] == "REST API dengan FastAPI"
    )
    detail = client.get(f"/courses/{cid}").json()["data"]
    assert len(detail["modules"]) == 4
    return detail


def test_register_ignores_role_and_rejects_duplicates(student):
    r = client.post(
        "/auth/register",
        json={"full_name": "X Y", "email": student["email"], "password": "Rahasia123"},
    )
    assert r.status_code == 409
    r = client.post(
        "/auth/register",
        json={"full_name": "Hacker", "email": f"h-{uuid.uuid4().hex[:6]}@mail.com",
              "password": "Rahasia123", "role": "admin"},
    )
    assert r.status_code == 201
    assert r.json()["data"]["role"] == "student"


def test_validation_errors_use_standard_format():
    r = client.post("/auth/register", json={"full_name": "A", "email": "bukan-email", "password": "123"})
    body = r.json()
    assert r.status_code == 422
    assert set(body) == {"message", "data", "errors"} and body["errors"]


def test_auth_errors(student):
    assert client.get("/enrollments/mycourses").status_code == 401
    assert client.get("/enrollments/mycourses", headers=auth("ngawur")).status_code == 401
    assert client.post("/auth/login", json={"email": student["email"], "password": "salah-salah"}).status_code == 401


def test_roles(student, course):
    admin = login("admin@skillbridge.id", "Admin123!")
    r = client.post("/enrollments", json={"course_id": course["id"]}, headers=auth(admin))
    assert r.status_code == 403
    r = client.post(
        "/courses",
        json={"category_id": course["category_id"], "title": "Kursus Baru", "price": "1000.00"},
        headers=auth(student["token"]),
    )
    assert r.status_code == 403
    inst = login("instructor@skillbridge.id", "Instruktur123!")
    r = client.post(
        "/courses",
        json={"category_id": course["category_id"], "title": "Kursus Baru", "price": "1000.00"},
        headers=auth(inst),
    )
    assert r.status_code == 201


def test_course_lookup_errors():
    assert client.get(f"/courses/{uuid.uuid4()}").status_code == 404
    assert client.get("/courses/abc").status_code == 422


def test_full_purchase_flow(student, course):
    h = auth(student["token"])

    # enrollment -> order + invoice
    r = client.post("/enrollments", json={"course_id": course["id"]}, headers=h)
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    enrollment_id, invoice_id = d["enrollment"]["id"], d["invoice"]["id"]
    assert d["enrollment"]["status"] == "pending_payment"
    assert d["invoice"]["status"] == "unpaid" and d["order"]["status"] == "pending"

    # dua kali -> 409
    assert client.post("/enrollments", json={"course_id": course["id"]}, headers=h).status_code == 409

    module_id = course["modules"][0]["id"]
    progress = {"module_id": module_id, "status": "completed"}

    # belum bayar -> progress ditolak
    r = client.patch(f"/enrollments/{enrollment_id}/progress", json=progress, headers=h)
    assert r.status_code == 403

    # payment
    r = client.post("/payments", json={"invoice_id": invoice_id, "method": "bank_transfer"}, headers=h)
    assert r.status_code == 201, r.text
    pay = r.json()["data"]
    assert client.post("/payments", json={"invoice_id": invoice_id, "method": "qris"}, headers=h).status_code == 409


    # Callback tanpa signature harus ditolak
    cb = {
        "external_ref": pay["external_ref"],
        "status": "paid",
        "amount": pay["amount"],
    }

    assert client.post(
        "/payments/callback",
        json=cb,
    ).status_code == 401

    # Signature yang salah harus ditolak
    assert client.post(
        "/payments/callback",
        json=cb,
        headers={"X-Callback-Signature": "signature-salah"},
    ).status_code == 401

    # Nominal salah dengan signature valid harus ditolak
    bad = {**cb, "amount": "1.00"}
    assert signed_callback(bad).status_code == 422

    # Enrollment belum aktif sebelum pembayaran berhasil
    my = client.get("/enrollments/mycourses", headers=h).json()["data"]
    assert my[0]["status"] == "pending_payment"

    # Callback dengan signature valid: pembayaran berhasil
    r = signed_callback(cb)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "paid"

    # Idempotency: callback yang sama tidak diproses dua kali
    r = signed_callback(cb)
    assert r.status_code == 200
    assert "sudah pernah" in r.json()["message"]

    my = client.get("/enrollments/mycourses", headers=h).json()["data"]
    assert my[0]["status"] == "active" and my[0]["total_modules"] == 4

    # progress 25% -> 100%
    r = client.patch(f"/enrollments/{enrollment_id}/progress", json=progress, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["progress_percentage"] == 25.0
    for m in course["modules"][1:]:
        r = client.patch(
            f"/enrollments/{enrollment_id}/progress",
            json={"module_id": m["id"], "status": "completed"}, headers=h,
        )
    assert r.json()["data"]["enrollment_status"] == "completed"
    assert r.json()["data"]["progress_percentage"] == 100.0

    # student lain tidak bisa menyentuh enrollment ini (404)
    other_email = f"lain-{uuid.uuid4().hex[:6]}@mail.com"
    client.post("/auth/register", json={"full_name": "Orang Lain", "email": other_email, "password": "Rahasia123"})
    other = login(other_email, "Rahasia123")
    r = client.patch(f"/enrollments/{enrollment_id}/progress", json=progress, headers=auth(other))
    assert r.status_code == 404
    r = client.post("/payments", json={"invoice_id": invoice_id, "method": "qris"}, headers=auth(other))
    assert r.status_code == 404


def test_failed_payment_allows_retry(student):
    h = auth(student["token"])
    inst = login("instructor@skillbridge.id", "Instruktur123!")
    cat = client.get("/courses").json()["data"][0]["category_id"]
    new = client.post(
        "/courses",
        json={"category_id": cat, "title": f"Retry {uuid.uuid4().hex[:5]}", "price": "50000.00"},
        headers=auth(inst),
    ).json()["data"]
    d = client.post("/enrollments", json={"course_id": new["id"]}, headers=h).json()["data"]
    inv = d["invoice"]["id"]
    p1 = client.post("/payments", json={"invoice_id": inv, "method": "ewallet"}, headers=h).json()["data"]
    r = signed_callback({
        "external_ref": p1["external_ref"],
        "status": "failed",
        "amount": p1["amount"],
    })
    assert r.status_code == 200 and r.json()["data"]["status"] == "failed"
    r = client.post("/payments", json={"invoice_id": inv, "method": "ewallet"}, headers=h)
    assert r.status_code == 201  # boleh coba bayar lagi

def test_callback_rejects_tampered_body():
    # Buat JSON callback pengujian
    original = json.dumps(
        {
            "external_ref": f"SB-TEST-{uuid.uuid4().hex}",
            "status": "paid",
            "amount": 50000,
        },
        separators=(",", ":"),
    ).encode("utf-8")

    # Buat signature dari JSON asli
    signature = hmac.new(
        settings.payment_callback_secret.encode("utf-8"),
        original,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Callback-Signature": signature,
    }

    # Signature valid, tetapi payment sengaja tidak ada
    r = client.post(
        "/payments/callback",
        content=original,
        headers=headers,
    )
    assert r.status_code == 404

    # Manipulasi nominal setelah signature dibuat
    tampered = original.replace(
        b'"amount":50000',
        b'"amount":50001',
    )
    assert tampered != original

    # Signature lama tidak cocok dengan JSON yang diubah
    r = client.post(
        "/payments/callback",
        content=tampered,
        headers=headers,
    )
    assert r.status_code == 401

def test_course_modules_endpoint(course):
    course_id = course["id"]

    # 1. Mengambil daftar modul kursus
    r = client.get(f"/courses/{course_id}/modules")

    assert r.status_code == 200, r.text

    modules = r.json()["data"]

    # 2. Memastikan jumlah modul ada 4
    assert len(modules) == 4

    # 3. Memastikan urutan posisi modul benar
    positions = [m["position"] for m in modules]
    assert positions == [1, 2, 3, 4]

    # 4. Kursus yang tidak ditemukan harus menghasilkan 404
    invalid_id = uuid.uuid4()

    r = client.get(f"/courses/{invalid_id}/modules")
    assert r.status_code == 404

def test_payment_detail_access(student, course):
    # 1. Login sebagai instructor
    instructor = login(
        "instructor@skillbridge.id",
        "Instruktur123!",
    )

    # 2. Buat kursus khusus pengujian
    r = client.post(
        "/courses",
        json={
            "category_id": course["category_id"],
            "title": f"Payment Detail {uuid.uuid4().hex[:6]}",
            "price": "25000.00",
        },
        headers=auth(instructor),
    )
    assert r.status_code == 201, r.text
    course_id = r.json()["data"]["id"]

    # 3. Student membuat enrollment
    r = client.post(
        "/enrollments",
        json={"course_id": course_id},
        headers=auth(student["token"]),
    )
    assert r.status_code == 201, r.text
    invoice_id = r.json()["data"]["invoice"]["id"]

    # 4. Student membuat pembayaran
    r = client.post(
        "/payments",
        json={
            "invoice_id": invoice_id,
            "method": "bank_transfer",
        },
        headers=auth(student["token"]),
    )
    assert r.status_code == 201, r.text
    payment_id = r.json()["data"]["id"]

    # 5. Pemilik pembayaran boleh melihat datanya
    r = client.get(
        f"/payments/{payment_id}",
        headers=auth(student["token"]),
    )
    assert r.status_code == 200
    assert r.json()["data"]["id"] == payment_id
    assert r.json()["data"]["status"] == "pending"

    # 6. Buat akun student kedua
    email = f"student-lain-{uuid.uuid4().hex[:6]}@mail.com"

    r = client.post(
        "/auth/register",
        json={
            "full_name": "Student Lain",
            "email": email,
            "password": "Rahasia123",
        },
    )
    assert r.status_code == 201
    other_token = login(email, "Rahasia123")

    # 7. Student lain tidak boleh melihat pembayaran
    r = client.get(
        f"/payments/{payment_id}",
        headers=auth(other_token),
    )
    assert r.status_code == 404

    # 8. Tanpa login harus ditolak
    r = client.get(f"/payments/{payment_id}")
    assert r.status_code == 401

    # 9. Payment ID yang tidak ada harus menghasilkan 404
    r = client.get(
        f"/payments/{uuid.uuid4()}",
        headers=auth(student["token"]),
    )
    assert r.status_code == 404

def test_patch_course_permissions(student, course):
    # 1. Login instructor dan admin
    instructor = login(
        "instructor@skillbridge.id",
        "Instruktur123!",
    )
    admin = login(
        "admin@skillbridge.id",
        "Admin123!",
    )

    # 2. Instructor membuat kursus baru
    r = client.post(
        "/courses",
        json={
            "category_id": course["category_id"],
            "title": f"PATCH Test {uuid.uuid4().hex[:6]}",
            "price": "120000.00",
        },
        headers=auth(instructor),
    )
    assert r.status_code == 201, r.text

    course_id = r.json()["data"]["id"]

    # 3. Instructor pemilik boleh mengedit kursus
    r = client.patch(
        f"/courses/{course_id}",
        json={"description": "Diubah oleh instructor"},
        headers=auth(instructor),
    )
    assert r.status_code == 200
    assert r.json()["data"]["description"] == "Diubah oleh instructor"

    # 4. Student tidak boleh mengedit kursus
    r = client.patch(
        f"/courses/{course_id}",
        json={"price": "130000.00"},
        headers=auth(student["token"]),
    )
    assert r.status_code == 403

    # 5. Admin boleh mengedit kursus instructor
    r = client.patch(
        f"/courses/{course_id}",
        json={"description": "Diubah oleh admin"},
        headers=auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["data"]["description"] == "Diubah oleh admin"

    # 6. Admin membuat kursus lain
    r = client.post(
        "/courses",
        json={
            "category_id": course["category_id"],
            "title": f"Admin Course {uuid.uuid4().hex[:6]}",
            "price": "50000.00",
        },
        headers=auth(admin),
    )
    assert r.status_code == 201, r.text

    admin_course_id = r.json()["data"]["id"]

    # 7. Instructor tidak boleh mengedit kursus
    # yang bukan miliknya
    r = client.patch(
        f"/courses/{admin_course_id}",
        json={"description": "Percobaan edit tanpa izin"},
        headers=auth(instructor),
    )
    assert r.status_code == 403

    # 8. Kursus yang tidak ada harus menghasilkan 404
    r = client.patch(
        f"/courses/{uuid.uuid4()}",
        json={"title": "Kursus Tidak Ada"},
        headers=auth(instructor),
    )
    assert r.status_code == 404

def test_invoice_expires_after_24_hours(student, course):
    # 1. Login instructor
    instructor = login(
        "instructor@skillbridge.id",
        "Instruktur123!",
    )

    # 2. Buat kursus khusus pengujian
    r = client.post(
        "/courses",
        json={
            "category_id": course["category_id"],
            "title": f"Invoice Expiry {uuid.uuid4().hex[:6]}",
            "price": "50000.00",
        },
        headers=auth(instructor),
    )
    assert r.status_code == 201, r.text
    course_id = r.json()["data"]["id"]

    # 3. Student membuat enrollment
    r = client.post(
        "/enrollments",
        json={"course_id": course_id},
        headers=auth(student["token"]),
    )
    assert r.status_code == 201, r.text

    data = r.json()["data"]
    invoice_id = uuid.UUID(data["invoice"]["id"])
    order_id = uuid.UUID(data["order"]["id"])

    assert data["invoice"]["status"] == "unpaid"
    assert data["order"]["status"] == "pending"

    # 4. Simulasikan invoice berumur 25 jam
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        assert invoice is not None

        invoice.issued_at = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        )
        db.commit()

    # 5. Coba bayar invoice yang sudah kedaluwarsa
    r = client.post(
        "/payments",
        json={
            "invoice_id": str(invoice_id),
            "method": "bank_transfer",
        },
        headers=auth(student["token"]),
    )

    # 6. Pembayaran harus ditolak
    assert r.status_code == 409, r.text
    assert "kedaluwarsa" in r.json()["message"].lower()

    # 7. Periksa status di database
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        order = db.get(Order, order_id)

        assert invoice.status == "void"
        assert order.status == "cancelled"

def test_expired_invoice_rejects_payment_callback(student, course):
    # 1. Login instructor
    instructor = login(
        "instructor@skillbridge.id",
        "Instruktur123!",
    )

    # 2. Buat kursus khusus pengujian
    r = client.post(
        "/courses",
        json={
            "category_id": course["category_id"],
            "title": f"Expired Callback {uuid.uuid4().hex[:6]}",
            "price": "50000.00",
        },
        headers=auth(instructor),
    )
    assert r.status_code == 201, r.text
    course_id = r.json()["data"]["id"]

    # 3. Student membuat enrollment
    r = client.post(
        "/enrollments",
        json={"course_id": course_id},
        headers=auth(student["token"]),
    )
    assert r.status_code == 201, r.text

    data = r.json()["data"]
    enrollment_id = uuid.UUID(data["enrollment"]["id"])
    invoice_id = uuid.UUID(data["invoice"]["id"])
    order_id = uuid.UUID(data["order"]["id"])

    # 4. Buat payment saat invoice masih aktif
    r = client.post(
        "/payments",
        json={
            "invoice_id": str(invoice_id),
            "method": "bank_transfer",
        },
        headers=auth(student["token"]),
    )
    assert r.status_code == 201, r.text

    payment_data = r.json()["data"]
    payment_id = uuid.UUID(payment_data["id"])

    assert payment_data["status"] == "pending"

    # 5. Simulasikan invoice berumur 25 jam
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        invoice.issued_at = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        )
        db.commit()

    # 6. Kirim callback dengan signature HMAC valid
    callback = {
        "external_ref": payment_data["external_ref"],
        "status": "paid",
        "amount": payment_data["amount"],
    }

    r = signed_callback(callback)

    # 7. Callback harus ditolak karena kedaluwarsa
    assert r.status_code == 409, r.text
    assert "kedaluwarsa" in r.json()["message"].lower()

    # 8. Pastikan status database benar
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        order = db.get(Order, order_id)
        payment = db.get(Payment, payment_id)
        enrollment = db.get(Enrollment, enrollment_id)

        assert invoice.status == "void"
        assert order.status == "cancelled"
        assert payment.status == "failed"
        assert enrollment.status == "pending_payment"

