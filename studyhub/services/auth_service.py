import hmac
from datetime import datetime, timezone
import argon2
from flask import current_app, abort, redirect, url_for, flash
from flask_login import current_user
from functools import wraps
from studyhub.extensions import db, login_manager
from studyhub.models.user import User
from studyhub.models.tenant import Tenant
from studyhub.models.audit import AuditLog

# Argon2id password hasher with secure modern parameters
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
    """Checks if password hash needs to be recomputed under newer parameters."""
    return _hasher.check_needs_rehash(hash_str)

@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login user loader."""
    return db.session.get(User, user_id)

def is_platform_owner_initialized() -> bool:
    """Checks whether the first-time Platform Owner has already been created."""
    owner_count = db.session.query(User).filter_by(role="platform_owner").count()
    return owner_count > 0

def bootstrap_platform_owner(token: str, full_name: str, username: str, email: str, password: str, ip_address: str = None) -> User:
    """
    Initializes the single Platform Owner on first deployment.
    Permanent lock once created.
    """
    if is_platform_owner_initialized():
        raise ValueError("Platform Owner setup is permanently closed. An owner account already exists.")

    expected_token = current_app.config.get("OWNER_BOOTSTRAP_TOKEN", "")
    if not expected_token or not hmac.compare_digest(expected_token.strip(), token.strip()):
        raise ValueError("Invalid setup bootstrap token.")

    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")

    # Create the owner user
    owner = User(
        full_name=full_name.strip(),
        username=username.strip().lower(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role="platform_owner",
        tenant_id=None,
        is_active=True,
        must_change_password=False,
        created_by="system_bootstrap"
    )
    db.session.add(owner)
    
    # Audit log
    audit = AuditLog(
        tenant_id=None,
        actor_user_id=owner.id,
        action="platform_owner_bootstrap",
        target_type="user",
        target_id=owner.id,
        description=f"Platform Owner initialized via bootstrap token: {username}",
        ip_address=ip_address
    )
    db.session.add(audit)
    db.session.commit()
    return owner

def role_required(*allowed_roles):
    """Decorator ensuring current user has one of the specified roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            
            if current_user.role not in allowed_roles:
                abort(403)
                
            if current_user.must_change_password:
                flash("You must change your temporary password before proceeding.", "warning")
                return redirect(url_for("auth.change_password"))
                
            # If tenant-scoped user (admin or student), verify tenant is active
            if current_user.tenant_id:
                tenant = db.session.get(Tenant, current_user.tenant_id)
                if not tenant or tenant.status != "active":
                    flash("Your institution account is inactive or suspended. Please contact your administrator.", "danger")
                    abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator
