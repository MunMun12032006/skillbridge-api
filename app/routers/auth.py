from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import authenticate
from app.models import User
from app.schemas import ApiResponse, LoginIn, RegisterIn, TokenOut, UserOut, ok
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=201, response_model=ApiResponse[UserOut])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email sudah terdaftar")

    user = User(
        full_name=body.full_name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role="student",  # SELALU student, tidak boleh dari input client
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # dua request bersamaan lolos cek di atas
        db.rollback()
        raise HTTPException(409, "Email sudah terdaftar")
    return ok(user, "Registrasi berhasil")


@router.post("/login", response_model=ApiResponse[TokenOut])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Pesan sengaja sama untuk email salah dan password salah
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email atau password salah")

    token = create_access_token(str(user.id), user.role)
    return ok({"access_token": token, "token_type": "bearer", "user": user}, "Login berhasil")


@router.get("/me", response_model=ApiResponse[UserOut])
def me(user: User = Depends(authenticate)):
    return ok(user)
