import pytest
from studyhub.services.content_service import ContentService
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial, PdfVersion

def test_subject_unique_constraint_per_tenant(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        admin_a_id = two_tenants["admin_a"].id

        # Creating duplicate subject name in same tenant raises ValueError
        with pytest.raises(ValueError, match="already exists"):
            ContentService.create_subject(
                tenant_id=tenant_a_id,
                created_by=admin_a_id,
                subject_name="Mathematics A"
            )

        # Same subject name in different tenant (Tenant B) is allowed!
        tenant_b_id = two_tenants["tenant_b"].id
        admin_b_id = two_tenants["admin_b"].id
        sub_b_math = ContentService.create_subject(
            tenant_id=tenant_b_id,
            created_by=admin_b_id,
            subject_name="Mathematics A"
        )
        assert sub_b_math.tenant_id == tenant_b_id

def test_pdf_replacement_archives_previous_version(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        admin_a_id = two_tenants["admin_a"].id
        pdf_a = two_tenants["pdf_a"]
        old_key = pdf_a.storage_key
        old_filename = pdf_a.original_filename

        # Replace PDF
        updated = ContentService.replace_pdf_material(
            tenant_id=tenant_a_id,
            replaced_by=admin_a_id,
            pdf_id=pdf_a.id,
            new_storage_key=f"tenants/{tenant_a_id}/pdfs/new_v2.pdf",
            new_original_filename="calc_v2.pdf",
            new_file_size=5000000,
            new_sha256="new-sha256-hash-v2"
        )

        assert updated.storage_key == f"tenants/{tenant_a_id}/pdfs/new_v2.pdf"
        assert updated.original_filename == "calc_v2.pdf"
        assert updated.file_size == 5000000

        # Check archived version in pdf_versions
        versions = updated.versions
        assert len(versions) == 1
        assert versions[0].storage_key == old_key
        assert versions[0].original_filename == old_filename

def test_soft_delete_cascades_safely(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        subject_a_id = two_tenants["subject_a"].id
        title_a_id = two_tenants["title_a"].id
        pdf_a_id = two_tenants["pdf_a"].id

        ContentService.delete_subject(tenant_a_id, subject_a_id, soft=True)

        # In tenant-filtered queries, deleted items must not appear
        assert ContentService.get_subject_by_id(tenant_a_id, subject_a_id) is None
        assert ContentService.get_title_by_id(tenant_a_id, title_a_id) is None
        assert ContentService.get_material_by_id(tenant_a_id, pdf_a_id) is None
