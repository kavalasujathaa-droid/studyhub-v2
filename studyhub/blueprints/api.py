from flask import Blueprint, jsonify, request, abort
from flask_login import current_user, login_required
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.storage_service import StorageService, StorageQuotaExceededError, InvalidPdfSignatureError
from studyhub.services.engagement_service import EngagementService
from studyhub.services.communication_service import CommunicationService
from studyhub.services.audit_service import AuditService

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

@api_bp.route("/healthz")
def healthz():
    """Minimal health check endpoint for Render Free."""
    return jsonify({
        "status": "healthy",
        "service": "StudyHub V2",
        "mode": "shared_global_library"
    }), 200

# =============================================================================
# ADMIN STORAGE / UPLOAD APIs
# =============================================================================

@api_bp.route("/subjects/<subject_id>/titles")
@login_required
def get_subject_titles(subject_id):
    """Dynamic titles lookup for admin upload form (shared library)."""
    if not (current_user.is_admin() or current_user.is_main_admin()):
        abort(403)

    titles = ContentService.get_titles_for_subject(subject_id, published_only=False)
    return jsonify({
        "titles": [{"id": t.id, "title_name": t.title_name} for t in titles]
    })

@api_bp.route("/storage/presigned-upload", methods=["POST"])
@login_required
def get_presigned_upload_url():
    """Generates presigned PUT URL for direct browser upload to Cloudflare R2."""
    if not (current_user.is_admin() or current_user.is_main_admin()):
        abort(403)

    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    title_id = data.get("title_id")
    file_size = int(data.get("file_size", 0))
    filename = data.get("filename", "")

    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are permitted."}), 400

    # Hierarchical verification in shared library
    subject = ContentService.get_subject_by_id(subject_id)
    if not subject:
        return jsonify({"error": "Subject not found."}), 404

    title = ContentService.get_title_by_id(title_id)
    if not title or title.subject_id != subject.id:
        return jsonify({"error": "Invalid title for the selected subject."}), 404

    try:
        presigned_data = StorageService.generate_presigned_upload_url(
            estimated_size=file_size
        )
        return jsonify(presigned_data), 200
    except (ValueError, StorageQuotaExceededError) as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/storage/complete-upload", methods=["POST"])
