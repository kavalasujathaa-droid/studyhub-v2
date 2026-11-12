import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class Subject(db.Model):
    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="bi-journal-bookmark")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="subjects")
    titles = relationship("SubjectTitle", back_populates="subject", cascade="all, delete-orphan")
    pdf_materials = relationship("PdfMaterial", back_populates="subject", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "subject_name", name="uq_tenant_subject_name"),
        Index("ix_subjects_tenant_published", "tenant_id", "is_published", "deleted_at"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<Subject {self.subject_name} tenant={self.tenant_id}>"


class SubjectTitle(db.Model):
    __tablename__ = "subject_titles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(36), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    title_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="titles")
    subject = relationship("Subject", back_populates="titles")
    pdf_materials = relationship("PdfMaterial", back_populates="title_ref", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "subject_id", "title_name", name="uq_tenant_subject_title_name"),
        Index("ix_titles_tenant_subject_published", "tenant_id", "subject_id", "is_published", "deleted_at"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<SubjectTitle {self.title_name} subject={self.subject_id} tenant={self.tenant_id}>"


class PdfMaterial(db.Model):
    __tablename__ = "pdf_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(36), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id: Mapped[str] = mapped_column(String(36), ForeignKey("subject_titles.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="pdf_materials")
    subject = relationship("Subject", back_populates="pdf_materials")
    title_ref = relationship("SubjectTitle", back_populates="pdf_materials")
    versions = relationship("PdfVersion", back_populates="pdf_material", cascade="all, delete-orphan", order_by="desc(PdfVersion.created_at)")
    bookmarks = relationship("Bookmark", back_populates="pdf_material", cascade="all, delete-orphan")
    history_entries = relationship("ViewingHistory", back_populates="pdf_material", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pdfs_tenant_published", "tenant_id", "is_published", "deleted_at"),
        Index("ix_pdfs_tenant_title", "tenant_id", "title_id", "is_published"),
    )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def __repr__(self) -> str:
        return f"<PdfMaterial {self.title} tenant={self.tenant_id}>"


class PdfVersion(db.Model):
    __tablename__ = "pdf_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    replaced_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    pdf_material = relationship("PdfMaterial", back_populates="versions")

    def __repr__(self) -> str:
        return f"<PdfVersion {self.id} for pdf={self.pdf_id}>"
