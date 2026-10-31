from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.pagination import Page, PageDep
from app.db.models import Provider, ServiceCode
from app.db.session import SessionDep

router = APIRouter(prefix="/reference", tags=["reference"])


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_id: str
    name: str
    city: str


class ServiceCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    category: str
    repeatable: bool
    min_interval_days: int | None
    max_per_week: int | None


@router.get("/providers")
async def providers(session: SessionDep, page: PageDep) -> Page[ProviderOut]:
    total = await session.scalar(select(func.count()).select_from(Provider))
    rows = await session.scalars(
        select(Provider).order_by(Provider.provider_id).offset(page.offset).limit(page.page_size)
    )
    return Page(items=[ProviderOut.model_validate(r) for r in rows], total=total or 0)


@router.get("/service-codes")
async def service_codes(session: SessionDep, page: PageDep) -> Page[ServiceCodeOut]:
    total = await session.scalar(select(func.count()).select_from(ServiceCode))
    rows = await session.scalars(
        select(ServiceCode).order_by(ServiceCode.code).offset(page.offset).limit(page.page_size)
    )
    return Page(items=[ServiceCodeOut.model_validate(r) for r in rows], total=total or 0)
