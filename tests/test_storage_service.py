import pytest
from studyhub.services.storage_service import (
    StorageService,
    StorageQuotaExceededError,
    InvalidPdfSignatureError
)

def test_presigned_upload_url_has_tenant_prefix(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        data = StorageService.generate_presigned_upload_url(tenant_a_id, estimated_size=1024)

        assert data["storage_key"].startswith(f"tenants/{tenant_a_id}/pdfs/")
        assert data["storage_key"].endswith(".pdf")
        assert "upload_url" in data
        assert data["expires_in"] == 900

def test_reject_oversized_pdf(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        oversized = 105 * 1024 * 1024 # 105 MB (limit is 100 MB)

        with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
            StorageService.generate_presigned_upload_url(tenant_a_id, estimated_size=oversized)

def test_storage_quota_enforcement(app, two_tenants):
    with app.app_context():
        from studyhub.extensions import db
        tenant_a_id = two_tenants["tenant_a"].id
        tenant_a = db.session.get(two_tenants["tenant_a"].__class__, tenant_a_id)

        # Temporarily set tenant storage limit to 5 MB and commit
        tenant_a.storage_limit_bytes = 5 * 1024 * 1024
        db.session.commit()

        # PDF A is already 2 MB. An 8 MB upload should exceed 5 MB limit.
        with pytest.raises(StorageQuotaExceededError, match="Storage quota exceeded"):
            StorageService.verify_storage_quota(tenant_a_id, new_bytes=8 * 1024 * 1024)

def test_presigned_download_url_generation(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        pdf_a = two_tenants["pdf_a"]

        # Inline viewing URL
        inline_url = StorageService.generate_presigned_download_url(
            tenant_id=tenant_a_id,
            storage_key=pdf_a.storage_key,
            filename=pdf_a.original_filename,
            inline=True
        )
        assert inline_url is not None

        # Attachment download URL
        download_url = StorageService.generate_presigned_download_url(
            tenant_id=tenant_a_id,
            storage_key=pdf_a.storage_key,
            filename=pdf_a.original_filename,
            inline=False
        )
        assert download_url is not None
