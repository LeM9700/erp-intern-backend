"""Schémas de pagination réutilisables."""
from pydantic import BaseModel
import math


class PaginationMeta(BaseModel):
    total: int
    page: int
    size: int
    pages: int


def paginate_meta(total: int, page: int, size: int) -> PaginationMeta:
    return PaginationMeta(
        total=total,
        page=page,
        size=size,
        pages=max(1, math.ceil(total / size)),
    )
