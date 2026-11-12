import pytest
from studyhub import create_app
from studyhub.extensions import db
from studyhub.models.user import User
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial
from studyhub.models.metadata import Category
from studyhub.services.auth_service import bootstrap_main_admin, hash_password
from studyhub.services.content_service import ContentService
from studyhub.services.student_service import StudentService

@pytest.fixture
def app():
    """Application configured for testing with in-memory SQLite."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def bootstrap_owner(app):
    """Provisions the initial Platform Main Administrator."""
    with app.app_context():
        owner = bootstrap_main_admin(
            token="test-bootstrap-token-12345",
            full_name="Master Administrator",
            username="main_admin",
            email="owner@studyhub.internal",
            password="StrongOwnerPassword123!",
            ip_address="127.0.0.1"
        )
        owner_id = owner.id
        return db.session.get(User, owner_id)

@pytest.fixture
def setup_shared_environment(app, bootstrap_owner):
    """
    Sets up a complete shared global library environment:
    - Main Admin
    - Category: Computer Science
    - Admin A and Admin B (both created by Main Admin)
    - Student A1 (created by Admin A)
    - Student B1 (created by Admin B)
    - Shared Subject A (created by Admin A) with Title A and PDF A
    - Shared Subject B (created by Admin B) with Title B and PDF B
    """
    with app.app_context():
        owner = db.session.get(User, bootstrap_owner.id)

        # Create Category
        cat_cs = ContentService.get_or_create_category(
            name="Computer Science",
            description="Computing, Programming and Systems",
            icon="bi-cpu",
            creator_id=owner.id
        )

        # Admin A
        admin_a = User(
            full_name="Prof. Alice Smith",
            username="admin_alice",
            email="alice@university.edu",
            password_hash=hash_password("PasswordAlice123!"),
            role="admin",
            is_active=True,
            must_change_password=False
        )
        db.session.add(admin_a)

        # Admin B
        admin_b = User(
            full_name="Dr. Bob Jones",
            username="admin_bob",
            email="bob@institute.edu",
            password_hash=hash_password("PasswordBob123!"),
            role="admin",
            is_active=True,
            must_change_password=False
        )
        db.session.add(admin_b)
        db.session.commit()

        # Student A1 (created by Admin A)
        student_a1 = StudentService.create_student(
            admin_id=admin_a.id,
            full_name="Charlie Student",
            username="student_charlie",
            email="charlie@students.edu",
            password="StudentPass123!"
        )
        student_a1.must_change_password = False

        # Student B1 (created by Admin B)
        student_b1 = StudentService.create_student(
            admin_id=admin_b.id,
            full_name="Diana Student",
            username="student_diana",
            email="diana@students.edu",
            password="StudentPass123!"
        )
        student_b1.must_change_password = False
        db.session.commit()

        # Shared Subject A (Alice)
        subject_a = ContentService.create_subject(
            subject_name="Data Structures & Algorithms",
            created_by_admin_id=admin_a.id,
            description="Algorithmic problem solving",
            icon="bi-code-square",
            is_published=True,
            category_ids=[cat_cs.id],
            tag_names=["algorithms", "trees", "sorting"]
        )

        title_a = ContentService.create_title(
            subject_id=subject_a.id,
            title_name="Module 1: Binary Search Trees",
            created_by_admin_id=admin_a.id,
            description="BST balancing and traversal algorithms",
            is_published=True
        )

        pdf_a = ContentService.create_pdf_material(
            subject_id=subject_a.id,
            title_id=title_a.id,
            title="BST Lecture Notes",
            description="Detailed lecture slides on BST",
            storage_key="materials/mock_bst.pdf",
            original_filename="bst_lecture.pdf",
            file_size=2048576,
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            uploaded_by_admin_id=admin_a.id,
            is_published=True,
            tag_names=["trees", "algorithms"]
        )

        # Shared Subject B (Bob)
        subject_b = ContentService.create_subject(
            subject_name="Operating Systems",
            created_by_admin_id=admin_b.id,
            description="Kernel architecture, memory & concurrency",
            icon="bi-gear-wide-connected",
            is_published=True,
            category_ids=[cat_cs.id],
            tag_names=["os", "concurrency", "linux"]
        )

        title_b = ContentService.create_title(
            subject_id=subject_b.id,
            title_name="Unit 2: Virtual Memory & Paging",
            created_by_admin_id=admin_b.id,
            description="TLB, page replacement and segmentation",
            is_published=True
        )

        pdf_b = ContentService.create_pdf_material(
            subject_id=subject_b.id,
            title_id=title_b.id,
            title="Virtual Memory Handout",
            description="Paging and page fault handling",
            storage_key="materials/mock_vm.pdf",
            original_filename="vm_handout.pdf",
            file_size=3145728,
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            uploaded_by_admin_id=admin_b.id,
            is_published=True,
            tag_names=["os", "memory"]
        )

        return {
            "owner": owner,
            "category": cat_cs,
            "admin_a": admin_a,
            "admin_b": admin_b,
            "student_a1": student_a1,
            "student_b1": student_b1,
            "subject_a": subject_a,
            "subject_b": subject_b,
            "title_a": title_a,
            "title_b": title_b,
            "pdf_a": pdf_a,
            "pdf_b": pdf_b
        }
