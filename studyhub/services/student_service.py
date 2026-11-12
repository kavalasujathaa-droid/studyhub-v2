import csv
import io
import re
import secrets
import string
from studyhub.extensions import db
from studyhub.models.user import User
from studyhub.models.audit import AuditLog
from studyhub.services.auth_service import hash_password

class StudentService:
    """Manages Student User Accounts (strictly scoped to the creating Administrator)."""

    @classmethod
    def create_student(
        cls,
        admin_id: str,
        full_name: str,
        username: str,
        email: str,
        password: str
    ) -> User:
        admin = db.session.get(User, admin_id)
        if not admin or admin.role not in ["admin", "main_admin"]:
            raise ValueError("Only an administrator or Main Admin can create students.")

        clean_username = username.strip().lower()
        clean_email = email.strip().lower()

        if len(clean_username) < 3 or not re.match(r"^[a-zA-Z0-9_.-]+$", clean_username):
            raise ValueError("Username must be at least 3 characters and contain only alphanumeric, dash, dot, or underscore.")

        if len(password) < 8:
            raise ValueError("Student password must be at least 8 characters long.")

        existing = db.session.query(User).filter(
            (User.username == clean_username) | (User.email == clean_email)
        ).first()
        if existing:
            raise ValueError("A user with this username or email already exists on the platform.")

        student = User(
            full_name=full_name.strip(),
            username=clean_username,
            email=clean_email,
            password_hash=hash_password(password),
            role="user",
            is_active=True,
            must_change_password=True,
            created_by_admin_id=admin.id
        )
        db.session.add(student)
        db.session.flush()

        audit = AuditLog(
            actor_user_id=admin.id,
            action="student_created",
            target_type="user",
            target_id=student.id,
            description=f"Admin {admin.username} enrolled student {clean_username}"
        )
        db.session.add(audit)
        db.session.commit()
        return student

    @classmethod
    def get_students_for_admin(cls, admin_id: str, search_query: str = None) -> list[User]:
        """Returns students created by this administrator."""
        query = db.session.query(User).filter(
            User.created_by_admin_id == admin_id,
            User.role.in_(["user", "student"])
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
    def get_all_students(cls, search_query: str = None) -> list[User]:
        """Returns all students across platform for Main Admin."""
        query = db.session.query(User).filter(User.role.in_(["user", "student"]))
        if search_query:
            term = f"%{search_query.strip().lower()}%"
            query = query.filter(
                (User.username.ilike(term)) |
                (User.full_name.ilike(term)) |
                (User.email.ilike(term))
            )
        return query.order_by(User.created_at.desc()).all()

    @classmethod
    def _resolve_admin_user(cls, admin_user: User | str) -> tuple[User | None, str]:
        if isinstance(admin_user, str):
            u = db.session.get(User, admin_user)
            return u, admin_user
        return admin_user, admin_user.id if admin_user else ""

    @classmethod
    def get_student_by_id(cls, student_id: str, admin_user: User | str) -> User | None:
        """Retrieves student with creator permission enforcement."""
        student = db.session.get(User, student_id)
        if not student or student.role not in ["user", "student"]:
            return None

        admin_obj, admin_id = cls._resolve_admin_user(admin_user)
        is_main = admin_obj.is_main_admin() if admin_obj else False

        if not is_main and student.created_by_admin_id != admin_id:
            return None

        return student

    @classmethod
    def update_student(
        cls,
        student_id: str,
        admin_user: User | str,
        full_name: str = None,
        is_active: bool = None
    ) -> User:
        student = cls.get_student_by_id(student_id, admin_user)
        if not student:
            raise PermissionError("Student not found or you lack permission to modify this student.")

        if full_name:
            student.full_name = full_name.strip()
        if is_active is not None:
            student.is_active = is_active

        db.session.commit()
        return student

    @classmethod
    def reset_student_password(cls, student_id: str, admin_user: User | str, new_password: str):
        student = cls.get_student_by_id(student_id, admin_user)
        if not student:
            raise PermissionError("Student not found or you lack permission to reset this password.")

        _, admin_id = cls._resolve_admin_user(admin_user)
        student.password_hash = hash_password(new_password)
        student.must_change_password = True

        audit = AuditLog(
            actor_user_id=admin_id,
            action="student_password_reset",
            target_type="user",
            target_id=student.id,
            description=f"Admin reset password for student: {student.username}"
        )
        db.session.add(audit)
        db.session.commit()

    @classmethod
    def toggle_student_status(cls, student_id: str, admin_user: User | str, is_active: bool):
        student = cls.get_student_by_id(student_id, admin_user)
        if not student:
            raise PermissionError("Student not found or you lack permission to alter this account.")

        _, admin_id = cls._resolve_admin_user(admin_user)
        student.is_active = is_active
        action_name = "student_activated" if is_active else "student_deactivated"

        audit = AuditLog(
            actor_user_id=admin_id,
            action=action_name,
            target_type="user",
            target_id=student.id,
            description=f"Student account {'activated' if is_active else 'deactivated'}: {student.username}"
        )
        db.session.add(audit)
        db.session.commit()

    # =========================================================================
    # BULK CSV IMPORT
    # =========================================================================

    @classmethod
    def generate_random_password(cls, length: int = 10) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @classmethod
    def generate_csv_template(cls) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["full_name", "username", "email", "password"])
        writer.writerow(["Alex Mercer", "alex_m", "alex@example.edu", "TempPass123!"])
        writer.writerow(["Samantha Lee", "slee24", "samantha@example.edu", "TempPass456!"])
        return output.getvalue()

    @classmethod
    def import_students_from_csv(cls, admin_id: str, csv_file_or_content) -> dict:
        """
        Parses CSV, validates duplicate usernames and emails,
        and provisions valid student accounts with temporary passwords.
        Accepts file stream or raw string.
        """
        if hasattr(csv_file_or_content, "read"):
            content = csv_file_or_content.read()
        else:
            content = csv_file_or_content

        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")

        if not content or not content.strip():
            raise ValueError("CSV content is empty.")

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ValueError("CSV must contain columns: full_name, username, email, password")

        field_map = {fn.strip().lower(): fn for fn in reader.fieldnames}
        req_fields = ["full_name", "username", "email"]
        for rf in req_fields:
            if rf not in field_map:
                raise ValueError(f"CSV must contain columns: full_name, username, email, password (missing '{rf}')")

        success_count = 0
        errors = []
        created_records = []
        seen_usernames = set()
        seen_emails = set()

        for row_idx, row in enumerate(reader, start=2):
            fn = row.get(field_map["full_name"], "").strip()
            un = row.get(field_map["username"], "").strip().lower()
            em = row.get(field_map["email"], "").strip().lower()
            pwd = row.get(field_map.get("password", ""), "").strip() if "password" in field_map else None

            if not fn or not un or not em:
                errors.append({"row": row_idx, "error": "Missing full_name, username, or email"})
                continue

            if un in seen_usernames:
                errors.append({"row": row_idx, "error": f"Duplicate username in CSV: '{un}'"})
                continue
            if em in seen_emails:
                errors.append({"row": row_idx, "error": f"Duplicate email in CSV: '{em}'"})
                continue

            existing = db.session.query(User).filter((User.username == un) | (User.email == em)).first()
            if existing:
                errors.append({"row": row_idx, "error": f"Username '{un}' or email '{em}' already exists in database."})
                continue

            seen_usernames.add(un)
            seen_emails.add(em)
            assigned_pwd = pwd if pwd and len(pwd) >= 8 else cls.generate_random_password()

            student = User(
                full_name=fn,
                username=un,
                email=em,
                password_hash=hash_password(assigned_pwd),
                role="user",
                is_active=True,
                must_change_password=True,
                created_by_admin_id=admin_id
            )
            db.session.add(student)
            created_records.append({
                "username": un,
                "email": em,
                "temporary_password": assigned_pwd
            })
            success_count += 1

        db.session.commit()

        if success_count > 0:
            audit = AuditLog(
                actor_user_id=admin_id,
                action="students_bulk_imported",
                target_type="user",
                description=f"Bulk imported {success_count} student accounts via CSV"
            )
            db.session.add(audit)
            db.session.commit()

        return {
            "created_count": success_count,
            "errors": errors,
            "created_records": created_records
        }

    # Alias for convenience
    bulk_import_students = import_students_from_csv
