from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from studyhub.services.auth_service import role_required
from studyhub.services.tenant_service import TenantService
from studyhub.services.audit_service import AuditService

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")

@owner_bp.route("/dashboard")
@role_required("platform_owner")
def dashboard():
    """Platform Owner overview dashboard."""
    stats = TenantService.get_platform_global_stats()
    recent_tenants = TenantService.get_all_tenants()[:5]
    recent_logs = AuditService.get_all_platform_logs(limit=10)
    return render_template(
        "owner/dashboard.html",
        stats=stats,
        recent_tenants=recent_tenants,
        recent_logs=recent_logs
    )

@owner_bp.route("/admins", methods=["GET", "POST"])
@role_required("platform_owner")
def admins():
    """List all administrators and create new administrator + tenant."""
    if request.method == "POST":
        tenant_name = request.form.get("tenant_name", "").strip()
        admin_full_name = request.form.get("admin_full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not all([tenant_name, admin_full_name, username, email, password]):
            flash("All fields are required to create a new tenant library.", "danger")
            return redirect(url_for("owner.admins"))

        try:
            tenant, admin = TenantService.create_tenant_and_admin(
                owner_id=current_user.id,
                tenant_name=tenant_name,
                admin_full_name=admin_full_name,
                username=username,
                email=email,
                password=password,
                ip_address=request.remote_addr
            )
            flash(f"Successfully provisioned Tenant '{tenant.tenant_name}' with Admin '{admin.username}'!", "success")
            return redirect(url_for("owner.admins"))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("owner.admins"))

    all_admins = TenantService.get_all_admins()
    return render_template("owner/admins.html", admins=all_admins)

@owner_bp.route("/admins/<admin_id>/reset-password", methods=["POST"])
@role_required("platform_owner")
def reset_admin_password(admin_id):
    """Resets an administrator's password."""
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("owner.admins"))

    try:
        TenantService.reset_admin_password(
            admin_id=admin_id,
            new_password=new_password,
            actor_id=current_user.id,
            ip_address=request.remote_addr
        )
        flash("Admin password has been reset. User must change it on next login.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("owner.admins"))

@owner_bp.route("/tenants")
@role_required("platform_owner")
def tenants():
    """List all tenants with status and storage quotas."""
    all_tenants = TenantService.get_all_tenants()
    return render_template("owner/tenants.html", tenants=all_tenants)

@owner_bp.route("/tenants/<tenant_id>/status", methods=["POST"])
@role_required("platform_owner")
def toggle_tenant_status(tenant_id):
    """Activates or suspends an institution tenant."""
    new_status = request.form.get("status")
    try:
        TenantService.toggle_tenant_status(
            tenant_id=tenant_id,
            new_status=new_status,
            actor_id=current_user.id,
            ip_address=request.remote_addr
        )
        flash(f"Tenant status updated to {new_status}.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("owner.tenants"))

@owner_bp.route("/audit-logs")
@role_required("platform_owner")
def audit_logs():
    """Platform-wide audit log trail."""
    logs = AuditService.get_all_platform_logs(limit=200)
    return render_template("owner/audit_logs.html", logs=logs)
