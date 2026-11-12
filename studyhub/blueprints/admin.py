from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import current_user
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.student_service import StudentService
from studyhub.services.storage_service import StorageService
from studyhub.services.audit_service import AuditService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    """Admin tenant overview dashboard."""
    tenant_id = current_user.tenant_id
    stats = ContentService.get_tenant_content_stats(tenant_id)
    students_count = len(StudentService.get_students_for_tenant(tenant_id))
    recent_materials = ContentService.get_tenant_recent_materials(tenant_id, limit=5, published_only=False)
    recent_logs = AuditService.get_tenant_logs(tenant_id, limit=10)

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        students_count=students_count,
        recent_materials=recent_materials,
        recent_logs=recent_logs
    )

# =============================================================================
# STUDENT MANAGEMENT
# =============================================================================

@admin_bp.route("/students", methods=["GET", "POST"])
@role_required("admin")
def students():
    """Manage students belonging to this admin's tenant."""
    tenant_id = current_user.tenant_id
    search_q = request.args.get("q", "").strip()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not all([full_name, username, email, password]):
            flash("All fields are required.", "danger")
            return redirect(url_for("admin.students"))

        try:
            student = StudentService.create_student(
                tenant_id=tenant_id,
                admin_id=current_user.id,
                full_name=full_name,
                username=username,
                email=email,
                password=password,
                ip_address=request.remote_addr
            )
            flash(f"Student account '{student.username}' created successfully!", "success")
        except ValueError as e:
            flash(str(e), "danger")

        return redirect(url_for("admin.students"))

    student_list = StudentService.get_students_for_tenant(tenant_id, search_query=search_q)
    return render_template("admin/students.html", students=student_list, search_query=search_q)

@admin_bp.route("/students/<student_id>/reset-password", methods=["POST"])
@role_required("admin")
def reset_student_password(student_id):
    """Resets student temporary password."""
    tenant_id = current_user.tenant_id
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("admin.students"))

    try:
        StudentService.reset_student_password(tenant_id, student_id, new_password, current_user.id)
        flash("Student password reset. Student must change it on next login.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.students"))

@admin_bp.route("/students/<student_id>/toggle-status", methods=["POST"])
@role_required("admin")
def toggle_student_status(student_id):
    """Activates or deactivates student account."""
    tenant_id = current_user.tenant_id
    is_active = request.form.get("is_active") == "1"
    try:
        StudentService.toggle_student_status(tenant_id, student_id, is_active, current_user.id)
        flash("Student account status updated.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.students"))

# =============================================================================
# SUBJECT MANAGEMENT
# =============================================================================

