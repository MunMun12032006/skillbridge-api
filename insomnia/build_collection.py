"""Membuat insomnia/SkillBridge.insomnia.json (format export v4)."""
import json
from pathlib import Path

WRK = "wrk_skillbridge"
JSON_H = [{"name": "Content-Type", "value": "application/json"}]
BEARER = {"type": "bearer", "token": "{{ _.token }}"}


def req(i, name, method, path, body=None, headers=None, auth=False):
    r = {
        "_id": f"req_sb_{i:02d}", "_type": "request", "parentId": WRK,
        "name": name, "method": method, "url": "{{ _.base_url }}" + path,
        "headers": list(headers or []), "authentication": BEARER if auth else {},
        "metaSortKey": i * 100,
    }
    if body is not None:
        r["body"] = {"mimeType": "application/json", "text": json.dumps(body, indent=2)}
        r["headers"] = JSON_H + r["headers"]
    return r


cb = [{"name": "X-Callback-Token", "value": "rahasia-callback-gateway"}]
reqs = [
    req(1, "01 Register", "POST", "/auth/register",
        {"full_name": "Budi Santoso", "email": "budi@mail.com", "password": "Rahasia123"}),
    req(2, "02 Login (salin data.access_token ke env token)", "POST", "/auth/login",
        {"email": "budi@mail.com", "password": "Rahasia123"}),
    req(3, "03 Get Courses (salin id ke env course_id)", "GET", "/courses"),
    req(4, "04 Get Course Detail (salin 1 module id ke env module_id)", "GET", "/courses/{{ _.course_id }}"),
    req(5, "05 Create Enrollment (salin enrollment.id & invoice.id)", "POST", "/enrollments",
        {"course_id": "{{ _.course_id }}"}, auth=True),
    req(6, "06 Create Payment (salin external_ref)", "POST", "/payments",
        {"invoice_id": "{{ _.invoice_id }}", "method": "bank_transfer"}, auth=True),
    req(7, "07 Update Progress SEBELUM bayar (harapan 403)", "PATCH",
        "/enrollments/{{ _.enrollment_id }}/progress",
        {"module_id": "{{ _.module_id }}", "status": "completed"}, auth=True),
    req(8, "08 Payment Callback (paid)", "POST", "/payments/callback",
        {"external_ref": "{{ _.external_ref }}", "status": "paid", "amount": "150000.00"}, headers=cb),
    req(9, "09 My Courses (harapan status active)", "GET", "/enrollments/mycourses", auth=True),
    req(10, "10 Update Progress SETELAH bayar (harapan 200)", "PATCH",
        "/enrollments/{{ _.enrollment_id }}/progress",
        {"module_id": "{{ _.module_id }}", "status": "completed"}, auth=True),
    req(11, "Extra: Auth Me", "GET", "/auth/me", auth=True),
    req(12, "Extra: Login Admin", "POST", "/auth/login",
        {"email": "admin@skillbridge.id", "password": "Admin123!"}),
    req(13, "Extra: Callback tanpa token (harapan 401)", "POST", "/payments/callback",
        {"external_ref": "{{ _.external_ref }}", "status": "paid", "amount": "150000.00"}),
]

resources = [
    {"_id": WRK, "_type": "workspace", "parentId": None, "name": "SkillBridge API",
     "description": "Koleksi praktikum SkillBridge (FastAPI)", "scope": "collection"},
    {"_id": "env_sb_base", "_type": "environment", "parentId": WRK, "name": "Base Environment",
     "data": {"base_url": "http://localhost:8000", "token": "", "course_id": "",
              "module_id": "", "enrollment_id": "", "invoice_id": "", "external_ref": ""}},
    *reqs,
]
out = {"_type": "export", "__export_format": 4, "__export_date": "2026-10-23T00:00:00.000Z",
       "__export_source": "skillbridge.praktikum", "resources": resources}
Path(__file__).with_name("SkillBridge.insomnia.json").write_text(json.dumps(out, indent=2))
print("ok", len(resources), "resources")
