from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import current_user
from studyhub.extensions import db
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.engagement_service import EngagementService
from studyhub.services.storage_service import StorageService
from studyhub.services.communication_service import CommunicationService
from studyhub.models.metadata import Category, Tag

student_bp = Blueprint("student", __name__, url_prefix="/student")

@student_bp.route("/dashboard")
@role_required("user", "admin", "main_admin")
def dashboard():
    """Personalized student portal dashboard with interest-based recommendations."""
    recommended_subjects = EngagementService.get_recommended_subjects(current_user.id, limit=6)
    recommended_pdfs = EngagementService.get_recommended_pdfs(current_user.id, limit=6)
    continue_reading = EngagementService.get_continue_reading_materials(current_user.id, limit=4)
    recent_materials = ContentService.get_recent_materials(limit=6, published_only=True)
    popular_materials = ContentService.get_popular_materials(limit=6, published_only=True)
    bookmarks = EngagementService.get_user_bookmarks(current_user.id)[:4]
    viewing_history = EngagementService.get_user_viewing_history(current_user.id, limit=4)
    announcements = CommunicationService.get_announcements(limit=3)
    categories = ContentService.get_all_categories()

    return render_template(
        "student/dashboard.html",
        recommended_subjects=recommended_subjects,
        recommended_pdfs=recommended_pdfs,
        continue_reading=continue_reading,
        recent_materials=recent_materials,
        popular_materials=popular_materials,
        bookmarks=bookmarks,
        viewing_history=viewing_history,
        announcements=announcements,
        categories=categories
    )

@student_bp.route("/subjects")
@role_required("user", "admin", "main_admin")
def subjects_list():
    """Browse all published subjects in the shared global library."""
    category_id = request.args.get("category_id", "").strip() or None
    search = request.args.get("q", "").strip() or None

    subjects = ContentService.get_all_subjects(published_only=True, category_id=category_id, search=search)
    categories = ContentService.get_all_categories()

    return render_template(
        "student/subjects_list.html",
        subjects=subjects,
        categories=categories,
        selected_category_id=category_id,
        search_query=search
    )

@student_bp.route("/subjects/<subject_id>")
@role_required("user", "admin", "main_admin")
def subject_detail(subject_id):
    """View published titles in a shared subject."""
    subject = ContentService.get_subject_by_id(subject_id, published_only=True)
    if not subject:
        abort(404)

    titles = ContentService.get_titles_for_subject(subject.id, published_only=True)
    return render_template("student/subject.html", subject=subject, titles=titles)

@student_bp.route("/titles/<title_id>")
@role_required("user", "admin", "main_admin")
def title_detail(title_id):
    """View published PDFs under a title."""
    title = ContentService.get_title_by_id(title_id, published_only=True)
    if not title:
        abort(404)

    # Check parent subject is active & published
    subject = ContentService.get_subject_by_id(title.subject_id, published_only=True)
    if not subject:
        abort(404)

    materials = ContentService.get_materials_for_title(title.id, published_only=True)
    user_bookmarks = set(b.id for b in EngagementService.get_user_bookmarks(current_user.id))

    return render_template(
        "student/title.html",
        subject=subject,
        title=title,
        materials=materials,
        bookmarked_ids=user_bookmarks
    )

@student_bp.route("/materials/<pdf_id>/view")
@role_required("user", "admin", "main_admin")
def view_pdf(pdf_id):
    """
    View PDF online via short-lived presigned GET URL (inline disposition).
    Records viewing history and loads study notes.
    """
    pdf = ContentService.get_material_by_id(pdf_id, published_only=True)
    if not pdf:
        abort(404)

    subject = ContentService.get_subject_by_id(pdf.subject_id, published_only=True)
    title = ContentService.get_title_by_id(pdf.title_id, published_only=True)
    if not subject or not title:
        abort(404)

    # Record view
    EngagementService.record_view(current_user.id, pdf.id)

    # Presigned inline URL
    presigned_url = StorageService.generate_presigned_download_url(
        storage_key=pdf.storage_key,
        filename=pdf.original_filename,
        inline=True
    )

    is_bookmarked = EngagementService.is_bookmarked(current_user.id, pdf.id)
    notes = EngagementService.get_user_notes(current_user.id, pdf_id=pdf.id)
    collections = EngagementService.get_user_collections(current_user.id)

    # Get reading status & last page
    history_entry = EngagementService.get_user_viewing_history(current_user.id, limit=30)
    current_entry = next((h for h in history_entry if h["pdf"].id == pdf.id), None)
    last_page = current_entry["last_page"] if current_entry else 1

    return render_template(
        "student/view_pdf.html",
        pdf=pdf,
        subject=subject,
        title=title,
        pdf_url=presigned_url,
        is_bookmarked=is_bookmarked,
        notes=notes,
        collections=collections,
        last_page=last_page
    )

