from app import models  # noqa: F401  (wajib di-import agar model terdaftar)
from app.database import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Tabel berhasil dibuat.")
