import pytest
from studyhub.models.user import User
from studyhub.services.auth_service import (
    bootstrap_main_admin,
    is_main_admin_initialized,
    verify_password,
    hash_password
)

def test_first_time_bootstrap_success(app):
    with app.app_context():
        assert not is_main_admin_initialized()
        owner = bootstrap_main_admin(
            token="test-bootstrap-token-12345",
            full_name="Root Admin",
            username="root_admin",
            email="root@studyhub.internal",
            password="SecureMasterPassword123!",
            ip_address="127.0.0.1"
        )
        assert owner.role in ["main_admin", "platform_owner"]
        assert owner.is_main_admin()
        assert is_main_admin_initialized()
        assert verify_password(owner.password_hash, "SecureMasterPassword123!")

def test_bootstrap_invalid_token_fails(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Invalid setup bootstrap token"):
            bootstrap_main_admin(
                token="wrong-token-abc",
                full_name="Attacker",
                username="attacker",
                email="hacker@evil.com",
                password="Password123456!"
            )

def test_second_bootstrap_attempt_blocked(app, bootstrap_owner):
    with app.app_context():
        with pytest.raises(ValueError, match="permanently closed"):
            bootstrap_main_admin(
                token="test-bootstrap-token-12345",
                full_name="Second Owner",
                username="owner_two",
                email="two@studyhub.internal",
                password="AnotherPassword123!"
            )

def test_setup_route_redirects_when_owner_exists(client, bootstrap_owner):
    res = client.get("/auth/setup")
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]

def test_login_flow(client, setup_shared_environment):
    # Valid login for Admin Alice
    res = client.post("/auth/login", data={
        "identifier": "admin_alice",
        "password": "PasswordAlice123!"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Educator Dashboard" in res.data or b"admin" in res.request.path.lower()

def test_login_invalid_password(client, setup_shared_environment):
    res = client.post("/auth/login", data={
        "identifier": "admin_alice",
        "password": "WrongPassword!"
    })
    assert res.status_code == 200
    assert b"Invalid credentials" in res.data

def test_no_public_registration_route(client):
    res = client.get("/register")
    assert res.status_code == 404
    res = client.get("/auth/register")
    assert res.status_code == 404
