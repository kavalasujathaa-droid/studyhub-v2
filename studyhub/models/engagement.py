import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class Bookmark(db.Model):
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="bookmarks")
    pdf_material = relationship("PdfMaterial", back_populates="bookmarks")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "pdf_id", name="uq_tenant_user_pdf_bookmark"),
        Index("ix_bookmarks_user", "tenant_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Bookmark user={self.user_id} pdf={self.pdf_id} tenant={self.tenant_id}>"


class ViewingHistory(db.Model):
    __tablename__ = "viewing_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_id: Mapped[str] = mapped_column(String(36), ForeignKey("pdf_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="history")
    pdf_material = relationship("PdfMaterial", back_populates="history_entries")

    __table_args__ = (
        Index("ix_history_user_date", "tenant_id", "user_id", "viewed_at"),
    )

    def __repr__(self) -> str:
        return f"<ViewingHistory user={self.user_id} pdf={self.pdf_id} viewed_at={self.viewed_at}>"
