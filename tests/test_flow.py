"""Uji otomatis alur lengkap SkillBridge (mengulang urutan Insomnia).

Prasyarat: tabel sudah dibuat dan seed sudah dijalankan.
Jalankan  : pytest -v
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
CALLBACK = {"X-Callback-Token": settings.payment_callback_secret}


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
    r = client.get("/courses")
    assert r.status_code == 200
    cid = r.json()["data"][0]["id"]
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

    # callback: token salah / tanpa token / nominal salah
    cb = {"external_ref": pay["external_ref"], "status": "paid", "amount": pay["amount"]}
    assert client.post("/payments/callback", json=cb).status_code == 401
    assert client.post("/payments/callback", json=cb, headers={"X-Callback-Token": "x"}).status_code == 401
    bad = {**cb, "amount": "1.00"}
    assert client.post("/payments/callback", json=bad, headers=CALLBACK).status_code == 422
    my = client.get("/enrollments/mycourses", headers=h).json()["data"]
    assert my[0]["status"] == "pending_payment"  # belum berubah

    # callback paid
    r = client.post("/payments/callback", json=cb, headers=CALLBACK)
    assert r.status_code == 200 and r.json()["data"]["status"] == "paid"

    # idempotent
    r = client.post("/payments/callback", json=cb, headers=CALLBACK)
    assert r.status_code == 200 and "sudah pernah" in r.json()["message"]

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
    r = client.post(
        "/payments/callback",
        json={"external_ref": p1["external_ref"], "status": "failed", "amount": p1["amount"]},
        headers=CALLBACK,
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "failed"
    r = client.post("/payments", json={"invoice_id": inv, "method": "ewallet"}, headers=h)
    assert r.status_code == 201  # boleh coba bayar lagi
