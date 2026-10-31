"""Sign-in, sessions and roles.

A session is a signed token in an httpOnly cookie. Every request loads the user row behind it, so a
deactivated account or a changed role takes effect at once, not when the token expires. Roles are
enforced here and in the routes, never only by hiding interface controls.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from sqlalchemy import select

from app.core.config import Settings
from app.core.enums import ROLE_RANK, Role
from app.core.errors import AppError
from app.db.models import User
from app.db.session import SessionDep

COOKIE_NAME = "azentio_session"
ALGORITHM = "HS256"

# PBKDF2-SHA256 from the standard library: no extra dependency, and strong enough for a demo's
# handful of accounts. The format is self-describing, so the cost can be raised later.
_HASH_SCHEME = "pbkdf2_sha256"
_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _HASH_ITERATIONS)
    return f"{_HASH_SCHEME}${_HASH_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if scheme != _HASH_SCHEME:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def credentials_match(settings: Settings, username: str, password: str) -> bool:
    """The bootstrap login from the environment, used only until the first admin row exists."""
    # Compare both fields in constant time so a wrong username takes as long as a wrong password.
    user_ok = hmac.compare_digest(username.encode(), settings.demo_username.encode())
    password_ok = hmac.compare_digest(password.encode(), settings.demo_password.get_secret_value().encode())
    return user_ok and password_ok


@dataclass(frozen=True)
class Principal:
    """The signed-in person, as the routes see them."""

    id: int
    username: str
    role: str
    display_name: str

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    @property
    def rank(self) -> int:
        return ROLE_RANK.get(self.role, 0)

    def can_escalate_to(self, target: str) -> bool:
        """Only upwards: an analyst to a senior reviewer or an admin, a senior reviewer to an admin."""
        return ROLE_RANK.get(target, 0) > self.rank

    def can_decide(self, escalated_to: str | None, escalated_by: str | None) -> bool:
        """The level it was escalated to, or higher, decides it; never the person who escalated it."""
        level = ROLE_RANK.get(escalated_to or Role.SENIOR_REVIEWER.value, 1)
        return self.rank >= level and escalated_by != self.username


def create_session_token(settings: Settings, user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.session_max_age_minutes),
    }
    return jwt.encode(payload, settings.session_secret.get_secret_value(), algorithm=ALGORITHM)


def _unauthorized(message: str = "Session is invalid or expired") -> AppError:
    return AppError(401, "unauthorized", message)


async def session_principal(request: Request, session: SessionDep) -> Principal:
    """FastAPI dependency: the signed-in user with their current role, or 401."""
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized("Not logged in")
    try:
        payload = jwt.decode(token, settings.session_secret.get_secret_value(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc
    uid = payload.get("uid")
    if not isinstance(uid, int):
        raise _unauthorized()
    user = await session.get(User, uid)
    if user is None or not user.is_active or user.username != payload.get("sub"):
        raise _unauthorized()
    return Principal(id=user.id, username=user.username, role=user.role, display_name=user.display_name)


async def session_username(principal: Annotated[Principal, Depends(session_principal)]) -> str:
    return principal.username


CurrentPrincipal = Annotated[Principal, Depends(session_principal)]

# The name the graph, document, correction and investigation routers guard themselves with.
get_current_user = session_principal
CurrentUser = Annotated[str, Depends(session_username)]


def require_roles(*roles: Role) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """A dependency that admits only the given roles; anyone else gets 403."""
    allowed = {role.value for role in roles}

    async def check(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed:
            raise forbidden("This needs the " + " or ".join(sorted(allowed)) + " role")
        return principal

    return check


def forbidden(message: str) -> AppError:
    return AppError(403, "forbidden", message)


async def find_user(session: Any, username: str) -> User | None:
    return await session.scalar(select(User).where(User.username == username))
