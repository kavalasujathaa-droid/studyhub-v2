import pytest
from studyhub.services.storage_service import (
    StorageService,
    StorageQuotaExceededError,
    InvalidPdfSignatureError
)

def test_presigned_upload_url_generation(app):
    with app.app_context():
        data = StorageService.generate_presigned_upload_url(estimated_size=1024)
        assert data["storage_key"].startswith("pdfs/")
        assert data["storage_key"].endswith(".pdf")
        assert "upload_url" in data
        assert data["expires_in"] == 900

def test_reject_oversized_pdf(app):
    with app.app_context():
        oversized = 105 * 1024 * 1024  # 105 MB (limit is 100 MB)
        with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
            StorageService.generate_presigned_upload_url(estimated_size=oversized)

def test_storage_quota_enforcement(app):
    with app.app_context():
        # Exceeding the 9 GiB safety quota
        overflow = 10 * 1024 * 1024 * 1024  # 10 GiB
        with pytest.raises(StorageQuotaExceededError, match="Storage safety quota exceeded"):
            StorageService.verify_storage_quota(new_bytes=overflow)

def test_presigned_download_url_generation(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        pdf_a = env["pdf_a"]

        # Inline viewing URL
        inline_url = StorageService.generate_presigned_download_url(
            storage_key=pdf_a.storage_key,
            filename=pdf_a.original_filename,
            inline=True
        )
        assert inline_url is not None
        assert "response-content-disposition=inline" in inline_url or "inline" in inline_url

        # Attachment download URL
        download_url = StorageService.generate_presigned_download_url(
            storage_key=pdf_a.storage_key,
            filename=pdf_a.original_filename,
            inline=False
        )
        assert download_url is not None
        assert "attachment" in download_url

def test_local_storage_direct_upload_and_verification(client, app, setup_shared_environment):
    env = setup_shared_environment
    admin = env["admin_a"]
    subject = env["subject_a"]
    title = env["title_a"]

    # Temporarily disable R2 account ID to test local server storage fallback
    old_account_id = app.config.get("R2_ACCOUNT_ID")
    app.config["R2_ACCOUNT_ID"] = ""

    try:
        # Authenticate as admin
        with client.session_transaction() as sess:
            sess["_user_id"] = admin.id
            sess["_fresh"] = True

        # 1. Request upload authorization
        res = client.post("/api/v1/storage/presigned-upload", json={
            "subject_id": subject.id,
            "title_id": title.id,
            "file_size": 2048,
            "filename": "local_test.pdf"
        })
        assert res.status_code == 200
        upload_data = res.get_json()
        storage_key = upload_data["storage_key"]
        upload_url = upload_data["upload_url"]
        assert upload_url.startswith("/api/v1/storage/upload/")

        # 2. Upload file bytes directly
        pdf_bytes = b"%PDF-1.4 mock binary content for unit testing local storage"
        upload_res = client.put(upload_url, data=pdf_bytes, headers={"Content-Type": "application/pdf"})
        assert upload_res.status_code == 200

        # 3. Complete upload
        complete_res = client.post("/api/v1/storage/complete-upload", json={
            "subject_id": subject.id,
            "title_id": title.id,
            "title": "Local Storage Unit Test PDF",
            "description": "Testing local storage fallback",
            "storage_key": storage_key,
            "original_filename": "local_test.pdf",
            "is_published": True,
            "language": "English"
        })
        assert complete_res.status_code == 201
        assert complete_res.get_json()["success"] is True

        # 4. Verify direct download endpoint works
        download_url = f"/api/v1/storage/download/{storage_key}?filename=local_test.pdf"
        download_res = client.get(download_url)
        assert download_res.status_code == 200
        assert download_res.data == pdf_bytes
    finally:
        app.config["R2_ACCOUNT_ID"] = old_account_id
