from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import Book, BookStatus, Loan, Role, User
from app.schemas import BookCreate, BookOut, BookUpdate, CheckoutRequest, LoanOut

router = APIRouter(prefix="/api/books", tags=["books"])


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.librarian)),
) -> Book:
    book = Book(title=payload.title, author=payload.author, metadata_json=payload.metadata)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.get("", response_model=list[BookOut])
def list_books(
    query: str | None = Query(default=None),
    author: str | None = Query(default=None),
    status_filter: BookStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.librarian, Role.member)),
) -> list[Book]:
    stmt: Select[tuple[Book]] = select(Book)

    if query:
        wildcard = f"%{query.lower()}%"
        stmt = stmt.where((Book.title.ilike(wildcard)) | (Book.author.ilike(wildcard)))
    if author:
        stmt = stmt.where(Book.author.ilike(f"%{author}%"))
    if status_filter:
        stmt = stmt.where(Book.status == status_filter)

    stmt = stmt.order_by(Book.created_at.desc())
    return list(db.scalars(stmt).all())


@router.patch("/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    payload: BookUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.librarian)),
) -> Book:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    if payload.title is not None:
        book.title = payload.title
    if payload.author is not None:
        book.author = payload.author
    if payload.metadata is not None:
        book.metadata_json = payload.metadata
    if payload.status is not None:
        book.status = payload.status

    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
) -> Response:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    db.delete(book)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{book_id}/checkout", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def checkout_book(
    book_id: int,
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.librarian)),
) -> Loan:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    if book.status == BookStatus.borrowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Book already borrowed")

    book.status = BookStatus.borrowed
    loan = Loan(book_id=book.id, borrower_name=payload.borrower_name, checked_out_by=user.id)
    db.add(book)
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


@router.post("/{book_id}/checkin", response_model=LoanOut)
def checkin_book(
    book_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.librarian)),
) -> Loan:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    if book.status == BookStatus.available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Book is already available")

    stmt = (
        select(Loan)
        .where(Loan.book_id == book.id, Loan.checked_in_at.is_(None))
        .order_by(Loan.checked_out_at.desc())
    )
    loan = db.scalar(stmt)
    if not loan:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active loan found")

    book.status = BookStatus.available
    loan.checked_in_at = datetime.now(timezone.utc)
    db.add(book)
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan
