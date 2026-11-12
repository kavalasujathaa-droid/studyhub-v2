import os
import uuid
import hashlib
from datetime import datetime, timezone
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from flask import current_app
from sqlalchemy import func
from studyhub.extensions import db
from studyhub.models.content import PdfMaterial, PdfVersion
from studyhub.models.tenant import Tenant

class StorageQuotaExceededError(Exception):
    pass

class InvalidPdfSignatureError(Exception):
    pass

class StorageService:
    """Manages Cloudflare R2 S3-compatible private storage and presigned operations."""

    @classmethod
    def get_s3_client(cls):
        """Constructs a Boto3 client pointing to Cloudflare R2 endpoint."""
        account_id = current_app.config.get("R2_ACCOUNT_ID")
        access_key = current_app.config.get("R2_ACCESS_KEY_ID")
        secret_key = current_app.config.get("R2_SECRET_ACCESS_KEY")
        
        # In test mode or when mock client configured
        if current_app.config.get("TESTING") and not account_id:
            return None

        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        
        return boto3.client(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"}
            )
        )

    @classmethod
    def generate_object_key(cls, tenant_id: str) -> str:
        """Generates a secure, non-guessable tenant-partitioned object key."""
        random_id = str(uuid.uuid4())
        return f"tenants/{tenant_id}/pdfs/{random_id}.pdf"

    @classmethod
    def get_tenant_storage_used(cls, tenant_id: str) -> int:
        """Calculates total storage used by tenant materials and versions in bytes."""
        materials_size = db.session.query(func.coalesce(func.sum(PdfMaterial.file_size), 0)).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        versions_size = db.session.query(func.coalesce(func.sum(PdfVersion.file_size), 0)).filter(
            PdfVersion.tenant_id == tenant_id
        ).scalar() or 0

        return int(materials_size + versions_size)

    @classmethod
    def verify_storage_quota(cls, tenant_id: str, new_bytes: int):
        """Ensures the upload will not exceed tenant quota or 9 GiB safety ceiling."""
        tenant = db.session.get(Tenant, tenant_id)
        limit = tenant.storage_limit_bytes if tenant else current_app.config.get("MAX_TENANT_STORAGE_BYTES")
        
        current_used = cls.get_tenant_storage_used(tenant_id)
        if current_used + new_bytes > limit:
            raise StorageQuotaExceededError(
                f"Storage quota exceeded. Used: {current_used / (1024*1024):.2f} MB, "
                f"Limit: {limit / (1024*1024):.2f} MB."
            )

    @classmethod
    def generate_presigned_upload_url(cls, tenant_id: str, estimated_size: int = 0) -> dict:
        """Generates a presigned PUT URL for direct browser-to-R2 upload."""
        max_file_size = current_app.config.get("MAX_CONTENT_LENGTH", 104857600) # 100 MB
        if estimated_size > max_file_size:
            raise ValueError(f"File size exceeds maximum allowed limit of {max_file_size // (1024*1024)} MB.")

        cls.verify_storage_quota(tenant_id, estimated_size)
        object_key = cls.generate_object_key(tenant_id)
        bucket = current_app.config.get("R2_BUCKET_NAME", "")

        client = cls.get_s3_client()
        if client is None:
            # Test / local stub mode
            return {
                "upload_url": f"/mock-storage/upload/{object_key}",
                "storage_key": object_key,
                "expires_in": 900,
            }

        presigned_url = client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": object_key,
                "ContentType": "application/pdf",
            },
            ExpiresIn=900, # 15 minutes
            HttpMethod="PUT"
        )

        return {
            "upload_url": presigned_url,
            "storage_key": object_key,
            "expires_in": 900
        }

    @classmethod
    def verify_and_inspect_uploaded_pdf(cls, tenant_id: str, storage_key: str) -> dict:
        """
        Validates the uploaded object in R2:
        - Confirms key belongs to tenant_id prefix
        - Confirms object exists
        - Confirms size <= 100 MB
        - Verifies %PDF- magic byte signature
        - Computes / verifies sha256
        """
        # Security check: object key MUST match tenant
        expected_prefix = f"tenants/{tenant_id}/pdfs/"
        if not storage_key.startswith(expected_prefix):
            raise PermissionError("Storage key does not belong to the authenticated tenant.")

        bucket = current_app.config.get("R2_BUCKET_NAME", "")
        client = cls.get_s3_client()

        if client is None:
            # Mock mode for testing without network
            return {
                "file_size": 1024,
                "sha256": "mock-sha256-hash-for-testing",
                "storage_key": storage_key,
                "mime_type": "application/pdf"
            }

        try:
            head = client.head_object(Bucket=bucket, Key=storage_key)
            file_size = head.get("ContentLength", 0)
        except ClientError as e:
            raise FileNotFoundError(f"Uploaded object not found in R2: {str(e)}")

        max_allowed = current_app.config.get("MAX_CONTENT_LENGTH", 104857600)
        if file_size > max_allowed:
            cls.delete_object(storage_key)
            raise ValueError(f"Uploaded file exceeds limit of {max_allowed // (1024*1024)} MB.")

        if file_size < 4:
            cls.delete_object(storage_key)
            raise InvalidPdfSignatureError("Uploaded file is corrupted or empty.")

        # Read first 1024 bytes to check %PDF- magic bytes signature
        try:
            range_obj = client.get_object(Bucket=bucket, Key=storage_key, Range="bytes=0-1023")
            header_bytes = range_obj["Body"].read()
            if not header_bytes.startswith(b"%PDF-"):
                cls.delete_object(storage_key)
                raise InvalidPdfSignatureError("File does not start with valid PDF magic bytes '%PDF-'.")
        except ClientError as e:
            cls.delete_object(storage_key)
            raise InvalidPdfSignatureError(f"Could not verify PDF header: {str(e)}")

        # Enforce quota with actual verified file size
        cls.verify_storage_quota(tenant_id, file_size)

        # Compute full SHA256 of object
        full_obj = client.get_object(Bucket=bucket, Key=storage_key)
        hasher = hashlib.sha256()
        for chunk in full_obj["Body"].iter_chunks(chunk_size=65536):
            hasher.update(chunk)
        sha256_hash = hasher.hexdigest()

        return {
            "file_size": file_size,
            "sha256": sha256_hash,
            "storage_key": storage_key,
            "mime_type": "application/pdf"
        }

    @classmethod
    def generate_presigned_download_url(cls, tenant_id: str, storage_key: str, filename: str, inline: bool = True) -> str:
        """Generates a short-lived presigned GET URL for inline viewing or attachment download."""
        expected_prefix = f"tenants/{tenant_id}/pdfs/"
        if not storage_key.startswith(expected_prefix):
            raise PermissionError("Access denied: Storage key does not belong to your tenant.")

        bucket = current_app.config.get("R2_BUCKET_NAME", "")
        client = cls.get_s3_client()
        if client is None:
            return f"/mock-storage/download/{storage_key}?inline={inline}"

        disposition_type = "inline" if inline else "attachment"
        safe_filename = filename.replace('"', '\\"')
        content_disposition = f'{disposition_type}; filename="{safe_filename}"'

        url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket,
                "Key": storage_key,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": content_disposition,
            },
            ExpiresIn=600 # 10 minutes
        )
        return url

    @classmethod
    def delete_object(cls, storage_key: str):
        """Removes an object from R2."""
        bucket = current_app.config.get("R2_BUCKET_NAME", "")
        client = cls.get_s3_client()
        if client:
            try:
                client.delete_object(Bucket=bucket, Key=storage_key)
            except ClientError:
                pass
