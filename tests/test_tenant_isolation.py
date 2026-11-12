import pytest
from flask_login import login_user
from studyhub.services.content_service import ContentService
from studyhub.services.student_service import StudentService
from studyhub.services.storage_service import StorageService

def test_admin_cannot_see_other_admin_students(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        tenant_b_id = two_tenants["tenant_b"].id

        students_a = StudentService.get_students_for_tenant(tenant_a_id)
        students_b = StudentService.get_students_for_tenant(tenant_b_id)

        usernames_a = [s.username for s in students_a]
        usernames_b = [s.username for s in students_b]

        assert "student_a1" in usernames_a
        assert "student_b1" not in usernames_a
        assert "student_b1" in usernames_b
        assert "student_a1" not in usernames_b

def test_admin_cannot_get_foreign_student_by_id(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        student_b1_id = two_tenants["student_b1"].id

        # Querying foreign student with Admin A's tenant_id must return None (no existence leakage)
        result = StudentService.get_student_by_id(tenant_a_id, student_b1_id)
        assert result is None

def test_admin_cannot_see_or_modify_other_subjects(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        tenant_b_id = two_tenants["tenant_b"].id
        subject_b_id = two_tenants["subject_b"].id

        # Admin A cannot retrieve Subject B
        assert ContentService.get_subject_by_id(tenant_a_id, subject_b_id) is None

        # Admin A attempting to update Subject B raises ValueError
        with pytest.raises(ValueError, match="Subject not found in your tenant"):
            ContentService.update_subject(
                tenant_id=tenant_a_id,
                subject_id=subject_b_id,
                subject_name="Hacked Subject"
            )

        # Admin A attempting to delete Subject B raises ValueError
        with pytest.raises(ValueError, match="Subject not found in your tenant"):
            ContentService.delete_subject(tenant_a_id, subject_b_id)

def test_cross_tenant_subject_title_creation_rejected(app, two_tenants):
    """Admin A cannot create a Title using Subject B from Tenant B."""
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        admin_a_id = two_tenants["admin_a"].id
        subject_b_id = two_tenants["subject_b"].id

        with pytest.raises(ValueError, match="Parent subject does not exist in your tenant"):
            ContentService.create_title(
                tenant_id=tenant_a_id,
                created_by=admin_a_id,
                subject_id=subject_b_id,
                title_name="Exploit Title"
            )

def test_cross_tenant_pdf_creation_rejected(app, two_tenants):
    """Admin A cannot associate a PDF with a Title from Tenant B."""
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        admin_a_id = two_tenants["admin_a"].id
        subject_a_id = two_tenants["subject_a"].id
        title_b_id = two_tenants["title_b"].id

        with pytest.raises(ValueError, match="Invalid title or title does not belong to your tenant"):
            ContentService.create_pdf_material(
                tenant_id=tenant_a_id,
                uploaded_by=admin_a_id,
                subject_id=subject_a_id,
                title_id=title_b_id,
                title="Cross Tenant Exploit",
                description="test",
                storage_key="tenants/exploit.pdf",
                original_filename="exploit.pdf",
                file_size=1024,
                sha256="dummy"
            )

def test_cross_tenant_signed_url_generation_blocked(app, two_tenants):
    """StorageService must reject generating signed download URL for another tenant's key."""
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        pdf_b_key = two_tenants["pdf_b"].storage_key

        with pytest.raises(PermissionError, match="Storage key does not belong to your tenant"):
            StorageService.generate_presigned_download_url(
                tenant_id=tenant_a_id,
                storage_key=pdf_b_key,
                filename="stolen.pdf"
            )

def test_student_cannot_access_other_tenant_pdf(client, two_tenants):
    """Student A1 attempting to view or download PDF B receives 404 (no existence leakage)."""
    # Authenticate Student A1
    with client.session_transaction() as sess:
        sess["_user_id"] = two_tenants["student_a1"].id
        sess["_fresh"] = True

    pdf_b_id = two_tenants["pdf_b"].id

    # View route
    view_res = client.get(f"/student/materials/{pdf_b_id}/view")
    assert view_res.status_code == 404

    # Download route
    download_res = client.get(f"/student/materials/{pdf_b_id}/download")
    assert download_res.status_code == 404

def test_student_cannot_access_unpublished_records(app, client, two_tenants):
    """Unpublished content is hidden from students."""
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        admin_a_id = two_tenants["admin_a"].id
        subject_a_id = two_tenants["subject_a"].id
        title_a_id = two_tenants["title_a"].id

        # Create unpublished PDF in Tenant A
        unpub_pdf = ContentService.create_pdf_material(
            tenant_id=tenant_a_id,
            uploaded_by=admin_a_id,
            subject_id=subject_a_id,
            title_id=title_a_id,
            title="Draft Exam Paper",
            description="Confidential draft",
            storage_key=f"tenants/{tenant_a_id}/pdfs/draft.pdf",
            original_filename="draft.pdf",
            file_size=1024,
            sha256="draft-hash",
            is_published=False # DRAFT
        )
        unpub_id = unpub_pdf.id

    # Student A1 attempts to access draft
    with client.session_transaction() as sess:
        sess["_user_id"] = two_tenants["student_a1"].id
        sess["_fresh"] = True

    res = client.get(f"/student/materials/{unpub_id}/view")
    assert res.status_code == 404

def test_platform_owner_has_no_access_to_student_content(client, bootstrap_owner, two_tenants):
    """Platform Owner must NOT automatically access private student portals or PDFs."""
    with client.session_transaction() as sess:
        sess["_user_id"] = bootstrap_owner.id
        sess["_fresh"] = True

    pdf_a_id = two_tenants["pdf_a"].id
    # Attempt to access student routes with platform_owner role
    res = client.get(f"/student/materials/{pdf_a_id}/view")
    assert res.status_code == 403

    res = client.get("/student/dashboard")
    assert res.status_code == 403
