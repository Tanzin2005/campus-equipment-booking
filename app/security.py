"""Argon2 passwords and revocable, opaque cookie sessions."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import Header, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from app.database import transaction
from app.models import auth_attempts, sessions, users

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("dummy-password-only-for-timing-equalization")
COOKIE = "campus_session"
SESSION_SECONDS = 60 * 60 * 12


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now():
    return datetime.now(timezone.utc)


def issue_session(db, user_id):
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    db.execute(delete(sessions).where(sessions.c.expires_at < now()))
    db.execute(sessions.insert().values(token_hash=digest(token), user_id=user_id,
        csrf_token=csrf, expires_at=now() + timedelta(seconds=SESSION_SECONDS)))
    return token, csrf


def set_cookie(response, token, secure):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=secure, samesite="strict", path="/")


def current_user(request: Request, csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 128:
        raise HTTPException(401, "Please sign in to continue")
    with transaction(request.app.state.engine) as db:
        record = db.execute(select(users, sessions.c.csrf_token).join(
            sessions, sessions.c.user_id == users.c.id).where(
                sessions.c.token_hash == digest(token), sessions.c.expires_at > now())).mappings().first()
    if not record:
        raise HTTPException(401, "Your session has expired. Please sign in again")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = csrf or ""
        if not secrets.compare_digest(supplied.encode(), record["csrf_token"].encode()):
            raise HTTPException(403, "Session verification failed. Refresh the page and try again")
    return dict(record)


def require_admin(user):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required")


def throttle(request, action, limit):
    """Shared database counters: atomic across threads and application workers."""
    stamp = now()
    bucket = int(stamp.timestamp()) // 900
    host = request.client.host if request.client else "unknown"
    key = f"{action}:{digest(host)}:{bucket}"
    engine = request.app.state.engine
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    with transaction(engine, write=True) as db:
        db.execute(delete(auth_attempts).where(auth_attempts.c.expires_at < stamp))
        statement = insert(auth_attempts).values(key=key, count=1,
            expires_at=datetime.fromtimestamp((bucket + 1) * 900, timezone.utc))
        count = db.execute(statement.on_conflict_do_update(index_elements=[auth_attempts.c.key],
            set_={"count": auth_attempts.c.count + 1}).returning(auth_attempts.c.count)).scalar_one()
    if count > limit:
        retry = max(1, (bucket + 1) * 900 - int(stamp.timestamp()))
        raise HTTPException(429, "Too many attempts. Please try again later", headers={"Retry-After": str(retry)})
