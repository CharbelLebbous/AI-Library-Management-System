from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import BookStatus, Role


class UserOut(BaseModel):
    id: str
    email: str
    role: Role

    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    author: str | None = Field(default=None, min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None
    status: BookStatus | None = None


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    metadata: dict[str, Any] = Field(alias="metadata_json")
    status: BookStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CheckoutRequest(BaseModel):
    borrower_name: str = Field(min_length=1, max_length=255)


class LoanOut(BaseModel):
    id: int
    book_id: int
    borrower_name: str
    checked_out_by: str
    checked_out_at: datetime
    checked_in_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EnrichBookRequest(BaseModel):
    title: str
    author: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnrichBookResponse(BaseModel):
    summary: str
    tags: list[str]


class ChatSearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    conversation_id: str | None = Field(default=None, min_length=8, max_length=128)
    reset: bool = False


class ChatSearchSource(BaseModel):
    book_id: int
    title: str
    author: str
    status: BookStatus
    score: float
    snippet: str


class ChatSearchResponse(BaseModel):
    answer: str
    sources: list[ChatSearchSource] = []
    blocked: bool = False
    reason: str | None = None
    retrieval_method: str = "keyword"
    conversation_id: str
