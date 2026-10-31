"""Shared demo login: a signed session token in an httpOnly cookie."""

import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Request

from app.core.config import Settings
from app.core.errors import AppError

COOKIE_NAME = "azentio_session"
ALGORITHM = "HS256"


def credentials_match(settings: Settings, username: str, password: str) -> bool:
    # Compare both fields in constant time so a wrong username takes as long as a wrong password.
    user_ok = hmac.compare_digest(username.encode(), settings.demo_username.encode())
    password_ok = hmac.compare_digest(password.encode(), settings.demo_password.get_secret_value().encode())
    return user_ok and password_ok


def create_session_token(settings: Settings, username: str) -> str:
    now = datetime.now(UTC)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(minutes=settings.session_max_age_minutes)}
    return jwt.encode(payload, settings.session_secret.get_secret_value(), algorithm=ALGORITHM)


def session_username(request: Request) -> str:
    """FastAPI dependency: the logged-in username, or 401."""
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise AppError(401, "unauthorized", "Not logged in")
    try:
        payload = jwt.decode(token, settings.session_secret.get_secret_value(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AppError(401, "unauthorized", "Session is invalid or expired") from exc
    if payload.get("sub") != settings.demo_username:
        raise AppError(401, "unauthorized", "Session is invalid or expired")
    return payload["sub"]


CurrentUser = Annotated[str, Depends(session_username)]