@student_bp.route("/materials/<pdf_id>/download")
@role_required("user", "admin", "main_admin")
def download_pdf(pdf_id):
    """Download PDF via short-lived presigned GET URL (attachment disposition)."""
    pdf = ContentService.get_material_by_id(pdf_id, published_only=True)
    if not pdf:
        abort(404)

    subject = ContentService.get_subject_by_id(pdf.subject_id, published_only=True)
    title = ContentService.get_title_by_id(pdf.title_id, published_only=True)
    if not subject or not title:
        abort(404)

    ContentService.increment_download_count(pdf.id)
    EngagementService.record_download(current_user.id, pdf.id)

    presigned_url = StorageService.generate_presigned_download_url(
        storage_key=pdf.storage_key,
        filename=pdf.original_filename,
        inline=False
    )
    return redirect(presigned_url)

@student_bp.route("/bookmarks")
@role_required("user", "admin", "main_admin")
def bookmarks():
    """View bookmarked PDFs with optional collection filter."""
    collection_id = request.args.get("collection_id", "").strip() or None
    bookmarks_list = EngagementService.get_user_bookmarks(current_user.id, collection_id=collection_id)
    collections = EngagementService.get_user_collections(current_user.id)

    return render_template(
        "student/bookmarks.html",
        bookmarks=bookmarks_list,
        collections=collections,
        selected_collection_id=collection_id
    )

@student_bp.route("/history")
@role_required("user", "admin", "main_admin")
def history():
    """View recently viewed PDFs and reading progress."""
    history_list = EngagementService.get_user_viewing_history(current_user.id, limit=50)
    return render_template("student/history.html", history=history_list)

@student_bp.route("/downloads")
@role_required("user", "admin", "main_admin")
def downloads():
    """View student download history."""
    downloads_list = EngagementService.get_user_download_history(current_user.id, limit=50)
    return render_template("student/downloads.html", downloads=downloads_list)

@student_bp.route("/notes")
@role_required("user", "admin", "main_admin")
def notes():
    """Manage private personal study notes."""
    search = request.args.get("q", "").strip() or None
    pdf_id = request.args.get("pdf_id", "").strip() or None
    notes_list = EngagementService.get_user_notes(current_user.id, pdf_id=pdf_id, search=search)

    return render_template("student/notes.html", notes=notes_list, search_query=search)

@student_bp.route("/interests", methods=["GET", "POST"])
@role_required("user", "admin", "main_admin")
def interests():
    """Manage personal subject, category, and tag interests."""
    if request.method == "POST":
        subject_ids = request.form.getlist("subject_ids")
        category_ids = request.form.getlist("category_ids")
        tags_raw = request.form.get("tags", "")
        tag_names = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        EngagementService.set_user_interests(
            user_id=current_user.id,
            subject_ids=subject_ids,
            category_ids=category_ids,
            tag_names=tag_names
        )
        flash("Your learning interests have been saved. Your dashboard is now personalized!", "success")
        return redirect(url_for("student.dashboard"))

    current_interests = EngagementService.get_user_interests(current_user.id)
    all_subjects = ContentService.get_all_subjects(published_only=True)
    all_categories = ContentService.get_all_categories()
    all_tags = ContentService.get_all_tags()

    return render_template(
        "student/interests.html",
        current_interests=current_interests,
        all_subjects=all_subjects,
        all_categories=all_categories,
        all_tags=all_tags
    )

@student_bp.route("/notifications")
@role_required("user", "admin", "main_admin")
def notifications():
    """View in-app notifications and announcements."""
    user_notifications = CommunicationService.get_user_notifications(current_user.id, limit=50)
    announcements = CommunicationService.get_announcements(limit=20)
    return render_template("student/notifications.html", notifications=user_notifications, announcements=announcements)

@student_bp.route("/search")
@role_required("user", "admin", "main_admin")
def search():
    """Global search across shared library with filters and pagination."""
    query_str = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", "").strip() or None
    subject_id = request.args.get("subject_id", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    academic_year = request.args.get("academic_year", "").strip() or None
    semester = request.args.get("semester", "").strip() or None
    sort_by = request.args.get("sort_by", "recent").strip()
    page = request.args.get("page", 1, type=int)

    pagination = EngagementService.search_library(
        query_str=query_str,
        category_id=category_id,
        subject_id=subject_id,
        tag=tag,
        academic_year=academic_year,
        semester=semester,
        sort_by=sort_by,
        page=page,
        per_page=12
    )

    categories = ContentService.get_all_categories()
    subjects = ContentService.get_all_subjects(published_only=True)

    return render_template(
        "student/search.html",
        query=query_str,
        pagination=pagination,
        results=pagination.items,
        categories=categories,
        subjects=subjects,
        selected_category_id=category_id,
        selected_subject_id=subject_id,
        selected_tag=tag,
        selected_academic_year=academic_year,
        selected_semester=semester,
        selected_sort_by=sort_by
    )