@login_required
def complete_upload():
    """
    Called by frontend after PUT to R2 completes.
    Validates R2 object, verifies %PDF- magic bytes, checks SHA-256 duplicate, and creates DB record.
    """
    if not (current_user.is_admin() or current_user.is_main_admin()):
        abort(403)

    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    title_id = data.get("title_id")
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    storage_key = data.get("storage_key", "")
    original_filename = data.get("original_filename", "").strip()
    is_published = bool(data.get("is_published", True))
    language = data.get("language", "English")
    academic_year = data.get("academic_year")
    semester = data.get("semester")
    tags_raw = data.get("tags", "")
    tag_names = [t.strip().lower() for t in tags_raw.split(",") if t.strip()] if isinstance(tags_raw, str) else tags_raw

    if not all([subject_id, title_id, title, storage_key, original_filename]):
        return jsonify({"error": "Missing required upload metadata."}), 400

    try:
        # Backend verification on R2 (%PDF- signature and SHA-256 calculation)
        verified = StorageService.verify_and_inspect_uploaded_pdf(storage_key)

        # Create record in shared library
        pdf = ContentService.create_pdf_material(
            subject_id=subject_id,
            title_id=title_id,
            title=title,
            description=description,
            storage_key=verified["storage_key"],
            original_filename=original_filename,
            file_size=verified["file_size"],
            sha256=verified["sha256"],
            uploaded_by_admin_id=current_user.id,
            language=language,
            academic_year=academic_year,
            semester=semester,
            is_published=is_published,
            tag_names=tag_names
        )

        AuditService.log(
            action="pdf_uploaded",
            actor_user_id=current_user.id,
            target_type="pdf_material",
            target_id=pdf.id,
            description=f"Uploaded PDF '{pdf.title}' ({verified['file_size']} bytes) to shared library",
            ip_address=request.remote_addr
        )

        return jsonify({
            "success": True,
            "pdf_id": pdf.id,
            "message": "PDF uploaded and verified successfully."
        }), 201

    except (InvalidPdfSignatureError, StorageQuotaExceededError, ValueError, PermissionError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        StorageService.delete_object(storage_key)
        return jsonify({"error": f"Failed to complete upload: {str(e)}"}), 500

@api_bp.route("/storage/complete-replace", methods=["POST"])
@login_required
def complete_replace():
    """Validates replaced PDF on R2 and updates material with version archive."""
    if not (current_user.is_admin() or current_user.is_main_admin()):
        abort(403)

    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")
    storage_key = data.get("storage_key")
    original_filename = data.get("original_filename")

    if not all([pdf_id, storage_key, original_filename]):
        return jsonify({"error": "Missing required replacement fields."}), 400

    try:
        verified = StorageService.verify_and_inspect_uploaded_pdf(storage_key)
        updated = ContentService.replace_pdf_material(
            pdf_id=pdf_id,
            user=current_user,
            new_storage_key=verified["storage_key"],
            new_original_filename=original_filename,
            new_file_size=verified["file_size"],
            new_sha256=verified["sha256"]
        )

        AuditService.log(
            action="pdf_replaced",
            actor_user_id=current_user.id,
            target_type="pdf_material",
            target_id=updated.id,
            description=f"Replaced version for PDF '{updated.title}'",
            ip_address=request.remote_addr
        )

        return jsonify({"success": True, "message": "PDF replaced with version archived."}), 200

    except Exception as e:
        StorageService.delete_object(storage_key)
        return jsonify({"error": str(e)}), 400

# =============================================================================
# STUDENT / USER ENGAGEMENT APIs
# =============================================================================

@api_bp.route("/bookmarks/toggle", methods=["POST"])
@login_required
def toggle_bookmark():
    """Toggles bookmark on a PDF for the user."""
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")
    collection_id = data.get("collection_id")

    if not pdf_id:
        return jsonify({"error": "Missing pdf_id"}), 400

    try:
        is_bookmarked = EngagementService.toggle_bookmark(current_user.id, pdf_id, collection_id)
        return jsonify({"success": True, "bookmarked": is_bookmarked}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@api_bp.route("/bookmark-collections", methods=["POST"])
@login_required
def create_bookmark_collection():
    """Creates a new personal bookmark collection for the user."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()

    if not name:
        return jsonify({"error": "Collection name is required."}), 400

    try:
        col = EngagementService.create_bookmark_collection(current_user.id, name, description)
        return jsonify({
            "success": True,
            "collection": {"id": col.id, "name": col.name, "description": col.description}
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/reading-progress", methods=["POST"])
@login_required
def update_reading_progress():
    """Updates reading progress (current page and completion status) for a PDF."""
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")
    page_number = data.get("page_number", 1)
    reading_status = data.get("reading_status", "in_progress")

    if not pdf_id:
        return jsonify({"error": "Missing pdf_id"}), 400

    EngagementService.record_view(
        user_id=current_user.id,
        pdf_id=pdf_id,
        page_number=int(page_number),
        reading_status=reading_status
    )
    return jsonify({"success": True}), 200

@api_bp.route("/notes", methods=["POST"])
@login_required
def create_study_note():
    """Creates a private study note attached to a PDF."""
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    page_number = data.get("page_number")

    if not all([pdf_id, title, content]):
        return jsonify({"error": "Missing required note fields."}), 400

    try:
        note = EngagementService.create_study_note(
            user_id=current_user.id,
            pdf_id=pdf_id,
            title=title,
            content=content,
            page_number=int(page_number) if page_number else None
        )
        return jsonify({
            "success": True,
            "note": {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "page_number": note.page_number,
                "created_at": note.created_at.strftime("%b %d, %Y")
            }
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/notes/<note_id>", methods=["PUT", "DELETE"])
@login_required
def manage_study_note(note_id):
    """Updates or deletes an existing study note owned by current user."""
    if request.method == "DELETE":
        try:
            EngagementService.delete_study_note(note_id, current_user.id)
            return jsonify({"success": True, "message": "Note deleted."}), 200
        except PermissionError:
            return jsonify({"error": "Permission denied."}), 403

    # PUT
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    page_number = data.get("page_number")

    if not title or not content:
        return jsonify({"error": "Title and content are required."}), 400

    try:
        updated = EngagementService.update_study_note(
            note_id=note_id,
            user_id=current_user.id,
            title=title,
            content=content,
            page_number=int(page_number) if page_number else None
        )
        return jsonify({
            "success": True,
            "note": {
                "id": updated.id,
                "title": updated.title,
                "content": updated.content,
                "page_number": updated.page_number
            }
        }), 200
    except PermissionError:
        return jsonify({"error": "Permission denied."}), 403

@api_bp.route("/reports/submit", methods=["POST"])
@login_required
def submit_content_report():
    """Submits a user report regarding incorrect, corrupted, or infringing content."""
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")
    category = data.get("category", "incorrect_content")
    description = data.get("description", "").strip()

    if not pdf_id or not description:
        return jsonify({"error": "Please provide a reason and description for your report."}), 400

    try:
        report = CommunicationService.submit_report(
            user_id=current_user.id,
            pdf_id=pdf_id,
            category=category,
            description=description
        )
        return jsonify({
            "success": True,
            "message": "Thank you. Your report has been submitted for review.",
            "report_id": report.id
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Marks a single notification as read."""
    CommunicationService.mark_as_read(notification_id, current_user.id)
    return jsonify({"success": True}), 200

@api_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Marks all notifications as read for current user."""
    CommunicationService.mark_all_as_read(current_user.id)
    return jsonify({"success": True}), 200
