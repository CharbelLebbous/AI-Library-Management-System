from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Role(str, enum.Enum):
    admin = "admin"
    librarian = "librarian"
    member = "member"


class BookStatus(str, enum.Enum):
    available = "available"
    borrowed = "borrowed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.member)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    loans: Mapped[list["Loan"]] = relationship(back_populates="checked_out_by_user")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    author: Mapped[str] = mapped_column(String(255), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[BookStatus] = mapped_column(Enum(BookStatus), default=BookStatus.available, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    loans: Mapped[list["Loan"]] = relationship(back_populates="book", cascade="all, delete-orphan")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    borrower_name: Mapped[str] = mapped_column(String(255))
    checked_out_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book: Mapped[Book] = relationship(back_populates="loans")
    checked_out_by_user: Mapped[User] = relationship(back_populates="loans")
