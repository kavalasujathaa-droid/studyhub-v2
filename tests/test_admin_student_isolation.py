import pytest
from studyhub.services.student_service import StudentService
from studyhub.services.content_service import ContentService
from studyhub.models.user import User

def test_admin_can_only_see_own_students(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        admin_a = env["admin_a"]
        admin_b = env["admin_b"]

        # Alice only sees Charlie
        alice_students = StudentService.get_students_for_admin(admin_a.id)
        assert len(alice_students) == 1
        assert alice_students[0].username == "student_charlie"

        # Bob only sees Diana
        bob_students = StudentService.get_students_for_admin(admin_b.id)
        assert len(bob_students) == 1
        assert bob_students[0].username == "student_diana"

def test_admin_cannot_modify_other_admin_students(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        admin_a = env["admin_a"]
        student_b1 = env["student_b1"]

        # Alice cannot get Bob's student
        assert StudentService.get_student_by_id(student_b1.id, admin_a.id) is None

        # Alice cannot deactivate Bob's student
        with pytest.raises(PermissionError):
            StudentService.toggle_student_status(student_b1.id, admin_a.id, is_active=False)

        # Alice cannot reset password for Bob's student
        with pytest.raises(PermissionError):
            StudentService.reset_student_password(student_b1.id, admin_a.id, "HackedPass123!")

def test_main_admin_can_manage_all(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        stats = ContentService.get_platform_analytics()
        assert stats["total_admins"] == 2
        assert stats["total_users"] == 2
        assert stats["total_pdfs"] == 2

def test_students_can_access_all_shared_library_content(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        # Charlie (created by Alice) accesses Bob's published PDF
        pdf_b = ContentService.get_material_by_id(env["pdf_b"].id, published_only=True)
        assert pdf_b is not None
        assert pdf_b.title == "Virtual Memory Handout"

        # Diana (created by Bob) accesses Alice's published PDF
        pdf_a = ContentService.get_material_by_id(env["pdf_a"].id, published_only=True)
        assert pdf_a is not None
        assert pdf_a.title == "BST Lecture Notes"

def test_bulk_csv_student_onboarding(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        admin_a = env["admin_a"]

        # Valid CSV
        csv_content = (
            "full_name,username,email,password\n"
            "Eve Online,student_eve,eve@students.edu,StrongPass123!\n"
            "Frank Ocean,student_frank,frank@students.edu,StrongPass456!\n"
        )
        result = StudentService.bulk_import_students(admin_a.id, csv_content)
        assert result["created_count"] == 2
        assert len(result["errors"]) == 0

        # Verify students belong to Alice
        alice_students = StudentService.get_students_for_admin(admin_a.id)
        assert len(alice_students) == 3

        # Invalid CSV format
        invalid_csv = "name,email\nNoPass,test@test.com\n"
        with pytest.raises(ValueError, match="CSV must contain columns"):
            StudentService.bulk_import_students(admin_a.id, invalid_csv)

def test_admin_create_student_post_route(client, setup_shared_environment):
    # Log in as admin_alice with correct password
    login_res = client.post("/auth/login", data={
        "identifier": "admin_alice",
        "password": "PasswordAlice123!"
    }, follow_redirects=True)
    assert login_res.status_code == 200

    # Post student creation (the exact flow that previously triggered 500)
    res = client.post("/admin/students", data={
        "full_name": "Grace Hopper",
        "username": "grace_hopper",
        "email": "grace@navy.edu",
        "password": "CobolCompiler123!"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"enrolled successfully" in res.data or b"grace_hopper" in res.data

