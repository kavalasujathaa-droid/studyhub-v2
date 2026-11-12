from datetime import datetime, timezone
from sqlalchemy import or_
from studyhub.extensions import db
from studyhub.models.engagement import Bookmark, ViewingHistory
from studyhub.models.content import PdfMaterial, Subject, SubjectTitle

class EngagementService:
    """Manages bookmarks, viewing history, and tenant-scoped search."""

    @classmethod
    def toggle_bookmark(cls, tenant_id: str, user_id: str, pdf_id: str) -> bool:
        """Toggles bookmark on a PDF. Returns True if now bookmarked, False if removed."""
        # Ensure PDF belongs to this tenant and is published & active
        pdf = db.session.query(PdfMaterial).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.id == pdf_id,
            PdfMaterial.deleted_at.is_(None)
        ).first()
        if not pdf:
            raise ValueError("PDF not found in your institution.")

        existing = db.session.query(Bookmark).filter(
            Bookmark.tenant_id == tenant_id,
            Bookmark.user_id == user_id,
            Bookmark.pdf_id == pdf_id
        ).first()

        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False
        else:
            bookmark = Bookmark(
                tenant_id=tenant_id,
                user_id=user_id,
                pdf_id=pdf_id
            )
            db.session.add(bookmark)
            db.session.commit()
            return True

    @classmethod
    def is_bookmarked(cls, tenant_id: str, user_id: str, pdf_id: str) -> bool:
        return db.session.query(Bookmark).filter(
            Bookmark.tenant_id == tenant_id,
            Bookmark.user_id == user_id,
            Bookmark.pdf_id == pdf_id
        ).count() > 0

    @classmethod
    def get_user_bookmarks(cls, tenant_id: str, user_id: str) -> list[PdfMaterial]:
        """Returns list of bookmarked published PDFs for user in this tenant."""
        bookmarks = db.session.query(Bookmark).filter(
            Bookmark.tenant_id == tenant_id,
            Bookmark.user_id == user_id
        ).order_by(Bookmark.created_at.desc()).all()

        results = []
        for b in bookmarks:
            if b.pdf_material and b.pdf_material.is_published and b.pdf_material.deleted_at is None:
                results.append(b.pdf_material)
        return results

    @classmethod
    def record_view(cls, tenant_id: str, user_id: str, pdf_id: str):
        """Records or updates user viewing timestamp for a PDF."""
        # Check PDF belongs to tenant
        pdf = db.session.query(PdfMaterial).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.id == pdf_id,
            PdfMaterial.deleted_at.is_(None)
        ).first()
        if not pdf:
            return

        entry = ViewingHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            pdf_id=pdf_id,
            viewed_at=datetime.now(timezone.utc)
        )
        db.session.add(entry)
        db.session.commit()

    @classmethod
    def get_user_viewing_history(cls, tenant_id: str, user_id: str, limit: int = 10) -> list[PdfMaterial]:
        """Returns recently viewed published PDFs for user in this tenant."""
        history = db.session.query(ViewingHistory).filter(
            ViewingHistory.tenant_id == tenant_id,
            ViewingHistory.user_id == user_id
        ).order_by(ViewingHistory.viewed_at.desc()).limit(limit * 2).all()

        seen_ids = set()
        materials = []
        for h in history:
            if h.pdf_id not in seen_ids:
                seen_ids.add(h.pdf_id)
                if h.pdf_material and h.pdf_material.is_published and h.pdf_material.deleted_at is None:
                    materials.append(h.pdf_material)
                    if len(materials) >= limit:
                        break
        return materials

    @classmethod
    def search_tenant_materials(cls, tenant_id: str, query_str: str, limit: int = 25) -> list[PdfMaterial]:
        """Searches PDF materials strictly within tenant; only returns published content."""
        if not query_str or len(query_str.strip()) < 2:
            return []

        pattern = f"%{query_str.strip().lower()}%"

        # Search across material title, description, subject name, title name
        query = db.session.query(PdfMaterial).join(
            Subject, PdfMaterial.subject_id == Subject.id
        ).join(
            SubjectTitle, PdfMaterial.title_id == SubjectTitle.id
        ).filter(
            PdfMaterial.tenant_id == tenant_id,
            PdfMaterial.is_published.is_(True),
            PdfMaterial.deleted_at.is_(None),
            Subject.is_published.is_(True),
            Subject.deleted_at.is_(None),
            SubjectTitle.is_published.is_(True),
            SubjectTitle.deleted_at.is_(None),
            or_(
                PdfMaterial.title.ilike(pattern),
                PdfMaterial.description.ilike(pattern),
                Subject.subject_name.ilike(pattern),
                SubjectTitle.title_name.ilike(pattern)
            )
        ).order_by(PdfMaterial.created_at.desc()).limit(limit)

        return query.all()
