import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import authorize_role
from app.models import Enrollment, Invoice, Order, Payment, User
from app.schemas import (
    ApiResponse, PaymentCallbackIn, PaymentCreateIn, PaymentOut, ok,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", status_code=201, response_model=ApiResponse[PaymentOut])
def create_payment(
    body: PaymentCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(authorize_role("student")),
):

    invoice = db.get(Invoice, body.invoice_id)
    order = db.get(Order, invoice.order_id) if invoice else None

    if invoice is None or order is None or order.student_id != user.id:
        raise HTTPException(404, "Invoice tidak ditemukan")

    # Periksa apakah invoice sudah melewati 24 jam
    expired_at = invoice.issued_at + timedelta(hours=24)
    now = datetime.now(timezone.utc)

    if invoice.status == "unpaid" and now >= expired_at:
        invoice.status = "void"
        order.status = "cancelled"
        db.commit()
        raise HTTPException(409, "Invoice kedaluwarsa setelah 24 jam")

    if invoice.status != "unpaid":
        raise HTTPException(409, "Invoice sudah dibayar atau tidak aktif")

    pending = db.scalar(
        select(Payment).where(Payment.invoice_id == invoice.id, Payment.status == "pending")
    )
    if pending:
        raise HTTPException(409, "Masih ada pembayaran yang menunggu untuk invoice ini")

    payment = Payment(
        invoice_id=invoice.id,
        method=body.method,
        amount=invoice.amount,
        external_ref=f"SB-{uuid.uuid4().hex[:12].upper()}",
    )
    db.add(payment)
    db.commit()
    return ok(payment, "Pembayaran dibuat, menunggu konfirmasi gateway")


@router.get("/{payment_id}", response_model=ApiResponse[PaymentOut])
def get_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(authorize_role("student")),
):
    payment = db.get(Payment, payment_id)

    if payment is None:
        raise HTTPException(404, "Pembayaran tidak ditemukan")

    invoice = db.get(Invoice, payment.invoice_id)

    if invoice is None:
        raise HTTPException(404, "Pembayaran tidak ditemukan")

    order = db.get(Order, invoice.order_id)

    if order is None or order.student_id != user.id:
        raise HTTPException(404, "Pembayaran tidak ditemukan")

    return ok(payment)

@router.post("/callback", response_model=ApiResponse[PaymentOut])
def payment_callback(
    body: PaymentCallbackIn,
    x_callback_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # 1) Validasi secret: tanpa ini siapa pun bisa "melunasi" invoice sendiri
    if not x_callback_token or not hmac.compare_digest(
        x_callback_token.encode(), settings.payment_callback_secret.encode()
    ):
        raise HTTPException(401, "Callback token tidak valid")

    # 2) Kunci baris payment agar callback ganda tidak balapan
    payment = db.scalar(
        select(Payment).where(Payment.external_ref == body.external_ref).with_for_update()
    )
    if payment is None:
        raise HTTPException(404, "Pembayaran tidak ditemukan")

    # 3) Idempotent: callback yang sudah diproses tidak diproses ulang
    if payment.status != "pending":
        return ok(payment, "Callback sudah pernah diproses")

    # 4) Nominal harus cocok
    if body.amount != payment.amount:
        raise HTTPException(422, "Nominal callback tidak sesuai dengan tagihan")

    # 5) Periksa invoice dan order
    invoice = db.get(Invoice, payment.invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice tidak ditemukan")

    order = db.get(Order, invoice.order_id)

    if order is None:
        raise HTTPException(404, "Order tidak ditemukan")

    # 6) Tolak callback jika invoice sudah kedaluwarsa
    expired_at = invoice.issued_at + timedelta(hours=24)
    now = datetime.now(timezone.utc)


    if invoice.status == "unpaid" and now >= expired_at:
        invoice.status = "void"
        order.status = "cancelled"

        # Gagalkan pembayaran lama yang masih pending
        pending_payments = db.scalars(
            select(Payment).where(
                Payment.invoice_id == invoice.id,
                Payment.status == "pending",
            )
        ).all()

        for pending_payment in pending_payments:
            pending_payment.status = "failed"

        db.commit()
        raise HTTPException(409, "Invoice kedaluwarsa setelah 24 jam")

    # 7) Invoice harus masih aktif
    if invoice.status != "unpaid":
        raise HTTPException(409, "Invoice sudah dibayar atau tidak aktif")

    if body.status == "failed":
        payment.status = "failed"
        db.commit()
        return ok(payment, "Pembayaran ditandai gagal")
    
    # 8) PAID: update payment, invoice, order, enrollment secara konsisten (1 transaksi)
    now = datetime.now(timezone.utc)
    payment.status = "paid"
    payment.paid_at = now

    invoice.status = "paid"
    invoice.paid_at = now

    order.status = "paid"

    enrollment = db.scalar(select(Enrollment).where(Enrollment.order_id == order.id))
    enrollment.status = "active"

    db.commit()  # semua berhasil, atau semua dibatalkan
    return ok(payment, "Pembayaran berhasil, enrollment aktif")
