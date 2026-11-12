from datetime import datetime, timezone
from sqlalchemy import func
from studyhub.extensions import db
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial, PdfVersion
from studyhub.models.audit import AuditLog
from studyhub.services.storage_service import StorageService

class ContentService:
    """Manages Subjects, Titles, and PDF Materials with strict multi-tenant isolation."""

    # =========================================================================
    # SUBJECT MANAGEMENT (TENANT SCOPED)
    # =========================================================================

    @classmethod
    def create_subject(
        cls,
        tenant_id: str,
        created_by: str,
        subject_name: str,
        description: str = None,
        icon: str = "bi-journal-bookmark",
        sort_order: int = 0,
        is_published: bool = False
    ) -> Subject:
        clean_name = subject_name.strip()
        # Verify uniqueness within tenant
        existing = db.session.query(Subject).filter(
            Subject.tenant_id == tenant_id,
            Subject.subject_name == clean_name,
            Subject.deleted_at.is_(None)
        ).first()
        if existing:
            raise ValueError(f"A subject named '{clean_name}' already exists in your library.")

        subject = Subject(
            tenant_id=tenant_id,
            created_by=created_by,
            subject_name=clean_name,
            description=description.strip() if description else None,
            icon=icon or "bi-journal-bookmark",
            sort_order=sort_order,
            is_published=is_published
        )
        db.session.add(subject)
        db.session.commit()
        return subject

    @classmethod
    def get_subjects_for_tenant(cls, tenant_id: str, published_only: bool = False) -> list[Subject]:
        query = db.session.query(Subject).filter(
            Subject.tenant_id == tenant_id,
            Subject.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(Subject.is_published.is_(True))
        return query.order_by(Subject.sort_order.asc(), Subject.subject_name.asc()).all()

    @classmethod
    def get_subject_by_id(cls, tenant_id: str, subject_id: str, published_only: bool = False) -> Subject | None:
        """Tenant-isolated subject retrieval (never returns another tenant's subject)."""
        query = db.session.query(Subject).filter(
            Subject.tenant_id == tenant_id,
            Subject.id == subject_id,
            Subject.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(Subject.is_published.is_(True))
        return query.first()

    @classmethod
    def update_subject(
        cls,
        tenant_id: str,
        subject_id: str,
        subject_name: str,
        description: str = None,
        icon: str = None,
        sort_order: int = None,
        is_published: bool = None
    ) -> Subject:
        subject = cls.get_subject_by_id(tenant_id, subject_id)
        if not subject:
            raise ValueError("Subject not found in your tenant.")

        clean_name = subject_name.strip()
        # Check uniqueness if renaming
        if clean_name != subject.subject_name:
            conflict = db.session.query(Subject).filter(
                Subject.tenant_id == tenant_id,
                Subject.subject_name == clean_name,
                Subject.id != subject_id,
                Subject.deleted_at.is_(None)
            ).first()
            if conflict:
                raise ValueError(f"Another subject named '{clean_name}' already exists.")
            subject.subject_name = clean_name

        if description is not None:
            subject.description = description.strip() if description else None
        if icon:
            subject.icon = icon
        if sort_order is not None:
            subject.sort_order = sort_order
        if is_published is not None:
            subject.is_published = is_published

        db.session.commit()
        return subject

    @classmethod
    def delete_subject(cls, tenant_id: str, subject_id: str, soft: bool = True):
        subject = cls.get_subject_by_id(tenant_id, subject_id)
        if not subject:
            raise ValueError("Subject not found in your tenant.")

        if soft:
            now = datetime.now(timezone.utc)
            subject.deleted_at = now
            # Cascade soft-delete to titles and pdfs under this subject
            for title in subject.titles:
                title.deleted_at = now
            for pdf in subject.pdf_materials:
                pdf.deleted_at = now
        else:
            db.session.delete(subject)

        db.session.commit()

    # =========================================================================
    # TITLE MANAGEMENT (TENANT SCOPED)
    # =========================================================================

    @classmethod
    def create_title(
        cls,
        tenant_id: str,
        created_by: str,
        subject_id: str,
        title_name: str,
        description: str = None,
        sort_order: int = 0,
        is_published: bool = False
    ) -> SubjectTitle:
        # STRICT CROSS-TENANT CHECK: subject must belong to this tenant
        subject = cls.get_subject_by_id(tenant_id, subject_id)
        if not subject:
            raise ValueError("Parent subject does not exist in your tenant.")

        clean_name = title_name.strip()
        existing = db.session.query(SubjectTitle).filter(
            SubjectTitle.tenant_id == tenant_id,
            SubjectTitle.subject_id == subject_id,
            SubjectTitle.title_name == clean_name,
            SubjectTitle.deleted_at.is_(None)
        ).first()
        if existing:
            raise ValueError(f"A title named '{clean_name}' already exists under this subject.")

        title = SubjectTitle(
            tenant_id=tenant_id,
            subject_id=subject_id,
            title_name=clean_name,
            description=description.strip() if description else None,
            sort_order=sort_order,
            is_published=is_published,
            created_by=created_by
        )
        db.session.add(title)
        db.session.commit()
        return title

    @classmethod
    def get_titles_for_subject(cls, tenant_id: str, subject_id: str, published_only: bool = False) -> list[SubjectTitle]:
        # Tenant isolation check on subject
        subject = cls.get_subject_by_id(tenant_id, subject_id, published_only=published_only)
        if not subject:
            return []

        query = db.session.query(SubjectTitle).filter(
            SubjectTitle.tenant_id == tenant_id,
            SubjectTitle.subject_id == subject_id,
            SubjectTitle.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(SubjectTitle.is_published.is_(True))
        return query.order_by(SubjectTitle.sort_order.asc(), SubjectTitle.title_name.asc()).all()

    @classmethod
    def get_title_by_id(cls, tenant_id: str, title_id: str, published_only: bool = False) -> SubjectTitle | None:
        query = db.session.query(SubjectTitle).filter(
            SubjectTitle.tenant_id == tenant_id,
            SubjectTitle.id == title_id,
            SubjectTitle.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(SubjectTitle.is_published.is_(True))
        return query.first()

    @classmethod
    def update_title(
        cls,
        tenant_id: str,
        title_id: str,
        title_name: str,
        description: str = None,
        sort_order: int = None,
        is_published: bool = None
    ) -> SubjectTitle:
        title = cls.get_title_by_id(tenant_id, title_id)
        if not title:
            raise ValueError("Title not found in your tenant.")

        clean_name = title_name.strip()
        if clean_name != title.title_name:
            conflict = db.session.query(SubjectTitle).filter(
                SubjectTitle.tenant_id == tenant_id,
                SubjectTitle.subject_id == title.subject_id,
                SubjectTitle.title_name == clean_name,
                SubjectTitle.id != title_id,
                SubjectTitle.deleted_at.is_(None)
            ).first()
            if conflict:
                raise ValueError(f"Another title named '{clean_name}' already exists under this subject.")
            title.title_name = clean_name

        if description is not None:
            title.description = description.strip() if description else None
        if sort_order is not None:
            title.sort_order = sort_order
        if is_published is not None:
            title.is_published = is_published

        db.session.commit()
        return title

    @classmethod
    def delete_title(cls, tenant_id: str, title_id: str, soft: bool = True):
        title = cls.get_title_by_id(tenant_id, title_id)
        if not title:
            raise ValueError("Title not found in your tenant.")

        if soft:
            now = datetime.now(timezone.utc)
            title.deleted_at = now
            for pdf in title.pdf_materials:
                pdf.deleted_at = now
        else:
            db.session.delete(title)

        db.session.commit()

    # =========================================================================
    # PDF MATERIALS MANAGEMENT (TENANT SCOPED)
    # =========================================================================

    @classmethod
    def create_pdf_material(
        cls,
        tenant_id: str,
        uploaded_by: str,
        subject_id: str,
        title_id: str,
        title: str,
        description: str,
        storage_key: str,
        original_filename: str,
        file_size: int,
        sha256: str,
        is_published: bool = False
    ) -> PdfMaterial:
        # STRICT CROSS-TENANT HIERARCHY VERIFICATION
        subject = cls.get_subject_by_id(tenant_id, subject_id)
        if not subject:
            raise ValueError("Invalid subject or subject does not belong to your tenant.")

        title_obj = cls.get_title_by_id(tenant_id, title_id)
        if not title_obj:
            raise ValueError("Invalid title or title does not belong to your tenant.")

        if title_obj.subject_id != subject.id:
            raise ValueError("The selected title does not belong to the selected subject.")

        pdf = PdfMaterial(
            tenant_id=tenant_id,
            subject_id=subject_id,
            title_id=title_id,
            title=title.strip(),
            description=description.strip() if description else None,
            storage_key=storage_key,
            original_filename=original_filename.strip(),
            file_size=file_size,
            mime_type="application/pdf",
            sha256=sha256,
            is_published=is_published,
            download_count=0,
            uploaded_by=uploaded_by
        )
        db.session.add(pdf)
        db.session.commit()
        return pdf

    @classmethod
    def get_materials_for_title(cls, tenant_id: str, title_id: str, published_only: bool = False) -> list[PdfMaterial]:
        title = cls.get_title_by_id(tenant_id, title_id, published_only=published_only)
        if not title:
            return []

        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.title_id == title_id,
            PdfMaterial.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(PdfMaterial.is_published.is_(True))
        return query.order_by(PdfMaterial.created_at.desc()).all()

    @classmethod
    def get_material_by_id(cls, tenant_id: str, pdf_id: str, published_only: bool = False) -> PdfMaterial | None:
        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.id == pdf_id,
            PdfMaterial.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(PdfMaterial.is_published.is_(True))
        return query.first()

    @classmethod
    def replace_pdf_material(
        cls,
        tenant_id: str,
        replaced_by: str,
        pdf_id: str,
        new_storage_key: str,
        new_original_filename: str,
        new_file_size: int,
        new_sha256: str
    ) -> PdfMaterial:
        pdf = cls.get_material_by_id(tenant_id, pdf_id)
        if not pdf:
            raise ValueError("PDF material not found in your tenant.")

        # Archive the existing current version in pdf_versions
        version = PdfVersion(
            tenant_id=tenant_id,
            pdf_id=pdf.id,
            storage_key=pdf.storage_key,
            original_filename=pdf.original_filename,
            file_size=pdf.file_size,
            sha256=pdf.sha256,
            replaced_by=replaced_by
        )
        db.session.add(version)

        # Update current record
        pdf.storage_key = new_storage_key
        pdf.original_filename = new_original_filename.strip()
        pdf.file_size = new_file_size
        pdf.sha256 = new_sha256
        pdf.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        return pdf

    @classmethod
    def update_material_metadata(
        cls,
        tenant_id: str,
        pdf_id: str,
        title: str = None,
        description: str = None,
        is_published: bool = None
    ) -> PdfMaterial:
        pdf = cls.get_material_by_id(tenant_id, pdf_id)
        if not pdf:
            raise ValueError("PDF material not found in your tenant.")

        if title is not None:
            pdf.title = title.strip()
        if description is not None:
            pdf.description = description.strip() if description else None
        if is_published is not None:
            pdf.is_published = is_published

        db.session.commit()
        return pdf

    @classmethod
    def delete_material(cls, tenant_id: str, pdf_id: str, soft: bool = True):
        pdf = cls.get_material_by_id(tenant_id, pdf_id)
        if not pdf:
            raise ValueError("PDF material not found in your tenant.")

        if soft:
            pdf.deleted_at = datetime.now(timezone.utc)
        else:
            # Delete R2 file
            StorageService.delete_object(pdf.storage_key)
            for v in pdf.versions:
                StorageService.delete_object(v.storage_key)
            db.session.delete(pdf)

        db.session.commit()

    @classmethod
    def increment_download_count(cls, tenant_id: str, pdf_id: str):
        pdf = cls.get_material_by_id(tenant_id, pdf_id)
        if pdf:
            pdf.download_count += 1
            db.session.commit()

    @classmethod
    def get_tenant_recent_materials(cls, tenant_id: str, limit: int = 6, published_only: bool = True) -> list[PdfMaterial]:
        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(PdfMaterial.is_published.is_(True))
        return query.order_by(PdfMaterial.created_at.desc()).limit(limit).all()

    @classmethod
    def get_tenant_content_stats(cls, tenant_id: str) -> dict:
        """Tenant-level analytics (subjects, titles, materials, downloads, storage)."""
        subjects_count = db.session.query(func.count(Subject.id)).filter(
            Subject.tenant_id == tenant_id,
            Subject.deleted_at.is_(None)
        ).scalar() or 0

        titles_count = db.session.query(func.count(SubjectTitle.id)).filter(
            SubjectTitle.tenant_id == tenant_id,
            SubjectTitle.deleted_at.is_(None)
        ).scalar() or 0

        materials_count = db.session.query(func.count(PdfMaterial.id)).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        published_materials = db.session.query(func.count(PdfMaterial.id)).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.is_published.is_(True),
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        total_downloads = db.session.query(func.coalesce(func.sum(PdfMaterial.download_count), 0)).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        storage_used = StorageService.get_tenant_storage_used(tenant_id)

        return {
            "subjects_count": subjects_count,
            "titles_count": titles_count,
            "materials_count": materials_count,
            "published_materials": published_materials,
            "total_downloads": total_downloads,
            "storage_used_bytes": storage_used,
            "storage_used_mb": round(storage_used / (1024 * 1024), 2),
            "storage_limit_mb": round(9663676416 / (1024 * 1024), 2)
        }
