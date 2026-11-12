from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.engagement_service import EngagementService
from studyhub.services.storage_service import StorageService

student_bp = Blueprint("student", __name__, url_prefix="/student")

@student_bp.route("/dashboard")
@role_required("student")
def dashboard():
    """Student portal dashboard."""
    tenant_id = current_user.tenant_id
    subjects = ContentService.get_subjects_for_tenant(tenant_id, published_only=True)
    recent_materials = ContentService.get_tenant_recent_materials(tenant_id, limit=6, published_only=True)
    bookmarks = EngagementService.get_user_bookmarks(tenant_id, current_user.id)[:4]
    history = EngagementService.get_user_viewing_history(tenant_id, current_user.id, limit=4)

    return render_template(
        "student/dashboard.html",
        subjects=subjects,
        recent_materials=recent_materials,
        bookmarks=bookmarks,
        history=history
    )

@student_bp.route("/subjects/<subject_id>")
@role_required("student")
def subject_detail(subject_id):
    """View published titles in a subject."""
    tenant_id = current_user.tenant_id
    subject = ContentService.get_subject_by_id(tenant_id, subject_id, published_only=True)
    if not subject:
        abort(404)

    titles = ContentService.get_titles_for_subject(tenant_id, subject.id, published_only=True)
    return render_template("student/subject.html", subject=subject, titles=titles)

@student_bp.route("/titles/<title_id>")
@role_required("student")
def title_detail(title_id):
    """View published PDFs under a title."""
    tenant_id = current_user.tenant_id
    title = ContentService.get_title_by_id(tenant_id, title_id, published_only=True)
    if not title:
        abort(404)

    # Check that parent subject is also published & active
    subject = ContentService.get_subject_by_id(tenant_id, title.subject_id, published_only=True)
    if not subject:
        abort(404)

    materials = ContentService.get_materials_for_title(tenant_id, title.id, published_only=True)
    
    # Compute bookmark status for each material
    user_bookmarks = set(b.id for b in EngagementService.get_user_bookmarks(tenant_id, current_user.id))

    return render_template(
        "student/title.html",
        subject=subject,
        title=title,
        materials=materials,
        bookmarked_ids=user_bookmarks
    )

@student_bp.route("/materials/<pdf_id>/view")
@role_required("student")
def view_pdf(pdf_id):
    """View PDF online via short-lived presigned GET URL (inline disposition)."""
    tenant_id = current_user.tenant_id
    pdf = ContentService.get_material_by_id(tenant_id, pdf_id, published_only=True)
    if not pdf:
        abort(404)

    # Verify parent subject and title are published
    subject = ContentService.get_subject_by_id(tenant_id, pdf.subject_id, published_only=True)
    title = ContentService.get_title_by_id(tenant_id, pdf.title_id, published_only=True)
    if not subject or not title:
        abort(404)

    # Record viewing history
    EngagementService.record_view(tenant_id, current_user.id, pdf.id)

    # Generate presigned inline GET URL
    presigned_url = StorageService.generate_presigned_download_url(
        tenant_id=tenant_id,
        storage_key=pdf.storage_key,
        filename=pdf.original_filename,
        inline=True
    )

    is_bookmarked = EngagementService.is_bookmarked(tenant_id, current_user.id, pdf.id)

    return render_template(
        "student/view_pdf.html",
        pdf=pdf,
        subject=subject,
        title=title,
        pdf_url=presigned_url,
        is_bookmarked=is_bookmarked
    )

@student_bp.route("/materials/<pdf_id>/download")
@role_required("student")
def download_pdf(pdf_id):
    """Download PDF via short-lived presigned GET URL (attachment disposition)."""
    tenant_id = current_user.tenant_id
    pdf = ContentService.get_material_by_id(tenant_id, pdf_id, published_only=True)
    if not pdf:
        abort(404)

    # Verify subject and title published
    subject = ContentService.get_subject_by_id(tenant_id, pdf.subject_id, published_only=True)
    title = ContentService.get_title_by_id(tenant_id, pdf.title_id, published_only=True)
    if not subject or not title:
        abort(404)

    ContentService.increment_download_count(tenant_id, pdf.id)

    presigned_url = StorageService.generate_presigned_download_url(
        tenant_id=tenant_id,
        storage_key=pdf.storage_key,
        filename=pdf.original_filename,
        inline=False
    )
    return redirect(presigned_url)

@student_bp.route("/bookmarks")
@role_required("student")
def bookmarks():
    """View bookmarked PDFs."""
    tenant_id = current_user.tenant_id
    bookmarks_list = EngagementService.get_user_bookmarks(tenant_id, current_user.id)
    return render_template("student/bookmarks.html", bookmarks=bookmarks_list)

@student_bp.route("/history")
@role_required("student")
def history():
    """View recently viewed PDFs."""
    tenant_id = current_user.tenant_id
    history_list = EngagementService.get_user_viewing_history(tenant_id, current_user.id, limit=30)
    return render_template("student/history.html", history=history_list)

@student_bp.route("/search")
@role_required("student")
def search():
    """Search library within tenant."""
    tenant_id = current_user.tenant_id
    query_str = request.args.get("q", "").strip()
    results = EngagementService.search_tenant_materials(tenant_id, query_str)
    return render_template("student/search.html", query=query_str, results=results)
