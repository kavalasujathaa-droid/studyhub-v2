import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db
from studyhub.models.metadata import subject_categories, subject_tags, pdf_tags

class Subject(db.Model):
    """Shared curriculum subjects available to all administrators and users."""
    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="bi-journal-bookmark")
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by_admin_id])
    categories = relationship("Category", secondary=subject_categories, back_populates="subjects")
    tags = relationship("Tag", secondary=subject_tags, back_populates="subjects")
    titles = relationship("SubjectTitle", back_populates="subject", cascade="all, delete-orphan")
    pdf_materials = relationship("PdfMaterial", back_populates="subject", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_subjects_published_deleted", "is_published", "deleted_at"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<Subject {self.subject_name}>"


class SubjectTitle(db.Model):
    """Shared playlist-style titles / units under a subject."""
    __tablename__ = "subject_titles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String(36), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    title_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # Relationships
    subject = relationship("Subject", back_populates="titles")
    creator = relationship("User", foreign_keys=[created_by_admin_id])
    pdf_materials = relationship("PdfMaterial", back_populates="title_ref", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("subject_id", "title_name", name="uq_subject_title_name"),
        Index("ix_titles_subject_published", "subject_id", "is_published", "deleted_at"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<SubjectTitle {self.title_name} subject={self.subject_id}>"


class PdfMaterial(db.Model):
    """Shared educational PDF material visible to all authenticated users."""
    __tablename__ = "pdf_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String(36), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id: Mapped[str] = mapped_column(String(36), ForeignKey("subject_titles.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Enhanced attributes
    language: Mapped[str | None] = mapped_column(String(50), nullable=True, default="English")
    academic_year: Mapped[str | None] = mapped_column(String(50), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # Relationships
    subject = relationship("Subject", back_populates="pdf_materials")
    title_ref = relationship("SubjectTitle", back_populates="pdf_materials")
    uploader = relationship("User", foreign_keys=[uploaded_by_admin_id])
    tags = relationship("Tag", secondary=pdf_tags, back_populates="pdf_materials")
    versions = relationship("PdfVersion", back_populates="pdf_material", cascade="all, delete-orphan", order_by="desc(PdfVersion.created_at)")
    bookmarks = relationship("Bookmark", back_populates="pdf_material", cascade="all, delete-orphan")
    history_entries = relationship("ViewingHistory", back_populates="pdf_material", cascade="all, delete-orphan")
    study_notes = relationship("UserStudyNote", back_populates="pdf_material", cascade="all, delete-orphan")
    reports = relationship("ContentReport", back_populates="pdf_material", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pdfs_published_deleted", "is_published", "deleted_at"),
        Index("ix_pdfs_title_id", "title_id", "is_published"),
        Index("ix_pdfs_uploader", "uploaded_by_admin_id"),
        Index("ix_pdfs_sha256", "sha256"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<PdfMaterial {self.title}>"


class PdfVersion(db.Model):
    """Previous archived revisions for PDF replacement and restoration."""
    __tablename__ = "pdf_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replaced_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    pdf_material = relationship("PdfMaterial", back_populates="versions")
    replacer = relationship("User", foreign_keys=[replaced_by_admin_id])

    def __repr__(self) -> str:
        return f"<PdfVersion v{self.version_number} for pdf={self.pdf_id}>"
