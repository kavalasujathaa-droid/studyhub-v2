from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import current_user
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.student_service import StudentService
from studyhub.services.communication_service import CommunicationService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    """Admin dashboard with analytics on own uploads and students."""
    analytics = ContentService.get_admin_analytics(current_user.id)
    recent_uploads = ContentService.get_admin_uploads(current_user.id, limit=5)
    recent_students = StudentService.get_students_for_admin(current_user.id)[:5]
    pending_reports = CommunicationService.get_reports_for_admin_uploads(current_user.id)

    return render_template(
        "admin/dashboard.html",
        analytics=analytics,
        recent_uploads=recent_uploads,
        recent_students=recent_students,
        pending_reports=pending_reports
    )

# =============================================================================
# STUDENT MANAGEMENT (OWN STUDENTS ONLY)
# =============================================================================

@admin_bp.route("/students", methods=["GET", "POST"])
@role_required("admin")
def students():
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
                admin_id=current_user.id,
                full_name=full_name,
                username=username,
                email=email,
                password=password,
                ip_address=request.remote_addr
            )
            flash(f"Student '{student.username}' enrolled successfully!", "success")
        except ValueError as e:
            flash(str(e), "danger")

        return redirect(url_for("admin.students"))

    student_list = StudentService.get_students_for_admin(current_user.id, search_query=search_q)
    return render_template("admin/students.html", students=student_list, search_query=search_q)

@admin_bp.route("/students/<student_id>/reset-password", methods=["POST"])
@role_required("admin")
def reset_student_password(student_id):
    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("admin.students"))

    try:
        StudentService.reset_student_password(student_id, current_user, new_password)
        flash("Student password updated.", "success")
    except PermissionError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.students"))

@admin_bp.route("/students/<student_id>/toggle-status", methods=["POST"])
@role_required("admin")
def toggle_student_status(student_id):
    is_active = request.form.get("is_active") == "1"
    try:
        StudentService.toggle_student_status(student_id, current_user, is_active)
        flash("Student account status updated.", "success")
    except PermissionError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.students"))

@admin_bp.route("/students/csv-template")
@role_required("admin")
def download_csv_template():
    """Download sample CSV template for bulk student onboarding."""
    csv_data = StudentService.generate_csv_template()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=studyhub_student_import_template.csv"}
    )

@admin_bp.route("/students/import-csv", methods=["POST"])
@role_required("admin")
def import_students_csv():
    """Bulk import students from CSV."""
    if "csv_file" not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("admin.students"))

    file = request.files["csv_file"]
    if not file or not file.filename.endswith(".csv"):
        flash("Please upload a valid .csv file.", "danger")
        return redirect(url_for("admin.students"))

    try:
        result = StudentService.import_students_from_csv(current_user.id, file.stream)
        if result["success_count"] > 0:
            flash(f"Successfully imported {result['success_count']} students!", "success")
        if result["errors"]:
            error_msgs = "; ".join([f"Row {e['row']}: {e['error']}" for e in result["errors"][:5]])
            flash(f"Errors occurred in {len(result['errors'])} rows: {error_msgs}", "warning")
    except Exception as e:
        flash(f"CSV import failed: {str(e)}", "danger")

    return redirect(url_for("admin.students"))

# =============================================================================
# SHARED SUBJECTS & TITLES
# =============================================================================

@admin_bp.route("/subjects", methods=["GET", "POST"])
@role_required("admin")
def subjects():
    cat_id = request.args.get("category")
    search_q = request.args.get("q")

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("subject_name", "").strip()
            desc = request.form.get("description", "").strip()
            icon = request.form.get("icon", "bi-journal-bookmark").strip()
            cover = request.form.get("cover_image_url", "").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))
            category_ids = request.form.getlist("category_ids")

            try:
                ContentService.create_subject(
                    subject_name=name,
                    created_by_admin_id=current_user.id,
                    description=desc,
                    icon=icon,
                    cover_image_url=cover,
                    sort_order=sort_order,
                    is_published=is_published,
                    category_ids=category_ids
                )
                flash(f"Subject '{name}' added to the shared library!", "success")
            except ValueError as e:
                flash(str(e), "danger")

        elif action == "edit":
            subject_id = request.form.get("subject_id")
            name = request.form.get("subject_name", "").strip()
            desc = request.form.get("description", "").strip()
            icon = request.form.get("icon", "bi-journal-bookmark").strip()
            cover = request.form.get("cover_image_url", "").strip()
            sort_order = int(request.form.get("sort_order", 0))
            is_published = bool(request.form.get("is_published"))
            category_ids = request.form.getlist("category_ids")

            try:
                ContentService.update_subject(
                    subject_id=subject_id,
                    user=current_user,
                    subject_name=name,
                    description=desc,
                    icon=icon,
                    cover_image_url=cover,
                    sort_order=sort_order,
                    is_published=is_published,
                    category_ids=category_ids
                )
                flash("Subject updated.", "success")
            except (ValueError, PermissionError) as e:
                flash(str(e), "danger")

        elif action == "delete":
            subject_id = request.form.get("subject_id")
            try:
                ContentService.delete_subject(subject_id, current_user, soft=True)
                flash("Subject archived.", "info")
            except (ValueError, PermissionError) as e:
                flash(str(e), "danger")

        return redirect(url_for("admin.subjects"))

    all_subjects = ContentService.get_all_subjects(published_only=False, category_id=cat_id, search=search_q)
    categories = ContentService.get_all_categories()
    return render_template("admin/subjects.html", subjects=all_subjects, categories=categories, current_cat=cat_id)

