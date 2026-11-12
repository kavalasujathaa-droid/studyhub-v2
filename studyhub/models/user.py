import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from studyhub.extensions import db

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Exactly three roles: main_admin, admin, user
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # main_admin, admin, user
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Creator tracking: Main Admin creates Admin; Admin creates User (Student)
    created_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    created_users = relationship("User", foreign_keys=[created_by_admin_id], backref=db.backref("creator_admin", remote_side=[id]))
    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")
    history = relationship("ViewingHistory", back_populates="user", cascade="all, delete-orphan")
    study_notes = relationship("UserStudyNote", back_populates="user", cascade="all, delete-orphan")
    download_history = relationship("UserDownloadHistory", back_populates="user", cascade="all, delete-orphan")
    interests = relationship("UserInterest", back_populates="user", cascade="all, delete-orphan")
    bookmark_collections = relationship("BookmarkCollection", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_role_active", "role", "is_active"),
        Index("ix_users_creator", "created_by_admin_id"),
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

    def is_main_admin(self) -> bool:
        return self.role in ["main_admin", "platform_owner"]

    # Backward compatibility alias
    def is_platform_owner(self) -> bool:
        return self.is_main_admin()

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_user(self) -> bool:
        return self.role in ["user", "student"]

    # Backward compatibility alias
    def is_student(self) -> bool:
        return self.is_user()

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"
