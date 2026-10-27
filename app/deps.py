import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)
_UNAUTH = {"WWW-Authenticate": "Bearer"}


def authenticate(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Token tidak dikirim", headers=_UNAUTH)
    try:
        payload = decode_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Token tidak valid atau kedaluwarsa", headers=_UNAUTH)

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "User tidak ditemukan", headers=_UNAUTH)
    return user


def authorize_role(*roles: str):
    def checker(user: User = Depends(authenticate)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Anda tidak punya akses ke resource ini")
        return user

    return checker
