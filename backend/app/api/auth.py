from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core import audit
from app.core.config import Settings
from app.core.enums import Role
from app.core.errors import AppError
from app.core.security import (
    COOKIE_NAME,
    CurrentPrincipal,
    create_session_token,
    credentials_match,
    find_user,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.db.session import SessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    username: str
    display_name: str
    role: Role


async def _bootstrap_admin(session: SessionDep, settings: Settings, username: str, password: str) -> User | None:
    """With no users yet, the environment's demo login creates the first admin, so a fresh deployment
    can sign in and onboard everyone else. Once a user exists, the environment login stops working."""
    count = await session.scalar(select(func.count()).select_from(User))
    if count or not credentials_match(settings, username, password):
        return None
    user = User(
        username=settings.demo_username,
        display_name="Administrator",
        role=Role.ADMIN.value,
        password_hash=hash_password(password),
        created_by=None,
    )
    session.add(user)
    await session.flush()
    audit.record(session, user.username, "user_bootstrapped", "user", user.id, role=user.role)
    await session.commit()
    return user


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> SessionOut:
    settings: Settings = request.app.state.settings
    username = body.username.strip()
    user = await find_user(session, username)
    if user is None:
        user = await _bootstrap_admin(session, settings, username, body.password)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Invalid username or password")
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(settings, user),
        max_age=settings.session_max_age_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionOut(username=user.username, display_name=user.display_name, role=Role(user.role))


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(principal: CurrentPrincipal) -> SessionOut:
    return SessionOut(username=principal.username, display_name=principal.display_name, role=Role(principal.role))
