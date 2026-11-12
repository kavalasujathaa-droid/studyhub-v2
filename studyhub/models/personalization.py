import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class UserInterest(db.Model):
    """User interest preferences (subject, category, tag) used for non-restrictive recommendations."""
    __tablename__ = "user_interests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    interest_type: Mapped[str] = mapped_column(String(20), nullable=False) # 'subject', 'category', 'tag'
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="interests")

    __table_args__ = (
        UniqueConstraint("user_id", "interest_type", "target_id", name="uq_user_interest"),
    )

    def __repr__(self) -> str:
        return f"<UserInterest user={self.user_id} type={self.interest_type} target={self.target_id}>"


class BookmarkCollection(db.Model):
    """Personal folder/collection for organizing user bookmarks."""
    __tablename__ = "bookmark_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="bookmark_collections")
    bookmarks = relationship("Bookmark", back_populates="collection")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_collection_name"),
    )

    def __repr__(self) -> str:
        return f"<BookmarkCollection {self.name} user={self.user_id}>"


class Bookmark(db.Model):
    """User PDF bookmark."""
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bookmark_collections.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="bookmarks")
    pdf_material = relationship("PdfMaterial", back_populates="bookmarks")
    collection = relationship("BookmarkCollection", back_populates="bookmarks")

    __table_args__ = (
        UniqueConstraint("user_id", "pdf_id", name="uq_user_pdf_bookmark"),
        Index("ix_bookmarks_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Bookmark user={self.user_id} pdf={self.pdf_id}>"


class ViewingHistory(db.Model):
    """User PDF viewing history, view count, and study progress."""
    __tablename__ = "viewing_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    last_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reading_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started") # not_started, in_progress, completed
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="history")
    pdf_material = relationship("PdfMaterial", back_populates="history_entries")

    __table_args__ = (
        UniqueConstraint("user_id", "pdf_id", name="uq_user_pdf_history"),
        Index("ix_history_user_last_viewed", "user_id", "last_viewed_at"),
    )

    def __repr__(self) -> str:
        return f"<ViewingHistory user={self.user_id} pdf={self.pdf_id} status={self.reading_status}>"


class UserStudyNote(db.Model):
    """Personal private study notes linked to a PDF."""
    __tablename__ = "user_study_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="study_notes")
    pdf_material = relationship("PdfMaterial", back_populates="study_notes")

    __table_args__ = (
        Index("ix_study_notes_user_pdf", "user_id", "pdf_id"),
    )

    def __repr__(self) -> str:
        return f"<UserStudyNote {self.title} user={self.user_id}>"


class UserDownloadHistory(db.Model):
    """Tracks downloaded PDFs per user."""
    __tablename__ = "user_download_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="download_history")
    pdf_material = relationship("PdfMaterial")

    __table_args__ = (
        Index("ix_downloads_user_date", "user_id", "downloaded_at"),
    )

    def __repr__(self) -> str:
        return f"<UserDownloadHistory user={self.user_id} pdf={self.pdf_id}>"
