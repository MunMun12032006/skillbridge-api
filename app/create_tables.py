from app import models  # noqa: F401  (wajib di-import agar model terdaftar)
from sqlalchemy import text

from app.database import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    # create_all tidak menambah kolom ke tabel yang sudah ada.
    # Migrasi ringan dan idempotent untuk database praktikum PostgreSQL lama.
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "UPDATE invoices SET expired_at = issued_at + INTERVAL '24 hours' "
            "WHERE expired_at IS NULL"
        ))
        conn.execute(text(
            "ALTER TABLE invoices ALTER COLUMN expired_at SET NOT NULL"
        ))
    print("Tabel dan kolom expired_at siap.")
