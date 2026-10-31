"""Onboarding and roles. Admin only; every change is audited."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core import audit
from app.core.enums import Role
from app.core.errors import AppError, not_found
from app.core.security import Principal, find_user, hash_password, require_roles
from app.db.models import User
from app.db.session import SessionDep

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_roles(Role.ADMIN))])

Admin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,99}$"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    is_active: bool
    created_by: str | None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN, description="Lowercase letters, digits, dots, dashes")
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=8, max_length=256)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display_name must not be blank")
        return value.strip()


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


def _out(user: User) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.get("")
async def list_users(session: SessionDep) -> list[UserOut]:
    users = await session.scalars(select(User).order_by(User.created_at, User.id))
    return [_out(u) for u in users]


@router.post("", status_code=201)
async def create_user(body: UserCreate, session: SessionDep, admin: Admin) -> UserOut:
    if await find_user(session, body.username) is not None:
        raise AppError(409, "conflict", "That username is taken")
    user = User(
        username=body.username,
        display_name=body.display_name,
        role=body.role.value,
        password_hash=hash_password(body.password),
        created_by=admin.username,
    )
    session.add(user)
    await session.flush()
    audit.record(session, admin.username, "user_created", "user", user.id, username=user.username, role=user.role)
    await session.commit()
    await session.refresh(user)
    return _out(user)


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UserPatch, session: SessionDep, admin: Admin) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("User")
    changes: dict[str, object] = {}
    if user.id == admin.id and (body.is_active is False or (body.role is not None and body.role != Role.ADMIN)):
        # An admin cannot lock themselves out; another admin has to do it.
        raise AppError(409, "conflict", "You cannot remove your own admin access")
    if body.display_name is not None and body.display_name.strip() != user.display_name:
        changes["display_name"] = user.display_name = body.display_name.strip()
    if body.role is not None and body.role.value != user.role:
        changes["role"] = {"from": user.role, "to": body.role.value}
        user.role = body.role.value
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes["password"] = "reset"
    if changes:
        audit.record(session, admin.username, "user_updated", "user", user.id, **changes)
        await session.commit()
        await session.refresh(user)
    return _out(user)