@admin_bp.route("/subjects/<subject_id>/titles", methods=["GET", "POST"])
@role_required("admin")
def titles(subject_id):
    subject = ContentService.get_subject_by_id(subject_id)
    if not subject:
        flash("Subject not found.", "danger")
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
                    subject_id=subject.id,
                    title_name=title_name,
                    created_by_admin_id=current_user.id,
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
                    title_id=title_id,
                    user=current_user,
                    title_name=title_name,
                    description=desc,
                    sort_order=sort_order,
                    is_published=is_published
                )
                flash("Title updated.", "success")
            except (ValueError, PermissionError) as e:
                flash(str(e), "danger")

        elif action == "delete":
            title_id = request.form.get("title_id")
            try:
                ContentService.delete_title(title_id, current_user, soft=True)
                flash("Title archived.", "info")
            except (ValueError, PermissionError) as e:
                flash(str(e), "danger")

        return redirect(url_for("admin.titles", subject_id=subject.id))

    title_list = ContentService.get_titles_for_subject(subject.id, published_only=False)
    return render_template("admin/titles.html", subject=subject, titles=title_list)

# =============================================================================
# PDF MATERIALS MANAGEMENT
# =============================================================================

@admin_bp.route("/upload")
@role_required("admin")
def upload():
    subjects = ContentService.get_all_subjects(published_only=False)
    analytics = ContentService.get_admin_analytics(current_user.id)
    return render_template("admin/upload.html", subjects=subjects, analytics=analytics)

@admin_bp.route("/materials")
@role_required("admin")
def materials():
    """View PDF materials with option to filter by own uploads or all shared."""
    view_all = request.args.get("all") == "1"
    if view_all:
        materials_list = ContentService.get_recent_materials(limit=200, published_only=False)
    else:
        materials_list = ContentService.get_admin_uploads(current_user.id, limit=200)

    return render_template("admin/materials.html", materials=materials_list, view_all=view_all)

@admin_bp.route("/materials/<pdf_id>/toggle-publish", methods=["POST"])
@role_required("admin")
def toggle_publish_material(pdf_id):
    pdf = ContentService.get_material_by_id(pdf_id)
    if not pdf:
        abort(404)

    try:
        ContentService.update_material(
            pdf_id=pdf_id,
            user=current_user,
            is_published=not pdf.is_published
        )
        flash(f"Material '{pdf.title}' publication status updated.", "success")
    except PermissionError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.materials"))

@admin_bp.route("/materials/<pdf_id>/delete", methods=["POST"])
@role_required("admin")
def delete_material(pdf_id):
    try:
        ContentService.delete_material(pdf_id, current_user, soft=True)
        flash("PDF material archived.", "info")
    except (ValueError, PermissionError) as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.materials"))

@admin_bp.route("/materials/<pdf_id>/versions")
@role_required("admin")
def material_versions(pdf_id):
    pdf = ContentService.get_material_by_id(pdf_id)
    if not pdf:
        abort(404)
    return render_template("admin/versions.html", pdf=pdf, versions=pdf.versions)

@admin_bp.route("/materials/<pdf_id>/restore-version/<version_id>", methods=["POST"])
@role_required("admin")
def restore_version(pdf_id, version_id):
    try:
        ContentService.restore_pdf_version(pdf_id, version_id, current_user)
        flash("PDF version restored successfully!", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.material_versions", pdf_id=pdf_id))

@admin_bp.route("/reports")
@role_required("admin")
def reports():
    """Content reports on documents uploaded by this admin."""
    reports_list = CommunicationService.get_reports_for_admin_uploads(current_user.id)
    return render_template("admin/reports.html", reports=reports_list)

@admin_bp.route("/reports/<report_id>/resolve", methods=["POST"])
@role_required("admin")
def resolve_report(report_id):
    action = request.form.get("action")
    notes = request.form.get("admin_notes", "").strip()
    try:
        CommunicationService.resolve_report(report_id, current_user, action, notes)
        flash("Report resolved.", "success")
    except Exception as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.reports"))

@admin_bp.route("/storage")
@role_required("admin")
def storage():
    """Contribution analytics and storage capacity."""
    analytics = ContentService.get_admin_analytics(current_user.id)
    stats = {
        "storage_used_mb": analytics["storage_used_mb"],
        "storage_limit_mb": 9216.0
    }
    return render_template("admin/storage.html", stats=stats, analytics=analytics)

@admin_bp.route("/activity")
@role_required("admin")
def activity():
    """Personal audit log of uploads and student enrollments for this admin."""
    from studyhub.models.audit import AuditLog
    from studyhub.extensions import db
    logs = db.session.query(AuditLog).filter_by(actor_user_id=current_user.id).order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template("admin/activity.html", logs=logs)
