from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import COOKIE_NAME, CurrentUser, create_session_token, credentials_match

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    username: str


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response) -> SessionOut:
    settings: Settings = request.app.state.settings
    if not credentials_match(settings, body.username.strip(), body.password):
        raise AppError(401, "invalid_credentials", "Invalid username or password")
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(settings, settings.demo_username),
        max_age=settings.session_max_age_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionOut(username=settings.demo_username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(username: CurrentUser) -> SessionOut:
    return SessionOut(username=username)
