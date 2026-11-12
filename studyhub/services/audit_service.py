from studyhub.extensions import db
from studyhub.models.audit import AuditLog

class AuditService:
    """Audit logging service for security, authentication, and administrative actions."""

    @classmethod
    def log(
        cls,
        action: str,
        tenant_id: str = None,
        actor_user_id: str = None,
        target_type: str = None,
        target_id: str = None,
        description: str = None,
        ip_address: str = None
    ):
        log_entry = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            ip_address=ip_address
        )
        db.session.add(log_entry)
        db.session.commit()

    @classmethod
    def get_tenant_logs(cls, tenant_id: str, limit: int = 50) -> list[AuditLog]:
        return db.session.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()

    @classmethod
    def get_all_platform_logs(cls, limit: int = 100) -> list[AuditLog]:
        return db.session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
