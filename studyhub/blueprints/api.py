from flask import Blueprint, jsonify, request, abort
from flask_login import current_user, login_required
from studyhub.services.auth_service import role_required
from studyhub.services.content_service import ContentService
from studyhub.services.storage_service import StorageService, StorageQuotaExceededError, InvalidPdfSignatureError
from studyhub.services.engagement_service import EngagementService
from studyhub.services.audit_service import AuditService

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

@api_bp.route("/healthz")
def healthz():
    """Minimal health check endpoint for Render Free."""
    return jsonify({
        "status": "healthy",
        "service": "StudyHub V2",
        "mode": "multi-tenant"
    }), 200

# =============================================================================
# ADMIN STORAGE / UPLOAD APIs
# =============================================================================

@api_bp.route("/subjects/<subject_id>/titles")
@login_required
def get_subject_titles(subject_id):
    """Dynamic titles lookup for admin upload form (strictly tenant-scoped)."""
    if not current_user.is_admin():
        abort(403)
    
    tenant_id = current_user.tenant_id
    titles = ContentService.get_titles_for_subject(tenant_id, subject_id, published_only=False)
    return jsonify({
        "titles": [{"id": t.id, "title_name": t.title_name} for t in titles]
    })

@api_bp.route("/storage/presigned-upload", methods=["POST"])
@login_required
def get_presigned_upload_url():
    """Generates presigned PUT URL for direct browser upload to Cloudflare R2."""
    if not current_user.is_admin():
        abort(403)

    tenant_id = current_user.tenant_id
    data = request.get_json(silent=True) or {}
    
    subject_id = data.get("subject_id")
    title_id = data.get("title_id")
    file_size = int(data.get("file_size", 0))
    filename = data.get("filename", "")

    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are permitted."}), 400

    # Cross-tenant hierarchical verification
    subject = ContentService.get_subject_by_id(tenant_id, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found in your tenant."}), 404

    title = ContentService.get_title_by_id(tenant_id, title_id)
    if not title or title.subject_id != subject.id:
        return jsonify({"error": "Invalid title for the selected subject."}), 404

    try:
        presigned_data = StorageService.generate_presigned_upload_url(
            tenant_id=tenant_id,
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
    Validates R2 object, verifies %PDF- magic bytes signature, and creates DB record.
    """
    if not current_user.is_admin():
        abort(403)

    tenant_id = current_user.tenant_id
    data = request.get_json(silent=True) or {}

    subject_id = data.get("subject_id")
    title_id = data.get("title_id")
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    storage_key = data.get("storage_key", "")
    original_filename = data.get("original_filename", "").strip()
    is_published = bool(data.get("is_published"))

    if not all([subject_id, title_id, title, storage_key, original_filename]):
        return jsonify({"error": "Missing required upload metadata."}), 400

    try:
        # Backend verification on R2
        verified = StorageService.verify_and_inspect_uploaded_pdf(tenant_id, storage_key)
        
        # Create TiDB record
        pdf = ContentService.create_pdf_material(
            tenant_id=tenant_id,
            uploaded_by=current_user.id,
            subject_id=subject_id,
            title_id=title_id,
            title=title,
            description=description,
            storage_key=verified["storage_key"],
            original_filename=original_filename,
            file_size=verified["file_size"],
            sha256=verified["sha256"],
            is_published=is_published
        )

        AuditService.log(
            action="pdf_uploaded",
            tenant_id=tenant_id,
            actor_user_id=current_user.id,
            target_type="pdf_material",
            target_id=pdf.id,
            description=f"Uploaded PDF '{pdf.title}' ({verified['file_size']} bytes)",
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
        # Clean up orphaned object on R2 if DB insertion failed
        StorageService.delete_object(storage_key)
        return jsonify({"error": f"Failed to complete upload: {str(e)}"}), 500

@api_bp.route("/storage/complete-replace", methods=["POST"])
@login_required
def complete_replace():
    """Validates replaced PDF on R2 and updates material with version history."""
    if not current_user.is_admin():
        abort(403)

    tenant_id = current_user.tenant_id
    data = request.get_json(silent=True) or {}

    pdf_id = data.get("pdf_id")
    storage_key = data.get("storage_key")
    original_filename = data.get("original_filename")

    if not all([pdf_id, storage_key, original_filename]):
        return jsonify({"error": "Missing required replacement fields."}), 400

    try:
        verified = StorageService.verify_and_inspect_uploaded_pdf(tenant_id, storage_key)
        updated = ContentService.replace_pdf_material(
            tenant_id=tenant_id,
            replaced_by=current_user.id,
            pdf_id=pdf_id,
            new_storage_key=verified["storage_key"],
            new_original_filename=original_filename,
            new_file_size=verified["file_size"],
            new_sha256=verified["sha256"]
        )

        AuditService.log(
            action="pdf_replaced",
            tenant_id=tenant_id,
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
# STUDENT ENGAGEMENT APIs
# =============================================================================

@api_bp.route("/bookmarks/toggle", methods=["POST"])
@login_required
def toggle_bookmark():
    """Toggles bookmark on a PDF for student."""
    if not current_user.is_student():
        abort(403)

    tenant_id = current_user.tenant_id
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id")

    if not pdf_id:
        return jsonify({"error": "Missing pdf_id"}), 400

    try:
        is_bookmarked = EngagementService.toggle_bookmark(tenant_id, current_user.id, pdf_id)
        return jsonify({"success": True, "bookmarked": is_bookmarked}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
