from studyhub.extensions import db
from studyhub.models.user import User
from studyhub.models.audit import AuditLog
from studyhub.services.auth_service import hash_password

class StudentService:
    """Manages student accounts strictly scoped to the administrator's tenant."""

    @classmethod
    def create_student(
        cls,
        tenant_id: str,
        admin_id: str,
        full_name: str,
        username: str,
        email: str,
        password: str,
        ip_address: str = None
    ) -> User:
        clean_username = username.strip().lower()
        clean_email = email.strip().lower()

        # Check for username / email conflict globally
        if db.session.query(User).filter((User.username == clean_username) | (User.email == clean_email)).first():
            raise ValueError("Username or email is already taken.")

        student = User(
            tenant_id=tenant_id,
            full_name=full_name.strip(),
            username=clean_username,
            email=clean_email,
            password_hash=hash_password(password),
            role="student",
            is_active=True,
            must_change_password=True,
            created_by=admin_id
        )
        db.session.add(student)

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            action="student_created",
            target_type="user",
            target_id=student.id,
            description=f"Admin created student account: {student.username}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
        return student

    @classmethod
    def get_students_for_tenant(cls, tenant_id: str, search_query: str = None) -> list[User]:
        query = db.session.query(User).filter(
            User.tenant_id == tenant_id,
            User.role == "student"
        )
        if search_query:
            term = f"%{search_query.strip().lower()}%"
            query = query.filter(
                (User.username.ilike(term)) |
                (User.full_name.ilike(term)) |
                (User.email.ilike(term))
            )
        return query.order_by(User.created_at.desc()).all()

    @classmethod
    def get_student_by_id(cls, tenant_id: str, student_id: str) -> User | None:
        """Tenant-isolated retrieval: never returns students from other tenants."""
        return db.session.query(User).filter(
            User.tenant_id == tenant_id,
            User.id == student_id,
            User.role == "student"
        ).first()

    @classmethod
    def update_student(
        cls,
        tenant_id: str,
        student_id: str,
        full_name: str = None,
        is_active: bool = None
    ) -> User:
        student = cls.get_student_by_id(tenant_id, student_id)
        if not student:
            raise ValueError("Student not found in your tenant.")

        if full_name:
            student.full_name = full_name.strip()
        if is_active is not None:
            student.is_active = is_active

        db.session.commit()
        return student

    @classmethod
    def reset_student_password(cls, tenant_id: str, student_id: str, new_password: str, admin_id: str):
        student = cls.get_student_by_id(tenant_id, student_id)
        if not student:
            raise ValueError("Student not found in your tenant.")

        student.password_hash = hash_password(new_password)
        student.must_change_password = True

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            action="student_password_reset",
            target_type="user",
            target_id=student.id,
            description=f"Admin reset password for student: {student.username}"
        )
        db.session.add(audit)
        db.session.commit()

    @classmethod
    def toggle_student_status(cls, tenant_id: str, student_id: str, is_active: bool, admin_id: str):
        student = cls.get_student_by_id(tenant_id, student_id)
        if not student:
            raise ValueError("Student not found in your tenant.")

        student.is_active = is_active
        action_name = "student_activated" if is_active else "student_deactivated"

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            action=action_name,
            target_type="user",
            target_id=student.id,
            description=f"Student account {'activated' if is_active else 'deactivated'}: {student.username}"
        )
        db.session.add(audit)
        db.session.commit()
