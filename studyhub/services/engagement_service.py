from datetime import datetime, timezone
from sqlalchemy import or_, desc, func
from studyhub.extensions import db
from studyhub.models.personalization import (
    UserInterest,
    BookmarkCollection,
    Bookmark,
    ViewingHistory,
    UserStudyNote,
    UserDownloadHistory,
)
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial
from studyhub.models.metadata import Category, Tag

class EngagementService:
    """Manages student personalization: interests, recommendations, bookmarks, study notes, and search."""

    # =========================================================================
    # PERSONAL INTERESTS & RECOMMENDATIONS
    # =========================================================================

    @classmethod
    def set_user_interests(cls, user_id: str, subject_ids: list[str] = None, category_ids: list[str] = None, tag_names: list[str] = None):
        """Replaces user interest preferences."""
        # Clear existing
        db.session.query(UserInterest).filter_by(user_id=user_id).delete()

        if subject_ids:
            for sid in set(subject_ids):
                if sid:
                    db.session.add(UserInterest(user_id=user_id, interest_type="subject", target_id=sid))
        if category_ids:
            for cid in set(category_ids):
                if cid:
                    db.session.add(UserInterest(user_id=user_id, interest_type="category", target_id=cid))
        if tag_names:
            for tag in set(tag_names):
                clean_tag = tag.strip().lower()
                if clean_tag:
                    db.session.add(UserInterest(user_id=user_id, interest_type="tag", target_id=clean_tag))

        db.session.commit()

    @classmethod
    def get_user_interests(cls, user_id: str) -> dict:
        interests = db.session.query(UserInterest).filter_by(user_id=user_id).all()
        return {
            "subject_ids": [i.target_id for i in interests if i.interest_type == "subject"],
            "category_ids": [i.target_id for i in interests if i.interest_type == "category"],
            "tag_names": [i.target_id for i in interests if i.interest_type == "tag"],
        }

    @classmethod
    def get_recommended_subjects(cls, user_id: str, limit: int = 6) -> list[Subject]:
        """
        Recommends published subjects based on user's selected interests.
        Falls back to popular / active subjects if no interests are set.
        """
        interests = cls.get_user_interests(user_id)
        sub_ids = interests["subject_ids"]
        cat_ids = interests["category_ids"]

        query = db.session.query(Subject).filter(
            Subject.is_published.is_(True),
            Subject.deleted_at.is_(None)
        )

        conditions = []
        if sub_ids:
            conditions.append(Subject.id.in_(sub_ids))
        if cat_ids:
            conditions.append(Subject.categories.any(Category.id.in_(cat_ids)))

        if conditions:
            recommended = query.filter(or_(*conditions)).limit(limit).all()
            if len(recommended) >= limit:
                return recommended
            # If fewer than limit, supplement with additional subjects
            existing_ids = set(s.id for s in recommended)
            fillers = query.filter(Subject.id.not_in(existing_ids)).limit(limit - len(recommended)).all()
            return recommended + fillers

        # Default fallback
        return query.order_by(Subject.sort_order.asc()).limit(limit).all()

    @classmethod
    def get_recommended_pdfs(cls, user_id: str, limit: int = 6) -> list[PdfMaterial]:
        """Recommends PDFs matching user's interests (subjects, categories, tags)."""
        interests = cls.get_user_interests(user_id)
        sub_ids = interests["subject_ids"]
        cat_ids = interests["category_ids"]
        tags = interests["tag_names"]

        now = datetime.now(timezone.utc)
        query = db.session.query(PdfMaterial).filter(
            PdfMaterial.is_published.is_(True),
            PdfMaterial.deleted_at.is_(None),
            or_(PdfMaterial.scheduled_at.is_(None), PdfMaterial.scheduled_at <= now)
        )

        conditions = []
        if sub_ids:
            conditions.append(PdfMaterial.subject_id.in_(sub_ids))
        if cat_ids:
            conditions.append(PdfMaterial.subject.has(Subject.categories.any(Category.id.in_(cat_ids))))
        if tags:
            conditions.append(PdfMaterial.tags.any(Tag.name.in_(tags)))

        if conditions:
            matched = query.filter(or_(*conditions)).order_by(PdfMaterial.download_count.desc()).limit(limit).all()
            if len(matched) >= limit:
                return matched
            existing_ids = set(p.id for p in matched)
            fillers = query.filter(PdfMaterial.id.not_in(existing_ids)).order_by(PdfMaterial.created_at.desc()).limit(limit - len(matched)).all()
            return matched + fillers

        return query.order_by(PdfMaterial.created_at.desc()).limit(limit).all()

    # =========================================================================
    # BOOKMARKS & COLLECTIONS
    # =========================================================================

    @classmethod
    def toggle_bookmark(cls, user_id: str, pdf_id: str, collection_id: str = None) -> bool:
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF document not found.")

        existing = db.session.query(Bookmark).filter_by(user_id=user_id, pdf_id=pdf_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False
        else:
            bm = Bookmark(user_id=user_id, pdf_id=pdf_id, collection_id=collection_id)
            db.session.add(bm)
            db.session.commit()
            return True

    @classmethod
    def is_bookmarked(cls, user_id: str, pdf_id: str) -> bool:
        return db.session.query(Bookmark).filter_by(user_id=user_id, pdf_id=pdf_id).count() > 0

    @classmethod
    def get_user_bookmarks(cls, user_id: str, collection_id: str = None) -> list[PdfMaterial]:
        query = db.session.query(Bookmark).filter_by(user_id=user_id)
        if collection_id:
            query = query.filter_by(collection_id=collection_id)
        bookmarks = query.order_by(Bookmark.created_at.desc()).all()

        results = []
        for b in bookmarks:
            if b.pdf_material and b.pdf_material.is_published and b.pdf_material.deleted_at is None:
                results.append(b.pdf_material)
        return results

    @classmethod
    def create_bookmark_collection(cls, user_id: str, name: str, description: str = None) -> BookmarkCollection:
        clean_name = name.strip()
        existing = db.session.query(BookmarkCollection).filter_by(user_id=user_id, name=clean_name).first()
        if existing:
            raise ValueError(f"Collection '{clean_name}' already exists.")

        col = BookmarkCollection(user_id=user_id, name=clean_name, description=description)
        db.session.add(col)
        db.session.commit()
        return col

    @classmethod
    def get_user_collections(cls, user_id: str) -> list[BookmarkCollection]:
        return db.session.query(BookmarkCollection).filter_by(user_id=user_id).order_by(BookmarkCollection.name.asc()).all()

    # =========================================================================
    # VIEWING HISTORY & STUDY PROGRESS
    # =========================================================================

    @classmethod
    def record_view(cls, user_id: str, pdf_id: str, page_number: int = 1, reading_status: str = "in_progress"):
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            return

        entry = db.session.query(ViewingHistory).filter_by(user_id=user_id, pdf_id=pdf_id).first()
        now = datetime.now(timezone.utc)

        if entry:
            entry.view_count += 1
            entry.last_viewed_at = now
            if page_number:
                entry.last_page = page_number
            if reading_status:
                entry.reading_status = reading_status
        else:
            entry = ViewingHistory(
                user_id=user_id,
                pdf_id=pdf_id,
                last_page=page_number or 1,
                reading_status=reading_status or "in_progress",
                view_count=1,
                last_viewed_at=now
            )
            db.session.add(entry)

        pdf.view_count += 1
        db.session.commit()

    @classmethod
    def get_user_viewing_history(cls, user_id: str, limit: int = 15) -> list[dict]:
        history = db.session.query(ViewingHistory).filter_by(user_id=user_id).order_by(
            ViewingHistory.last_viewed_at.desc()
        ).limit(limit).all()

        results = []
        for h in history:
            if h.pdf_material and h.pdf_material.is_published and h.pdf_material.deleted_at is None:
                results.append({
                    "pdf": h.pdf_material,
                    "last_page": h.last_page,
                    "reading_status": h.reading_status,
                    "view_count": h.view_count,
                    "last_viewed_at": h.last_viewed_at
                })
        return results

    @classmethod
    def get_continue_reading_materials(cls, user_id: str, limit: int = 5) -> list[PdfMaterial]:
        history = db.session.query(ViewingHistory).filter(
            ViewingHistory.user_id == user_id,
            ViewingHistory.reading_status == "in_progress"
        ).order_by(ViewingHistory.last_viewed_at.desc()).limit(limit).all()

        materials = []
        for h in history:
            if h.pdf_material and h.pdf_material.is_published and h.pdf_material.deleted_at is None:
                materials.append(h.pdf_material)
        return materials

    # =========================================================================
    # PRIVATE STUDY NOTES
    # =========================================================================

    @classmethod
    def create_study_note(cls, user_id: str, pdf_id: str, title: str, content: str, page_number: int = None) -> UserStudyNote:
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF not found.")

        note = UserStudyNote(
            user_id=user_id,
            pdf_id=pdf_id,
            title=title.strip(),
            content=content.strip(),
            page_number=page_number
        )
        db.session.add(note)
        db.session.commit()
        return note

    @classmethod
    def get_user_notes(cls, user_id: str, pdf_id: str = None, search: str = None) -> list[UserStudyNote]:
        query = db.session.query(UserStudyNote).filter_by(user_id=user_id)
        if pdf_id:
            query = query.filter_by(pdf_id=pdf_id)
        if search:
            term = f"%{search.strip().lower()}%"
            query = query.filter(or_(UserStudyNote.title.ilike(term), UserStudyNote.content.ilike(term)))
        return query.order_by(UserStudyNote.updated_at.desc()).all()

    @classmethod
    def update_study_note(cls, note_id: str, user_id: str, title: str, content: str, page_number: int = None) -> UserStudyNote:
        note = db.session.get(UserStudyNote, note_id)
        if not note or note.user_id != user_id:
            raise PermissionError("Note not found or access denied.")

        note.title = title.strip()
        note.content = content.strip()
        note.page_number = page_number
        db.session.commit()
        return note

    @classmethod
    def delete_study_note(cls, note_id: str, user_id: str):
        note = db.session.get(UserStudyNote, note_id)
        if not note or note.user_id != user_id:
            raise PermissionError("Note not found or access denied.")
        db.session.delete(note)
        db.session.commit()

    # =========================================================================
    # DOWNLOAD HISTORY
    # =========================================================================

    @classmethod
    def record_download(cls, user_id: str, pdf_id: str):
        record = UserDownloadHistory(user_id=user_id, pdf_id=pdf_id)
        db.session.add(record)
        db.session.commit()

    @classmethod
    def get_user_download_history(cls, user_id: str, limit: int = 20) -> list[PdfMaterial]:
        history = db.session.query(UserDownloadHistory).filter_by(user_id=user_id).order_by(
            UserDownloadHistory.downloaded_at.desc()
        ).limit(limit).all()

        seen = set()
        materials = []
        for h in history:
            if h.pdf_id not in seen and h.pdf_material and h.pdf_material.deleted_at is None:
                seen.add(h.pdf_id)
                materials.append(h.pdf_material)
        return materials

    # =========================================================================
    # GLOBAL SEARCH & DISCOVERY
    # =========================================================================

    @classmethod
    def search_library(
        cls,
        query_str: str = None,
        category_id: str = None,
        subject_id: str = None,
        tag: str = None,
        academic_year: str = None,
        semester: str = None,
        sort_by: str = "recent",
        page: int = 1,
        per_page: int = 12
    ):
        """Global search across shared library with parameterized SQL and indexing."""
        now = datetime.now(timezone.utc)
        query = db.session.query(PdfMaterial).join(
            Subject, PdfMaterial.subject_id == Subject.id
        ).join(
            SubjectTitle, PdfMaterial.title_id == SubjectTitle.id
        ).filter(
            PdfMaterial.is_published.is_(True),
            PdfMaterial.deleted_at.is_(None),
            Subject.is_published.is_(True),
            Subject.deleted_at.is_(None),
            SubjectTitle.is_published.is_(True),
            SubjectTitle.deleted_at.is_(None),
            or_(PdfMaterial.scheduled_at.is_(None), PdfMaterial.scheduled_at <= now)
        )

        if query_str and len(query_str.strip()) > 0:
            pattern = f"%{query_str.strip().lower()}%"
            query = query.filter(or_(
                PdfMaterial.title.ilike(pattern),
                PdfMaterial.description.ilike(pattern),
                Subject.subject_name.ilike(pattern),
                SubjectTitle.title_name.ilike(pattern)
            ))

        if category_id:
            query = query.filter(Subject.categories.any(Category.id == category_id))

        if subject_id:
            query = query.filter(PdfMaterial.subject_id == subject_id)

        if tag:
            clean_tag = tag.strip().lower()
            query = query.filter(or_(
                PdfMaterial.tags.any(Tag.name == clean_tag),
                Subject.tags.any(Tag.name == clean_tag)
            ))

        if academic_year:
            query = query.filter(PdfMaterial.academic_year == academic_year)

        if semester:
            query = query.filter(PdfMaterial.semester == semester)

        # Sorting
        if sort_by == "popular":
            query = query.order_by(PdfMaterial.download_count.desc(), PdfMaterial.view_count.desc())
        elif sort_by == "alphabetical":
            query = query.order_by(PdfMaterial.title.asc())
        else:
            query = query.order_by(PdfMaterial.created_at.desc())

        return query.paginate(page=page, per_page=per_page, error_out=False)
