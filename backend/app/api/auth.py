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


# The accounts seeded on an empty users table, all with DEMO_PASSWORD. The admin's username comes
# from DEMO_USERNAME so the existing deployment keeps its login.
DEMO_ACCOUNTS: tuple[tuple[str | None, str, Role], ...] = (
    (None, "Administrator", Role.ADMIN),
    ("reviewer", "Senior claims reviewer", Role.SENIOR_REVIEWER),
    ("analyst", "Claims analyst", Role.ANALYST),
)


def demo_usernames(settings: Settings) -> list[str]:
    return [username or settings.demo_username for username, _, _ in DEMO_ACCOUNTS]


async def _bootstrap_demo_accounts(
    session: SessionDep, settings: Settings, username: str, password: str
) -> User | None:
    """With no users yet, the environment's demo login seeds the demo accounts, so a fresh deployment
    can sign in and onboard everyone else. Once any user exists, the environment login stops working."""
    count = await session.scalar(select(func.count()).select_from(User))
    if count or not credentials_match(settings, username, password):
        return None
    password_hash = hash_password(password)
    users = [
        User(
            username=name or settings.demo_username,
            display_name=display_name,
            role=role.value,
            password_hash=password_hash,
            created_by=None,
        )
        for name, display_name, role in DEMO_ACCOUNTS
    ]
    session.add_all(users)
    await session.flush()
    admin = users[0]
    audit.record(
        session, admin.username, "demo_accounts_seeded", "user", admin.id, usernames=[u.username for u in users]
    )
    await session.commit()
    return admin


class DemoAccount(BaseModel):
    username: str
    display_name: str
    role: Role
    password: str


@router.get("/demo-accounts")
async def demo_accounts(request: Request, session: SessionDep) -> list[DemoAccount]:
    """The seeded demo accounts, with passwords, for one-click sign-in. Empty unless DEMO_QUICK_LOGIN
    is on, and lists only accounts that still exist and are active."""
    settings: Settings = request.app.state.settings
    if not settings.demo_quick_login:
        return []
    users = await session.scalars(
        select(User).where(User.username.in_(demo_usernames(settings)), User.is_active.is_(True))
    )
    by_name = {u.username: u for u in users}
    return [
        DemoAccount(
            username=user.username,
            display_name=user.display_name,
            role=Role(user.role),
            password=settings.demo_password.get_secret_value(),
        )
        for name in demo_usernames(settings)
        if (user := by_name.get(name)) is not None
    ]


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> SessionOut:
    settings: Settings = request.app.state.settings
    username = body.username.strip()
    user = await find_user(session, username)
    if user is None:
        user = await _bootstrap_demo_accounts(session, settings, username, body.password)
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
