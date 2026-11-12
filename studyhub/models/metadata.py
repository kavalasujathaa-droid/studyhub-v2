import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

# Association Table: Subject <-> Category (Many-to-Many)
subject_categories = Table(
    "subject_categories",
    db.metadata,
    Column("subject_id", String(36), ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", String(36), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)

# Association Table: Subject <-> Tag (Many-to-Many)
subject_tags = Table(
    "subject_tags",
    db.metadata,
    Column("subject_id", String(36), ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

# Association Table: PdfMaterial <-> Tag (Many-to-Many)
pdf_tags = Table(
    "pdf_tags",
    db.metadata,
    Column("pdf_id", String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class Category(db.Model):
    """Dynamic organizational categories (e.g. CSE, ECE, Mathematics, Competitive Exams)."""
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="bi-folder")
    created_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    subjects = relationship("Subject", secondary=subject_categories, back_populates="categories")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Tag(db.Model):
    """Dynamic tags for cross-cutting search and discovery."""
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    subjects = relationship("Subject", secondary=subject_tags, back_populates="tags")
    pdf_materials = relationship("PdfMaterial", secondary=pdf_tags, back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"
