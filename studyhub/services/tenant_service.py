import re
import uuid
from datetime import datetime, timezone
from sqlalchemy import func
from studyhub.extensions import db
from studyhub.models.tenant import Tenant
from studyhub.models.user import User
from studyhub.models.content import PdfMaterial, PdfVersion, Subject, SubjectTitle
from studyhub.models.audit import AuditLog
from studyhub.services.auth_service import hash_password

def slugify(text: str) -> str:
    """Generates an alphanumeric URL-safe slug."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", text)

class TenantService:
    """Manages platform-level tenant creation and administrative accounts."""

    @classmethod
    def create_tenant_and_admin(
        cls,
        owner_id: str,
        tenant_name: str,
        admin_full_name: str,
        username: str,
        email: str,
        password: str,
        ip_address: str = None
    ) -> tuple[Tenant, User]:
        """
        Creates a new tenant and its administrator in an atomic transaction.
        Enforces 1:1 tenant-to-admin association.
        """
        clean_username = username.strip().lower()
        clean_email = email.strip().lower()

        # Check for username / email conflict
        if db.session.query(User).filter((User.username == clean_username) | (User.email == clean_email)).first():
            raise ValueError("Username or email is already in use by another user.")

        base_slug = slugify(tenant_name)
        slug = base_slug
        counter = 1
        while db.session.query(Tenant).filter_by(tenant_slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Create Tenant
        tenant = Tenant(
            tenant_name=tenant_name.strip(),
            tenant_slug=slug,
            created_by_owner_id=owner_id,
            status="active"
        )
        db.session.add(tenant)
        db.session.flush() # Populate tenant.id

        # Create Administrator
        admin = User(
            tenant_id=tenant.id,
            full_name=admin_full_name.strip(),
            username=clean_username,
            email=clean_email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            must_change_password=True,
            created_by=owner_id
        )
        db.session.add(admin)
        db.session.flush()

        # Audit
        audit = AuditLog(
            tenant_id=tenant.id,
            actor_user_id=owner_id,
            action="tenant_and_admin_created",
            target_type="tenant",
            target_id=tenant.id,
            description=f"Created tenant '{tenant.tenant_name}' with administrator '{admin.username}'",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()

        return tenant, admin

    @classmethod
    def get_all_tenants(cls) -> list[Tenant]:
        """Returns all tenants for Platform Owner overview."""
        return db.session.query(Tenant).order_by(Tenant.created_at.desc()).all()

    @classmethod
    def get_all_admins(cls) -> list[User]:
        """Returns all admin users for Platform Owner overview."""
        return db.session.query(User).filter_by(role="admin").order_by(User.created_at.desc()).all()

    @classmethod
    def get_tenant_by_id(cls, tenant_id: str) -> Tenant | None:
        return db.session.get(Tenant, tenant_id)

    @classmethod
    def toggle_tenant_status(cls, tenant_id: str, new_status: str, actor_id: str, ip_address: str = None) -> Tenant:
        if new_status not in ["active", "suspended", "deactivated"]:
            raise ValueError("Invalid tenant status.")
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant not found.")
        tenant.status = new_status
        
        audit = AuditLog(
            tenant_id=tenant.id,
            actor_user_id=actor_id,
            action="tenant_status_changed",
            target_type="tenant",
            target_id=tenant.id,
            description=f"Tenant status changed to {new_status}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
        return tenant

    @classmethod
    def reset_admin_password(cls, admin_id: str, new_password: str, actor_id: str, ip_address: str = None):
        admin = db.session.get(User, admin_id)
        if not admin or admin.role != "admin":
            raise ValueError("Admin account not found.")
        
        admin.password_hash = hash_password(new_password)
        admin.must_change_password = True
        
        audit = AuditLog(
            tenant_id=admin.tenant_id,
            actor_user_id=actor_id,
            action="admin_password_reset",
            target_type="user",
            target_id=admin.id,
            description=f"Password reset for admin {admin.username}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()

    @classmethod
    def get_platform_global_stats(cls) -> dict:
        """Global aggregate statistics for Platform Owner (metadata counts only, no private contents)."""
        total_tenants = db.session.query(func.count(Tenant.id)).scalar() or 0
        active_tenants = db.session.query(func.count(Tenant.id)).filter_by(status="active").scalar() or 0
        total_admins = db.session.query(func.count(User.id)).filter_by(role="admin").scalar() or 0
        total_students = db.session.query(func.count(User.id)).filter_by(role="student").scalar() or 0
        total_materials = db.session.query(func.count(PdfMaterial.id)).filter(PdfMaterial.deleted_at.is_(None)).scalar() or 0
        
        storage_materials = db.session.query(func.coalesce(func.sum(PdfMaterial.file_size), 0)).filter(PdfMaterial.deleted_at.is_(None)).scalar() or 0
        storage_versions = db.session.query(func.coalesce(func.sum(PdfVersion.file_size), 0)).scalar() or 0
        total_storage_bytes = storage_materials + storage_versions

        return {
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "total_admins": total_admins,
            "total_students": total_students,
            "total_materials": total_materials,
            "total_storage_bytes": total_storage_bytes,
            "total_storage_mb": round(total_storage_bytes / (1024 * 1024), 2),
            "total_storage_gb": round(total_storage_bytes / (1024 * 1024 * 1024), 3)
        }
