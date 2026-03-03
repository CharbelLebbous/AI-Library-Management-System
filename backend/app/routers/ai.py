from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat_search_books, enrich_book_payload
from app.auth import require_roles
from app.db import get_db
from app.models import Book, Role, User
from app.schemas import (
    ChatSearchRequest,
    ChatSearchResponse,
    EnrichBookRequest,
    EnrichBookResponse,
)

router = APIRouter(prefix="/api/ai/books", tags=["ai-books"])


@router.post("/enrich", response_model=EnrichBookResponse)
def enrich_book(
    payload: EnrichBookRequest,
    _: User = Depends(require_roles(Role.admin, Role.librarian, Role.member)),
    __: Session = Depends(get_db),
) -> EnrichBookResponse:
    enriched = enrich_book_payload(payload.title, payload.author, payload.metadata)
    return EnrichBookResponse(**enriched)


@router.post("/chat-search", response_model=ChatSearchResponse)
def chat_search(
    payload: ChatSearchRequest,
    _: User = Depends(require_roles(Role.admin, Role.librarian, Role.member)),
    db: Session = Depends(get_db),
) -> ChatSearchResponse:
    books = list(db.scalars(select(Book)).all())
    result = chat_search_books(
        payload.question,
        books,
        conversation_id=payload.conversation_id,
        reset=payload.reset,
    )
    return ChatSearchResponse(**result)
