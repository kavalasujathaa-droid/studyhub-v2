import pytest
from studyhub.services.content_service import ContentService
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial, PdfVersion

def test_shared_subject_duplicate_prevention(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        # Attempting to create duplicate subject name in shared library raises ValueError
        with pytest.raises(ValueError, match="already exists in the shared library"):
            ContentService.create_subject(
                subject_name="Data Structures & Algorithms",
                created_by_admin_id=env["admin_b"].id
            )

def test_admin_can_reuse_existing_shared_subject(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        # Admin B contributes a new title and PDF under Admin A's subject
        title_b_in_a = ContentService.create_title(
            subject_id=env["subject_a"].id,
            title_name="Module 4: Graph Algorithms",
            created_by_admin_id=env["admin_b"].id,
            description="Dijkstra, BFS, DFS notes",
            is_published=True
        )
        assert title_b_in_a.subject_id == env["subject_a"].id
        assert title_b_in_a.created_by_admin_id == env["admin_b"].id

        pdf_b_in_a = ContentService.create_pdf_material(
            subject_id=env["subject_a"].id,
            title_id=title_b_in_a.id,
            title="Graph Traversals Guide",
            description="BFS and DFS examples",
            storage_key="materials/graphs_b.pdf",
            original_filename="graphs_b.pdf",
            file_size=1048576,
            sha256="3333333333333333333333333333333333333333333333333333333333333333",
            uploaded_by_admin_id=env["admin_b"].id
        )
        assert pdf_b_in_a.subject_id == env["subject_a"].id

def test_duplicate_sha256_detection_across_library(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        # Attempting to upload exact same file (same SHA256) is rejected
        with pytest.raises(ValueError, match="Duplicate PDF detected"):
            ContentService.create_pdf_material(
                subject_id=env["subject_b"].id,
                title_id=env["title_b"].id,
                title="Duplicate BST Upload",
                description="Copy of bst",
                storage_key="materials/duplicate.pdf",
                original_filename="bst_copy.pdf",
                file_size=2048576,
                sha256=env["pdf_a"].sha256,
                uploaded_by_admin_id=env["admin_b"].id
            )

def test_pdf_replacement_and_version_restoration(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        pdf_a = env["pdf_a"]
        admin_a = env["admin_a"]
        admin_b = env["admin_b"]

        # Admin B cannot replace Admin A's PDF (Permission denied)
        with pytest.raises(PermissionError, match="Only the original uploader or Main Admin"):
            ContentService.replace_pdf_material(
                pdf_id=pdf_a.id,
                user=admin_b,
                new_storage_key="materials/malicious.pdf",
                new_original_filename="bad.pdf",
                new_file_size=1000,
                new_sha256="bad-sha"
            )

        # Admin A replaces own PDF
        updated = ContentService.replace_pdf_material(
            pdf_id=pdf_a.id,
            user=admin_a,
            new_storage_key="materials/bst_v2.pdf",
            new_original_filename="bst_v2_clean.pdf",
            new_file_size=2500000,
            new_sha256="4444444444444444444444444444444444444444444444444444444444444444"
        )
        assert updated.storage_key == "materials/bst_v2.pdf"
        assert len(updated.versions) == 1
        archived = updated.versions[0]
        assert archived.original_filename == "bst_lecture.pdf"

        # Restore original version
        restored = ContentService.restore_pdf_version(pdf_a.id, archived.id, admin_a)
        assert restored.original_filename == "bst_lecture.pdf"
        assert restored.storage_key == "materials/mock_bst.pdf"

def test_soft_delete_and_recovery(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        subject_a = env["subject_a"]
        admin_a = env["admin_a"]
        owner = env["owner"]

        ContentService.delete_subject(subject_a.id, admin_a, soft=True)
        assert ContentService.get_subject_by_id(subject_a.id, published_only=True) is None

        # Main Admin recovers subject from recovery vault
        ContentService.restore_subject(subject_a.id, owner)
        restored = ContentService.get_subject_by_id(subject_a.id)
        assert restored is not None
        assert restored.deleted_at is None
