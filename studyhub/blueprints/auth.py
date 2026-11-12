from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_user, logout_user, login_required, current_user
from studyhub.extensions import db, limiter
from studyhub.models.user import User
from studyhub.services.auth_service import (
    is_main_admin_initialized,
    bootstrap_main_admin,
    verify_password,
    hash_password,
)
from studyhub.services.audit_service import AuditService

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-time Main Administrator setup using OWNER_BOOTSTRAP_TOKEN."""
    if is_main_admin_initialized():
        flash("Main Administrator setup is permanently closed.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        token = request.form.get("bootstrap_token", "").strip()
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([token, full_name, username, email, password]):
            flash("All fields are required.", "danger")
            return render_template("auth/setup.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/setup.html")

        try:
            owner = bootstrap_main_admin(
                token=token,
                full_name=full_name,
                username=username,
                email=email,
                password=password,
                ip_address=request.remote_addr
            )
            login_user(owner)
            flash("StudyHub V2 Main Administrator initialized successfully!", "success")
            return redirect(url_for("owner.dashboard"))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/setup.html")

    return render_template("auth/setup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def login():
    """Secure login with rate limiting and Argon2id verification."""
    if current_user.is_authenticated:
        if current_user.is_main_admin():
            return redirect(url_for("owner.dashboard"))
        elif current_user.is_admin():
            return redirect(url_for("admin.dashboard"))
        else:
            return redirect(url_for("student.dashboard"))

    if not is_main_admin_initialized():
        return redirect(url_for("auth.setup"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not identifier or not password:
            flash("Please enter username/email and password.", "danger")
            return render_template("auth/login.html")

        user = db.session.query(User).filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if not user or not verify_password(user.password_hash, password):
            AuditService.log(
                action="login_failed",
                actor_user_id=None,
                description=f"Failed login attempt for identifier: {identifier}",
                ip_address=request.remote_addr
            )
            flash("Invalid credentials. Please verify your details.", "danger")
            return render_template("auth/login.html")

        if not user.is_active:
            flash("Your account has been deactivated. Please contact your administrator.", "danger")
            return render_template("auth/login.html")

        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        login_user(user, remember=remember)

        AuditService.log(
            action="login_success",
            actor_user_id=user.id,
            description=f"User {user.username} logged in successfully.",
            ip_address=request.remote_addr
        )

        if user.must_change_password:
            flash("You must set a new password on your first login.", "warning")
            return redirect(url_for("auth.change_password"))

        if user.is_main_admin():
            return redirect(url_for("owner.dashboard"))
        elif user.is_admin():
            return redirect(url_for("admin.dashboard"))
        else:
            return redirect(url_for("student.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    AuditService.log(
        action="logout",
        actor_user_id=current_user.id,
        description=f"User {current_user.username} logged out.",
        ip_address=request.remote_addr
    )
    logout_user()
    flash("You have been securely logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not verify_password(current_user.password_hash, current_password):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html")

        if len(new_password) < 10:
            flash("New password must be at least 10 characters long.", "danger")
            return render_template("auth/change_password.html")

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return render_template("auth/change_password.html")

        current_user.password_hash = hash_password(new_password)
        current_user.must_change_password = False
        db.session.commit()

        AuditService.log(
            action="password_changed",
            actor_user_id=current_user.id,
            description=f"User {current_user.username} changed their password.",
            ip_address=request.remote_addr
        )

        flash("Your password has been updated successfully.", "success")
        if current_user.is_main_admin():
            return redirect(url_for("owner.dashboard"))
        elif current_user.is_admin():
            return redirect(url_for("admin.dashboard"))
        else:
            return redirect(url_for("student.dashboard"))

    return render_template("auth/change_password.html")
