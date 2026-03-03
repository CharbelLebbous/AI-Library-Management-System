"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types once (checkfirst), then reuse column enums with create_type=False
    # to avoid duplicate CREATE TYPE on retried/degraded deploys.
    role_enum_create = postgresql.ENUM("admin", "librarian", "member", name="role")
    book_status_enum_create = postgresql.ENUM("available", "borrowed", name="book_status")

    role_enum_create.create(op.get_bind(), checkfirst=True)
    book_status_enum_create.create(op.get_bind(), checkfirst=True)

    role_enum = postgresql.ENUM("admin", "librarian", "member", name="role", create_type=False)
    book_status_enum = postgresql.ENUM("available", "borrowed", name="book_status", create_type=False)

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("role", role_enum, nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", book_status_enum, nullable=False, server_default="available"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False),
        sa.Column("borrower_name", sa.String(length=255), nullable=False),
        sa.Column("checked_out_by", sa.String(length=255), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("loans")
    op.drop_table("books")
    op.drop_table("users")

    sa.Enum(name="book_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="role").drop(op.get_bind(), checkfirst=True)
