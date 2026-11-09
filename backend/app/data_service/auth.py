"""Opaque, revocable database sessions; no default accounts or public registration."""

import hashlib
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.data_service.service import _normalized_datetime
from app.domain.management import UserView
from app.persistence.database import session_scope
from app.persistence.models import AuditLog, AuthSession, User, utc_now

bearer = HTTPBearer(auto_error=False, scheme_name="AdminSession")


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=32768,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
        dklen=32,
    ).hex()
    return f"scrypt-v1${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, _ = encoded.split("$")
        if scheme != "scrypt-v1" or len(salt) != 32:
            return False
        return secrets.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD = hash_password("unused-dummy-account-password")


def session_dependency(request: Request):
    with session_scope(request.app.state.session_factory) as session:
        yield session


DB = Annotated[Session, Depends(session_dependency, scope="function")]


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def current_user(
    session: DB,
    credential: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> User:
    if credential is None:
        raise ServiceError("UNAUTHORIZED", "Sign in to continue", 401)
    record = session.get(AuthSession, token_hash(credential.credentials))
    if record is None or _normalized_datetime(record.expires_at) <= utc_now():
        raise ServiceError("UNAUTHORIZED", "Session is invalid or expired", 401)
    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise ServiceError("UNAUTHORIZED", "Session is invalid or expired", 401)
    return user


def roles(*allowed):
    def require(user: Annotated[User, Depends(current_user)]):
        if user.role not in allowed:
            raise ServiceError("FORBIDDEN", "Your role cannot perform this operation", 403)
        return user

    return require


SignedIn = Annotated[User, Depends(current_user)]
Uploader = Annotated[User, Depends(roles("admin", "uploader"))]
Reviewer = Annotated[User, Depends(roles("admin", "reviewer"))]
Administrator = Annotated[User, Depends(roles("admin"))]


def user_view(user):
    return UserView.model_validate(user, from_attributes=True)


def audit(session, user, action, entity_type, entity_id, **details):
    session.add(
        AuditLog(
            actor_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details,
        )
    )


def login(session, payload, hours):
    email = payload.email.strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == email))
    valid = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD)
    if not valid or user is None or not user.is_active:
        raise ServiceError("UNAUTHORIZED", "Invalid email or password", 401)
    token = secrets.token_urlsafe(48)
    expires = utc_now() + timedelta(hours=hours)
    session.add(AuthSession(token_hash=token_hash(token), user_id=user.id, expires_at=expires))
    audit(session, user, "login", "user", user.id)
    return {"access_token": token, "expires_at": expires, "user": user_view(user)}
