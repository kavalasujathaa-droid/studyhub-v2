import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # platform_owner, admin, student
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="users", foreign_keys=[tenant_id])
    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")
    history = relationship("ViewingHistory", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_tenant_role", "tenant_id", "role"),
        Index("ix_users_tenant_active", "tenant_id", "is_active"),
    )

    # Flask-Login integration
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return self.id

    def is_platform_owner(self) -> bool:
        return self.role == "platform_owner"

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_student(self) -> bool:
        return self.role == "student"

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role} tenant={self.tenant_id}>"
