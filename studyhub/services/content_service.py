from datetime import datetime, timezone
from sqlalchemy import func, or_
from studyhub.extensions import db
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial, PdfVersion
from studyhub.models.metadata import Category, Tag, subject_categories, subject_tags, pdf_tags
from studyhub.models.user import User
from studyhub.models.audit import AuditLog
from studyhub.services.storage_service import StorageService

class ContentService:
    """Manages the Shared Global Content Library (Subjects, Titles, PDFs, Categories, Tags)."""

    # =========================================================================
    # CATEGORIES & TAGS MANAGEMENT
    # =========================================================================

    @classmethod
    def get_or_create_category(cls, name: str, description: str = None, icon: str = "bi-folder", creator_id: str = None) -> Category:
        clean_name = name.strip()
        cat = db.session.query(Category).filter_by(name=clean_name).first()
        if not cat:
            cat = Category(
                name=clean_name,
                description=description.strip() if description else None,
                icon=icon or "bi-folder",
                created_by_admin_id=creator_id
            )
            db.session.add(cat)
            db.session.commit()
        return cat

    @classmethod
    def get_all_categories(cls) -> list[Category]:
        return db.session.query(Category).order_by(Category.name.asc()).all()

    @classmethod
    def get_or_create_tags(cls, tag_names: list[str]) -> list[Tag]:
        tags = []
        for name in tag_names:
            clean = name.strip().lower()
            if not clean:
                continue
            tag = db.session.query(Tag).filter_by(name=clean).first()
            if not tag:
                tag = Tag(name=clean)
                db.session.add(tag)
                db.session.flush()
            tags.append(tag)
        db.session.commit()
        return tags

    @classmethod
    def get_all_tags(cls) -> list[Tag]:
        return db.session.query(Tag).order_by(Tag.name.asc()).all()

    # =========================================================================
    # SHARED SUBJECT MANAGEMENT
    # =========================================================================

    @classmethod
    def create_subject(
        cls,
        subject_name: str,
        created_by_admin_id: str,
        description: str = None,
        icon: str = "bi-journal-bookmark",
        cover_image_url: str = None,
        sort_order: int = 0,
        is_published: bool = True,
        category_ids: list[str] = None,
        tag_names: list[str] = None
    ) -> Subject:
        clean_name = subject_name.strip()
        existing = db.session.query(Subject).filter(
            Subject.subject_name == clean_name,
            Subject.deleted_at.is_(None)
        ).first()
        if existing:
            raise ValueError(f"A subject named '{clean_name}' already exists in the shared library.")

        subject = Subject(
            subject_name=clean_name,
            description=description.strip() if description else None,
            icon=icon or "bi-journal-bookmark",
            cover_image_url=cover_image_url.strip() if cover_image_url else None,
            sort_order=sort_order,
            is_published=is_published,
            created_by_admin_id=created_by_admin_id
        )
        db.session.add(subject)
        db.session.flush()

        # Attach categories
        if category_ids:
            cats = db.session.query(Category).filter(Category.id.in_(category_ids)).all()
            subject.categories = cats

        # Attach tags
        if tag_names:
            tags = cls.get_or_create_tags(tag_names)
            subject.tags = tags

        db.session.commit()
        return subject

    @classmethod
    def get_all_subjects(cls, published_only: bool = True, category_id: str = None, search: str = None) -> list[Subject]:
        query = db.session.query(Subject).filter(Subject.deleted_at.is_(None))
        if published_only:
            query = query.filter(Subject.is_published.is_(True))
        if category_id:
            query = query.join(Subject.categories).filter(Category.id == category_id)
        if search:
            term = f"%{search.strip().lower()}%"
            query = query.filter(Subject.subject_name.ilike(term))
        return query.order_by(Subject.sort_order.asc(), Subject.subject_name.asc()).all()

    @classmethod
    def get_subject_by_id(cls, subject_id: str, published_only: bool = False) -> Subject | None:
        query = db.session.query(Subject).filter(
            Subject.id == subject_id,
            Subject.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(Subject.is_published.is_(True))
        return query.first()

    @classmethod
    def update_subject(
        cls,
        subject_id: str,
        user: User,
        subject_name: str = None,
        description: str = None,
        icon: str = None,
        cover_image_url: str = None,
        sort_order: int = None,
        is_published: bool = None,
        category_ids: list[str] = None,
        tag_names: list[str] = None
    ) -> Subject:
        subject = db.session.get(Subject, subject_id)
        if not subject or subject.deleted_at is not None:
            raise ValueError("Subject not found.")

        # Permission check: Creator or Main Admin
        if not user.is_main_admin() and subject.created_by_admin_id != user.id:
            raise PermissionError("Only the creator administrator or Main Admin can modify this subject.")

        if subject_name:
            clean_name = subject_name.strip()
            if clean_name != subject.subject_name:
                conflict = db.session.query(Subject).filter(
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
        if cover_image_url is not None:
            subject.cover_image_url = cover_image_url.strip() if cover_image_url else None
        if sort_order is not None:
            subject.sort_order = sort_order
        if is_published is not None:
            subject.is_published = is_published

        if category_ids is not None:
            cats = db.session.query(Category).filter(Category.id.in_(category_ids)).all()
            subject.categories = cats

        if tag_names is not None:
            tags = cls.get_or_create_tags(tag_names)
            subject.tags = tags

        db.session.commit()
        return subject

    @classmethod
    def delete_subject(cls, subject_id: str, user: User, soft: bool = True):
        subject = db.session.get(Subject, subject_id)
        if not subject or subject.deleted_at is not None:
            raise ValueError("Subject not found.")

        if not user.is_main_admin() and subject.created_by_admin_id != user.id:
            raise PermissionError("Only the creator administrator or Main Admin can delete this subject.")

        if soft:
            now = datetime.now(timezone.utc)
            subject.deleted_at = now
            for title in subject.titles:
                title.deleted_at = now
            for pdf in subject.pdf_materials:
                pdf.deleted_at = now
        else:
            db.session.delete(subject)

        db.session.commit()

    @classmethod
    def restore_subject(cls, subject_id: str, user: User):
        """Restores a soft-deleted subject and its child entities (Main Admin or Creator)."""
        subject = db.session.get(Subject, subject_id)
        if not subject:
            raise ValueError("Subject not found.")
        if not user.is_main_admin() and subject.created_by_admin_id != user.id:
            raise PermissionError("Permission denied.")

        subject.deleted_at = None
        for title in subject.titles:
            title.deleted_at = None
        for pdf in subject.pdf_materials:
            pdf.deleted_at = None

        db.session.commit()

    # =========================================================================
    # SHARED TITLE / PLAYLIST MANAGEMENT
    # =========================================================================

    @classmethod
    def create_title(
        cls,
        subject_id: str,
        title_name: str,
        created_by_admin_id: str,
        description: str = None,
        sort_order: int = 0,
        is_published: bool = True
    ) -> SubjectTitle:
        subject = cls.get_subject_by_id(subject_id)
        if not subject:
            raise ValueError("Subject does not exist.")

        clean_name = title_name.strip()
        existing = db.session.query(SubjectTitle).filter(
            SubjectTitle.subject_id == subject_id,
            SubjectTitle.title_name == clean_name,
            SubjectTitle.deleted_at.is_(None)
        ).first()
        if existing:
            raise ValueError(f"A title named '{clean_name}' already exists under this subject.")

        title = SubjectTitle(
            subject_id=subject_id,
            title_name=clean_name,
            description=description.strip() if description else None,
            sort_order=sort_order,
            is_published=is_published,
            created_by_admin_id=created_by_admin_id
        )
        db.session.add(title)
        db.session.commit()
        return title

    @classmethod
    def get_titles_for_subject(cls, subject_id: str, published_only: bool = True) -> list[SubjectTitle]:
        query = db.session.query(SubjectTitle).filter(
            SubjectTitle.subject_id == subject_id,
            SubjectTitle.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(SubjectTitle.is_published.is_(True))
        return query.order_by(SubjectTitle.sort_order.asc(), SubjectTitle.title_name.asc()).all()

    @classmethod
    def get_title_by_id(cls, title_id: str, published_only: bool = False) -> SubjectTitle | None:
        query = db.session.query(SubjectTitle).filter(
            SubjectTitle.id == title_id,
            SubjectTitle.deleted_at.is_(None)
        )
        if published_only:
            query = query.filter(SubjectTitle.is_published.is_(True))
        return query.first()

    @classmethod
    def update_title(
        cls,
        title_id: str,
        user: User,
        title_name: str = None,
        description: str = None,
        sort_order: int = None,
        is_published: bool = None
    ) -> SubjectTitle:
        title = db.session.get(SubjectTitle, title_id)
        if not title or title.deleted_at is not None:
            raise ValueError("Title not found.")

        if not user.is_main_admin() and title.created_by_admin_id != user.id:
            raise PermissionError("Only the creator administrator or Main Admin can modify this title.")

        if title_name:
            clean_name = title_name.strip()
            if clean_name != title.title_name:
                conflict = db.session.query(SubjectTitle).filter(
                    SubjectTitle.subject_id == title.subject_id,
                    SubjectTitle.title_name == clean_name,
                    SubjectTitle.id != title_id,
                    SubjectTitle.deleted_at.is_(None)
                ).first()
                if conflict:
                    raise ValueError(f"Another title named '{clean_name}' already exists in this subject.")
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
    def delete_title(cls, title_id: str, user: User, soft: bool = True):
        title = db.session.get(SubjectTitle, title_id)
        if not title or title.deleted_at is not None:
            raise ValueError("Title not found.")

        if not user.is_main_admin() and title.created_by_admin_id != user.id:
            raise PermissionError("Only the creator administrator or Main Admin can delete this title.")

        if soft:
            now = datetime.now(timezone.utc)
            title.deleted_at = now
            for pdf in title.pdf_materials:
                pdf.deleted_at = now
        else:
            db.session.delete(title)

        db.session.commit()

    # =========================================================================
    # PDF MATERIALS MANAGEMENT
    # =========================================================================

    @classmethod
    def create_pdf_material(
        cls,
        subject_id: str,
        title_id: str,
        title: str,
        description: str,
        storage_key: str,
        original_filename: str,
        file_size: int,
        sha256: str,
        uploaded_by_admin_id: str,
        language: str = "English",
        academic_year: str = None,
        semester: str = None,
        is_published: bool = True,
        scheduled_at: datetime = None,
        tag_names: list[str] = None
    ) -> PdfMaterial:
        subject = cls.get_subject_by_id(subject_id)
        if not subject:
            raise ValueError("Invalid subject.")

        title_obj = cls.get_title_by_id(title_id)
        if not title_obj or title_obj.subject_id != subject.id:
            raise ValueError("Selected title does not belong to the selected subject.")

        # Duplicate SHA-256 Check
        duplicate = db.session.query(PdfMaterial).filter(
            PdfMaterial.sha256 == sha256,
            PdfMaterial.deleted_at.is_(None)
        ).first()
        if duplicate:
            raise ValueError(f"Duplicate PDF detected! This exact file is already published under '{duplicate.title}' in {duplicate.subject.subject_name}.")

        pdf = PdfMaterial(
            subject_id=subject_id,
            title_id=title_id,
            title=title.strip(),
            description=description.strip() if description else None,
            storage_key=storage_key,
            original_filename=original_filename.strip(),
            file_size=file_size,
            mime_type="application/pdf",
            sha256=sha256,
            language=language or "English",
            academic_year=academic_year,
            semester=semester,
            is_published=is_published,
            scheduled_at=scheduled_at,
            uploaded_by_admin_id=uploaded_by_admin_id
        )
        db.session.add(pdf)
        db.session.flush()

        if tag_names:
            tags = cls.get_or_create_tags(tag_names)
            pdf.tags = tags

        db.session.commit()
        return pdf

    @classmethod
    def get_materials_for_title(cls, title_id: str, published_only: bool = True) -> list[PdfMaterial]:
        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.title_id == title_id,
            PdfMaterial.deleted_at.is_(None)
        )
        if published_only:
            now = datetime.now(timezone.utc)
            query = query.filter(
                PdfMaterial.is_published.is_(True),
                or_(PdfMaterial.scheduled_at.is_(None), PdfMaterial.scheduled_at <= now)
            )
        return query.order_by(PdfMaterial.created_at.desc()).all()

    @classmethod
    def get_material_by_id(cls, pdf_id: str, published_only: bool = False) -> PdfMaterial | None:
        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.id == pdf_id,
            PdfMaterial.deleted_at.is_(None)
        )
        if published_only:
            now = datetime.now(timezone.utc)
            query = query.filter(
                PdfMaterial.is_published.is_(True),
                or_(PdfMaterial.scheduled_at.is_(None), PdfMaterial.scheduled_at <= now)
            )
        return query.first()

    @classmethod
    def update_material(
        cls,
        pdf_id: str,
        user: User,
        title: str = None,
        description: str = None,
        language: str = None,
        academic_year: str = None,
        semester: str = None,
        is_published: bool = None
    ) -> PdfMaterial:
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF material not found.")

        if not user.is_main_admin() and pdf.uploaded_by_admin_id != user.id:
            raise PermissionError("Only the original uploader or Main Admin can edit this PDF.")

        if title is not None:
            pdf.title = title.strip()
        if description is not None:
            pdf.description = description.strip() if description else None
        if language is not None:
            pdf.language = language
        if academic_year is not None:
            pdf.academic_year = academic_year
        if semester is not None:
            pdf.semester = semester
        if is_published is not None:
            pdf.is_published = is_published

        db.session.commit()
        return pdf

    @classmethod
    def replace_pdf_material(
        cls,
        pdf_id: str,
        user: User,
        new_storage_key: str,
        new_original_filename: str,
        new_file_size: int,
        new_sha256: str
    ) -> PdfMaterial:
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF not found.")

        if not user.is_main_admin() and pdf.uploaded_by_admin_id != user.id:
            raise PermissionError("Only the original uploader or Main Admin can replace this PDF.")

        # Archive current version into pdf_versions
        next_ver = len(pdf.versions) + 1
        version = PdfVersion(
            pdf_id=pdf.id,
            storage_key=pdf.storage_key,
            original_filename=pdf.original_filename,
            file_size=pdf.file_size,
            sha256=pdf.sha256,
            version_number=next_ver,
            replaced_by_admin_id=user.id
        )
        pdf.versions.append(version)

        # Update active PDF record
        pdf.storage_key = new_storage_key
        pdf.original_filename = new_original_filename.strip()
        pdf.file_size = new_file_size
        pdf.sha256 = new_sha256
        pdf.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        return pdf

    @classmethod
    def restore_pdf_version(cls, pdf_id: str, version_id: str, user: User) -> PdfMaterial:
        """Restores an earlier archived version to become the active PDF."""
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF not found.")

        if not user.is_main_admin() and pdf.uploaded_by_admin_id != user.id:
            raise PermissionError("Only the original uploader or Main Admin can restore previous versions.")

        target_ver = db.session.get(PdfVersion, version_id)
        if not target_ver or target_ver.pdf_id != pdf.id:
            raise ValueError("Target version not found.")

        # Archive current state before restoring
        next_ver = len(pdf.versions) + 1
        current_archived = PdfVersion(
            pdf_id=pdf.id,
            storage_key=pdf.storage_key,
            original_filename=pdf.original_filename,
            file_size=pdf.file_size,
            sha256=pdf.sha256,
            version_number=next_ver,
            replaced_by_admin_id=user.id
        )
        pdf.versions.append(current_archived)

        # Restore from target_ver
        pdf.storage_key = target_ver.storage_key
        pdf.original_filename = target_ver.original_filename
        pdf.file_size = target_ver.file_size
        pdf.sha256 = target_ver.sha256
        pdf.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        return pdf

    @classmethod
    def delete_material(cls, pdf_id: str, user: User, soft: bool = True):
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF not found.")

        if not user.is_main_admin() and pdf.uploaded_by_admin_id != user.id:
            raise PermissionError("Only the original uploader or Main Admin can delete this PDF.")

        if soft:
            pdf.deleted_at = datetime.now(timezone.utc)
        else:
            StorageService.delete_object(pdf.storage_key)
            for v in pdf.versions:
                StorageService.delete_object(v.storage_key)
            db.session.delete(pdf)

        db.session.commit()

    @classmethod
    def restore_material(cls, pdf_id: str, user: User):
        """Recovers a soft-deleted PDF (Main Admin or original uploader)."""
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf:
            raise ValueError("PDF not found.")

        if not user.is_main_admin() and pdf.uploaded_by_admin_id != user.id:
            raise PermissionError("Permission denied.")

        pdf.deleted_at = None
        db.session.commit()

    @classmethod
    def increment_download_count(cls, pdf_id: str):
        pdf = db.session.get(PdfMaterial, pdf_id)
        if pdf:
            pdf.download_count += 1
            db.session.commit()

    @classmethod
    def increment_view_count(cls, pdf_id: str):
        pdf = db.session.get(PdfMaterial, pdf_id)
        if pdf:
            pdf.view_count += 1
            db.session.commit()

    @classmethod
    def get_recent_materials(cls, limit: int = 8, published_only: bool = True) -> list[PdfMaterial]:
        query = db.session.query(PdfMaterial).filter(PdfMaterial.deleted_at.is_(None))
        if published_only:
            query = query.filter(PdfMaterial.is_published.is_(True))
        return query.order_by(PdfMaterial.created_at.desc()).limit(limit).all()

    @classmethod
    def get_popular_materials(cls, limit: int = 8, published_only: bool = True) -> list[PdfMaterial]:
        query = db.session.query(PdfMaterial).filter(PdfMaterial.deleted_at.is_(None))
        if published_only:
            query = query.filter(PdfMaterial.is_published.is_(True))
        return query.order_by(PdfMaterial.download_count.desc(), PdfMaterial.view_count.desc()).limit(limit).all()

    @classmethod
    def get_admin_uploads(cls, admin_id: str, limit: int = 50) -> list[PdfMaterial]:
        return db.session.query(PdfMaterial).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).order_by(PdfMaterial.created_at.desc()).limit(limit).all()

    @classmethod
    def get_admin_analytics(cls, admin_id: str) -> dict:
        """Analytics for a specific administrator's contributions."""
        uploads_count = db.session.query(func.count(PdfMaterial.id)).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        downloads_count = db.session.query(func.coalesce(func.sum(PdfMaterial.download_count), 0)).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        views_count = db.session.query(func.coalesce(func.sum(PdfMaterial.view_count), 0)).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        students_count = db.session.query(func.count(User.id)).filter(
            User.created_by_admin_id == admin_id,
            User.role == "user"
        ).scalar() or 0

        # Storage used by admin's uploaded active materials
        storage_bytes = db.session.query(func.coalesce(func.sum(PdfMaterial.file_size), 0)).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).scalar() or 0

        most_downloaded = db.session.query(PdfMaterial).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id,
            PdfMaterial.deleted_at.is_(None)
        ).order_by(PdfMaterial.download_count.desc()).limit(5).all()

        return {
            "uploads_count": uploads_count,
            "downloads_count": downloads_count,
            "views_count": views_count,
            "students_count": students_count,
            "storage_used_mb": round(storage_bytes / (1024 * 1024), 2),
            "most_downloaded": most_downloaded
        }

    @classmethod
    def get_platform_analytics(cls) -> dict:
        """Global platform statistics for Main Admin."""
        total_admins = db.session.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0
        total_users = db.session.query(func.count(User.id)).filter(User.role.in_(["user", "student"])).scalar() or 0
        total_subjects = db.session.query(func.count(Subject.id)).filter(Subject.deleted_at.is_(None)).scalar() or 0
        total_titles = db.session.query(func.count(SubjectTitle.id)).filter(SubjectTitle.deleted_at.is_(None)).scalar() or 0
        total_pdfs = db.session.query(func.count(PdfMaterial.id)).filter(PdfMaterial.deleted_at.is_(None)).scalar() or 0
        total_downloads = db.session.query(func.coalesce(func.sum(PdfMaterial.download_count), 0)).filter(PdfMaterial.deleted_at.is_(None)).scalar() or 0
        total_views = db.session.query(func.coalesce(func.sum(PdfMaterial.view_count), 0)).filter(PdfMaterial.deleted_at.is_(None)).scalar() or 0
        total_storage_bytes = StorageService.get_total_storage_used()

        return {
            "total_admins": total_admins,
            "total_users": total_users,
            "total_subjects": total_subjects,
            "total_titles": total_titles,
            "total_pdfs": total_pdfs,
            "total_downloads": total_downloads,
            "total_views": total_views,
            "total_storage_mb": round(total_storage_bytes / (1024 * 1024), 2),
            "total_storage_gb": round(total_storage_bytes / (1024 * 1024 * 1024), 3)
        }
