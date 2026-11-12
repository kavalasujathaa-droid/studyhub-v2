import hmac
from datetime import datetime, timezone
import argon2
from flask import current_app, abort, redirect, url_for, flash
from flask_login import current_user
from functools import wraps
from studyhub.extensions import db, login_manager
from studyhub.models.user import User
from studyhub.models.audit import AuditLog

# Argon2id password hasher
_hasher = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    type=argon2.Type.ID
)

def hash_password(password: str) -> str:
    """Hashes a password using Argon2id."""
    return _hasher.hash(password)

def verify_password(hash_str: str, password: str) -> bool:
    """Verifies a plain password against an Argon2id hash."""
    try:
        return _hasher.verify(hash_str, password)
    except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError, argon2.exceptions.InvalidHashError):
        return False

def check_needs_rehash(hash_str: str) -> bool:
    return _hasher.check_needs_rehash(hash_str)

@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, user_id)

def is_main_admin_initialized() -> bool:
    """Checks whether the first-time Main Administrator has already been created."""
    count = db.session.query(User).filter(User.role.in_(["main_admin", "platform_owner"])).count()
    return count > 0

# Backward compatibility alias
def is_platform_owner_initialized() -> bool:
    return is_main_admin_initialized()

def bootstrap_main_admin(token: str, full_name: str, username: str, email: str, password: str, ip_address: str = None) -> User:
    """Initializes the single Main Administrator on first deployment. Permanent lock once created."""
    if is_main_admin_initialized():
        raise ValueError("Main Admin setup is permanently closed. An administrator already exists.")

    expected_token = current_app.config.get("OWNER_BOOTSTRAP_TOKEN", "")
    if not expected_token or not hmac.compare_digest(expected_token.strip(), token.strip()):
        raise ValueError("Invalid setup bootstrap token.")

    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")

    admin = User(
        full_name=full_name.strip(),
        username=username.strip().lower(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role="main_admin",
        is_active=True,
        must_change_password=False,
        created_by_admin_id=None
    )
    db.session.add(admin)
    db.session.flush()

    audit = AuditLog(
        actor_user_id=admin.id,
        action="main_admin_bootstrap",
        target_type="user",
        target_id=admin.id,
        description=f"Main Administrator initialized via bootstrap token: {username}",
        ip_address=ip_address
    )
    db.session.add(audit)
    db.session.commit()
    return admin

# Backward compatibility alias
def bootstrap_platform_owner(token: str, full_name: str, username: str, email: str, password: str, ip_address: str = None) -> User:
    return bootstrap_main_admin(token, full_name, username, email, password, ip_address)

def role_required(*allowed_roles):
    """Decorator ensuring current user has one of the specified roles (supporting role aliases)."""
    # Normalize aliases
    normalized_roles = set(allowed_roles)
    if "main_admin" in normalized_roles:
        normalized_roles.add("platform_owner")
    if "platform_owner" in normalized_roles:
        normalized_roles.add("main_admin")
    if "user" in normalized_roles:
        normalized_roles.add("student")
    if "student" in normalized_roles:
        normalized_roles.add("user")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            
            if current_user.role not in normalized_roles:
                abort(403)
                
            if current_user.must_change_password:
                flash("You must update your temporary password before proceeding.", "warning")
                return redirect(url_for("auth.change_password"))
                
            if not current_user.is_active:
                flash("Your account has been deactivated. Please contact support.", "danger")
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator
