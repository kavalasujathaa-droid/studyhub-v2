import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class Tenant(db.Model):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_name: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_by_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, suspended, deactivated
    storage_limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=9663676416) # 9 GiB
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan", foreign_keys="User.tenant_id")
    subjects = relationship("Subject", back_populates="tenant", cascade="all, delete-orphan")
    titles = relationship("SubjectTitle", back_populates="tenant", cascade="all, delete-orphan")
    pdf_materials = relationship("PdfMaterial", back_populates="tenant", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tenants_status", "status"),
    )

    def is_active(self) -> bool:
        return self.status == "active"

    def __repr__(self) -> str:
        return f"<Tenant {self.tenant_name} ({self.tenant_slug})>"