@admin_bp.route("/subjects", methods=["GET", "POST"])
@role_required("admin")
def subjects():
    """Manage subjects in this library."""
    tenant_id = current_user.tenant_id

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("subject_name", "").strip()
            desc = request.form.get("description", "").strip()
            icon = request.form.get("icon", "bi-journal-bookmark").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))

            try:
                ContentService.create_subject(
                    tenant_id=tenant_id,
                    created_by=current_user.id,
                    subject_name=name,
                    description=desc,
                    icon=icon,
                    sort_order=sort_order,
                    is_published=is_published
                )
                flash(f"Subject '{name}' created successfully!", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif action == "edit":
            subject_id = request.form.get("subject_id")
            name = request.form.get("subject_name", "").strip()
            desc = request.form.get("description", "").strip()
            icon = request.form.get("icon", "bi-journal-bookmark").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))

            try:
                ContentService.update_subject(
                    tenant_id=tenant_id,
                    subject_id=subject_id,
                    subject_name=name,
                    description=desc,
                    icon=icon,
                    sort_order=sort_order,
                    is_published=is_published
                )
                flash("Subject updated.", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif action == "delete":
            subject_id = request.form.get("subject_id")
            try:
                ContentService.delete_subject(tenant_id, subject_id, soft=True)
                flash("Subject archived.", "info")
            except ValueError as e:
                flash(str(e), "danger")

        return redirect(url_for("admin.subjects"))

    all_subjects = ContentService.get_subjects_for_tenant(tenant_id)
    return render_template("admin/subjects.html", subjects=all_subjects)

# =============================================================================
# TITLE MANAGEMENT
# =============================================================================

@admin_bp.route("/subjects/<subject_id>/titles", methods=["GET", "POST"])
@role_required("admin")
def titles(subject_id):
    """Manage titles under a specific subject."""
    tenant_id = current_user.tenant_id
    subject = ContentService.get_subject_by_id(tenant_id, subject_id)
    if not subject:
        flash("Subject not found in your library.", "danger")
        return redirect(url_for("admin.subjects"))

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            title_name = request.form.get("title_name", "").strip()
            desc = request.form.get("description", "").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))

            try:
                ContentService.create_title(
                    tenant_id=tenant_id,
                    created_by=current_user.id,
                    subject_id=subject.id,
                    title_name=title_name,
                    description=desc,
                    sort_order=sort_order,
                    is_published=is_published
                )
                flash(f"Title '{title_name}' added to {subject.subject_name}!", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif action == "edit":
            title_id = request.form.get("title_id")
            title_name = request.form.get("title_name", "").strip()
            desc = request.form.get("description", "").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))

            try:
                ContentService.update_title(
                    tenant_id=tenant_id,
                    title_id=title_id,
                    title_name=title_name,
                    description=desc,
                    sort_order=sort_order,
                    is_published=is_published
                )
                flash("Title updated.", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif action == "delete":
            title_id = request.form.get("title_id")
            try:
                ContentService.delete_title(tenant_id, title_id, soft=True)
                flash("Title archived.", "info")
            except ValueError as e:
                flash(str(e), "danger")

        return redirect(url_for("admin.titles", subject_id=subject.id))

    title_list = ContentService.get_titles_for_subject(tenant_id, subject.id)
    return render_template("admin/titles.html", subject=subject, titles=title_list)

# =============================================================================
# PDF MATERIALS MANAGEMENT
# =============================================================================

@admin_bp.route("/upload")
@role_required("admin")
def upload():
    """Upload PDF page with interactive presigned R2 uploader."""
    tenant_id = current_user.tenant_id
    subject_list = ContentService.get_subjects_for_tenant(tenant_id)
    stats = ContentService.get_tenant_content_stats(tenant_id)
    return render_template("admin/upload.html", subjects=subject_list, stats=stats)

@admin_bp.route("/materials")
@role_required("admin")
def materials():
    """Table of all materials uploaded in tenant."""
    tenant_id = current_user.tenant_id
    materials_list = ContentService.get_tenant_recent_materials(tenant_id, limit=200, published_only=False)
    return render_template("admin/materials.html", materials=materials_list)

@admin_bp.route("/materials/<pdf_id>/toggle-publish", methods=["POST"])
@role_required("admin")
def toggle_publish_material(pdf_id):
    """Publishes or unpublishes a material."""
    tenant_id = current_user.tenant_id
    pdf = ContentService.get_material_by_id(tenant_id, pdf_id)
    if not pdf:
        abort(404)

    ContentService.update_material_metadata(
        tenant_id=tenant_id,
        pdf_id=pdf_id,
        is_published=not pdf.is_published
    )
    flash(f"Material '{pdf.title}' publication status updated.", "success")
    return redirect(url_for("admin.materials"))

@admin_bp.route("/materials/<pdf_id>/delete", methods=["POST"])
@role_required("admin")
def delete_material(pdf_id):
    """Soft deletes a material."""
    tenant_id = current_user.tenant_id
    try:
        ContentService.delete_material(tenant_id, pdf_id, soft=True)
        flash("PDF material deleted.", "info")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.materials"))

@admin_bp.route("/materials/<pdf_id>/versions")
@role_required("admin")
def material_versions(pdf_id):
    """View version history of replaced materials."""
    tenant_id = current_user.tenant_id
    pdf = ContentService.get_material_by_id(tenant_id, pdf_id)
    if not pdf:
        abort(404)
    return render_template("admin/versions.html", pdf=pdf, versions=pdf.versions)

@admin_bp.route("/storage")
@role_required("admin")
def storage():
    """Detailed storage analytics and usage breakdown."""
    tenant_id = current_user.tenant_id
    stats = ContentService.get_tenant_content_stats(tenant_id)
    return render_template("admin/storage.html", stats=stats)

@admin_bp.route("/activity")
@role_required("admin")
def activity():
    """Tenant activity audit log."""
    tenant_id = current_user.tenant_id
    logs = AuditService.get_tenant_logs(tenant_id, limit=100)
    return render_template("admin/activity.html", logs=logs)
