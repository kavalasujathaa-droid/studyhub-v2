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
