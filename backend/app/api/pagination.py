"""Shared list contract: `page` and `page_size` in, `{items, total}` out."""

from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    total: int


class PageParams(BaseModel):
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


PageDep = Annotated[PageParams, Depends(page_params)]
