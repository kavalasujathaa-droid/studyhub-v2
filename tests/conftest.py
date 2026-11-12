import pytest
from studyhub import create_app
from studyhub.extensions import db
from studyhub.models.user import User
from studyhub.models.tenant import Tenant
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial
from studyhub.services.auth_service import bootstrap_platform_owner
from studyhub.services.tenant_service import TenantService
from studyhub.services.student_service import StudentService
from studyhub.services.content_service import ContentService

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
    """Provisions the initial Platform Owner."""
    with app.app_context():
        owner = bootstrap_platform_owner(
            token="test-bootstrap-token-12345",
            full_name="Platform Master",
            username="platform_owner",
            email="owner@studyhub.internal",
            password="StrongOwnerPassword123!",
            ip_address="127.0.0.1"
        )
        owner_id = owner.id
        return db.session.get(User, owner_id)

@pytest.fixture
def two_tenants(app, bootstrap_owner):
    """
    Creates two completely isolated tenants:
    - Tenant A (Admin A, Student A1, Subject A, Title A, PDF A)
    - Tenant B (Admin B, Student B1, Subject B, Title B, PDF B)
    """
    with app.app_context():
        owner = db.session.get(User, bootstrap_owner.id)

        # Tenant A
        tenant_a, admin_a = TenantService.create_tenant_and_admin(
            owner_id=owner.id,
            tenant_name="Alpha Academy",
            admin_full_name="Admin Alpha",
            username="admin_alpha",
            email="admin_a@alpha.edu",
            password="PasswordAlpha123!"
        )
        student_a1 = StudentService.create_student(
            tenant_id=tenant_a.id,
            admin_id=admin_a.id,
            full_name="Student Alpha One",
            username="student_a1",
            email="student_a1@alpha.edu",
            password="StudentAlphaPass123!"
        )
        # Mark password changed for test browsing
        admin_a.must_change_password = False
        student_a1.must_change_password = False
        subject_a = ContentService.create_subject(
            tenant_id=tenant_a.id,
            created_by=admin_a.id,
            subject_name="Mathematics A",
            description="Alpha Calculus and Linear Algebra",
            is_published=True
        )
        title_a = ContentService.create_title(
            tenant_id=tenant_a.id,
            created_by=admin_a.id,
            subject_id=subject_a.id,
            title_name="Important Questions A",
            description="Exam revision notes",
            is_published=True
        )
        pdf_a = ContentService.create_pdf_material(
            tenant_id=tenant_a.id,
            uploaded_by=admin_a.id,
            subject_id=subject_a.id,
            title_id=title_a.id,
            title="Calculus Notes A",
            description="Differential calculus unit 1",
            storage_key=f"tenants/{tenant_a.id}/pdfs/mock_a.pdf",
            original_filename="calc_a.pdf",
            file_size=2048576,
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            is_published=True
        )

        # Tenant B
        tenant_b, admin_b = TenantService.create_tenant_and_admin(
            owner_id=owner.id,
            tenant_name="Beta Institute",
            admin_full_name="Admin Beta",
            username="admin_beta",
            email="admin_b@beta.edu",
            password="PasswordBeta123!"
        )
        student_b1 = StudentService.create_student(
            tenant_id=tenant_b.id,
            admin_id=admin_b.id,
            full_name="Student Beta One",
            username="student_b1",
            email="student_b1@beta.edu",
            password="StudentBetaPass123!"
        )
        admin_b.must_change_password = False
        student_b1.must_change_password = False
        db.session.commit()
        subject_b = ContentService.create_subject(
            tenant_id=tenant_b.id,
            created_by=admin_b.id,
            subject_name="Physics B",
            description="Beta Classical Mechanics",
            is_published=True
        )
        title_b = ContentService.create_title(
            tenant_id=tenant_b.id,
            created_by=admin_b.id,
            subject_id=subject_b.id,
            title_name="Unit 1 B",
            description="Kinematics and Dynamics",
            is_published=True
        )
        pdf_b = ContentService.create_pdf_material(
            tenant_id=tenant_b.id,
            uploaded_by=admin_b.id,
            subject_id=subject_b.id,
            title_id=title_b.id,
            title="Mechanics Notes B",
            description="Newtonian physics unit 1",
            storage_key=f"tenants/{tenant_b.id}/pdfs/mock_b.pdf",
            original_filename="mechanics_b.pdf",
            file_size=3145728,
            sha256="cbf529a4d5d4970424e3aeb42da8d42b5b706a813f07a0879f74928c1f9bf919",
            is_published=True
        )

        return {
            "tenant_a": tenant_a,
            "admin_a": admin_a,
            "student_a1": student_a1,
            "subject_a": subject_a,
            "title_a": title_a,
            "pdf_a": pdf_a,
            "tenant_b": tenant_b,
            "admin_b": admin_b,
            "student_b1": student_b1,
            "subject_b": subject_b,
            "title_b": title_b,
            "pdf_b": pdf_b,
        }
