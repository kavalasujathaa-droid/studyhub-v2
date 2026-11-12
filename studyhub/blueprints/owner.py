from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import current_user
from studyhub.extensions import db
from studyhub.models.user import User
from studyhub.models.content import Subject, PdfMaterial
from studyhub.models.metadata import Category
from studyhub.services.auth_service import role_required, hash_password
from studyhub.services.content_service import ContentService
from studyhub.services.communication_service import CommunicationService
from studyhub.services.backup_service import BackupService
from studyhub.services.audit_service import AuditService

owner_bp = Blueprint("owner", __name__, url_prefix="/main-admin")

@owner_bp.route("/dashboard")
@role_required("main_admin")
def dashboard():
    """Main Administrator platform overview."""
    stats = ContentService.get_platform_analytics()
    recent_reports = CommunicationService.get_all_reports(status="pending")[:5]
    recent_logs = AuditService.get_all_platform_logs(limit=10)
    announcements = CommunicationService.get_announcements(limit=5)

    return render_template(
        "owner/dashboard.html",
        stats=stats,
        recent_reports=recent_reports,
        recent_logs=recent_logs,
        announcements=announcements
    )

@owner_bp.route("/admins", methods=["GET", "POST"])
@role_required("main_admin")
def admins():
    """Create and manage institutional administrators."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not all([full_name, username, email, password]):
            flash("All fields are required.", "danger")
            return redirect(url_for("owner.admins"))

        existing = db.session.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing:
            flash("Username or email is already taken.", "danger")
            return redirect(url_for("owner.admins"))

        admin = User(
            full_name=full_name,
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            must_change_password=True,
            created_by_admin_id=current_user.id
        )
        db.session.add(admin)
        db.session.commit()

        AuditService.log(
            action="admin_created",
            actor_user_id=current_user.id,
            target_type="user",
            target_id=admin.id,
            description=f"Created administrator account: {admin.username}",
            ip_address=request.remote_addr
        )
        flash(f"Administrator '{admin.username}' created successfully!", "success")
        return redirect(url_for("owner.admins"))

    all_admins = db.session.query(User).filter_by(role="admin").order_by(User.created_at.desc()).all()
    return render_template("owner/admins.html", admins=all_admins)

@owner_bp.route("/admins/<admin_id>/reset-password", methods=["POST"])
@role_required("main_admin")
def reset_admin_password(admin_id):
    admin = db.session.get(User, admin_id)
    if not admin or admin.role != "admin":
        flash("Admin not found.", "danger")
        return redirect(url_for("owner.admins"))

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("owner.admins"))

    admin.password_hash = hash_password(new_password)
    admin.must_change_password = True
    db.session.commit()

    AuditService.log(
        action="admin_password_reset",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=admin.id,
        description=f"Reset password for admin: {admin.username}",
        ip_address=request.remote_addr
    )
    flash(f"Password reset for {admin.username}.", "success")
    return redirect(url_for("owner.admins"))

@owner_bp.route("/admins/<admin_id>/toggle-status", methods=["POST"])
@role_required("main_admin")
def toggle_admin_status(admin_id):
    admin = db.session.get(User, admin_id)
    if not admin or admin.role != "admin":
        flash("Admin not found.", "danger")
        return redirect(url_for("owner.admins"))

    admin.is_active = not admin.is_active
    db.session.commit()
    flash(f"Administrator {admin.username} {'activated' if admin.is_active else 'deactivated'}.", "info")
    return redirect(url_for("owner.admins"))

@owner_bp.route("/categories", methods=["GET", "POST"])
@role_required("main_admin")
def categories():
    """Manage dynamic categories."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        desc = request.form.get("description", "").strip()
        icon = request.form.get("icon", "bi-folder").strip()

        if not name:
            flash("Category name is required.", "danger")
        else:
            try:
                ContentService.get_or_create_category(
                    name=name,
                    description=desc,
                    icon=icon,
                    creator_id=current_user.id
                )
                flash(f"Category '{name}' created/updated.", "success")
            except Exception as e:
                flash(str(e), "danger")
        return redirect(url_for("owner.categories"))

    all_cats = ContentService.get_all_categories()
    return render_template("owner/categories.html", categories=all_cats)

@owner_bp.route("/announcements", methods=["GET", "POST"])
@role_required("main_admin")
def announcements():
    """Publish and manage platform announcements."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        is_pinned = bool(request.form.get("is_pinned"))

        if not title or not content:
            flash("Title and content are required.", "danger")
        else:
            CommunicationService.create_announcement(
                author_id=current_user.id,
                title=title,
                content=content,
                is_pinned=is_pinned
            )
            flash("Announcement published successfully!", "success")
        return redirect(url_for("owner.announcements"))

    all_announcements = CommunicationService.get_announcements(limit=50)
    return render_template("owner/announcements.html", announcements=all_announcements)

@owner_bp.route("/moderation")
@role_required("main_admin")
def moderation():
    """Review and resolve content reports submitted by users."""
    status_filter = request.args.get("status")
    reports = CommunicationService.get_all_reports(status=status_filter)
    return render_template("owner/moderation.html", reports=reports, current_filter=status_filter)

@owner_bp.route("/moderation/<report_id>/resolve", methods=["POST"])
@role_required("main_admin")
def resolve_report(report_id):
    action = request.form.get("action")
    notes = request.form.get("admin_notes", "").strip()
    try:
        CommunicationService.resolve_report(
            report_id=report_id,
            resolver_user=current_user,
            action=action,
            admin_notes=notes
        )
        flash("Content report updated.", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("owner.moderation"))

@owner_bp.route("/recovery")
@role_required("main_admin")
def recovery():
    """Soft-deleted subjects and PDF materials recovery console."""
    deleted_subjects = db.session.query(Subject).filter(Subject.deleted_at.is_not(None)).all()
    deleted_pdfs = db.session.query(PdfMaterial).filter(PdfMaterial.deleted_at.is_not(None)).all()
    return render_template("owner/recovery.html", subjects=deleted_subjects, pdfs=deleted_pdfs)

@owner_bp.route("/recovery/subject/<subject_id>/restore", methods=["POST"])
@role_required("main_admin")
def restore_subject(subject_id):
    try:
        ContentService.restore_subject(subject_id, current_user)
        flash("Subject restored successfully.", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("owner.recovery"))

@owner_bp.route("/recovery/pdf/<pdf_id>/restore", methods=["POST"])
@role_required("main_admin")
def restore_pdf(pdf_id):
    try:
        ContentService.restore_material(pdf_id, current_user)
        flash("PDF material restored successfully.", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("owner.recovery"))

@owner_bp.route("/backups")
@role_required("main_admin")
def backups():
    """Backup console and R2 storage inventory."""
    inventory = BackupService.get_storage_inventory()
    stats = ContentService.get_platform_analytics()
    return render_template("owner/backups.html", inventory=inventory, stats=stats)

@owner_bp.route("/backups/export-metadata")
@role_required("main_admin")
def export_metadata():
    """Downloads full library metadata as a JSON file."""
    json_data = BackupService.export_metadata_json()
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=studyhub_metadata_backup.json"}
    )

@owner_bp.route("/audit-logs")
@role_required("main_admin")
def audit_logs():
    logs = AuditService.get_all_platform_logs(limit=200)
    return render_template("owner/audit_logs.html", logs=logs)
