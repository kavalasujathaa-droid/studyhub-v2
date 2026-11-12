from datetime import datetime, timezone, timedelta
from studyhub.extensions import db
from studyhub.models.communication import Notification, Announcement, ContentReport
from studyhub.models.content import PdfMaterial
from studyhub.models.user import User

class CommunicationService:
    """Manages In-App Notifications, Announcements, and PDF Content Reports."""

    # =========================================================================
    # IN-APP NOTIFICATIONS
    # =========================================================================

    @classmethod
    def send_notification(
        cls,
        title: str,
        message: str,
        user_id: str = None,
        notification_type: str = "general",
        link_url: str = None
    ) -> Notification:
        note = Notification(
            user_id=user_id,
            title=title.strip(),
            message=message.strip(),
            notification_type=notification_type,
            link_url=link_url
        )
        db.session.add(note)
        db.session.commit()
        return note

    @classmethod
    def get_user_notifications(cls, user_id: str, unread_only: bool = False, limit: int = 30) -> list[Notification]:
        query = db.session.query(Notification).filter(
            (Notification.user_id == user_id) | (Notification.user_id.is_(None))
        )
        if unread_only:
            query = query.filter(Notification.is_read.is_(False))
        return query.order_by(Notification.created_at.desc()).limit(limit).all()

    @classmethod
    def mark_as_read(cls, notification_id: str, user_id: str):
        note = db.session.get(Notification, notification_id)
        if note and (note.user_id == user_id or note.user_id is None):
            note.is_read = True
            db.session.commit()

    @classmethod
    def mark_all_as_read(cls, user_id: str):
        db.session.query(Notification).filter(
            (Notification.user_id == user_id) | (Notification.user_id.is_(None)),
            Notification.is_read.is_(False)
        ).update({"is_read": True}, synchronize_session=False)
        db.session.commit()

    # =========================================================================
    # ANNOUNCEMENTS
    # =========================================================================

    @classmethod
    def create_announcement(cls, author_id: str, title: str, content: str, is_pinned: bool = False) -> Announcement:
        ann = Announcement(
            author_id=author_id,
            title=title.strip(),
            content=content.strip(),
            is_pinned=is_pinned,
            is_published=True
        )
        db.session.add(ann)
        db.session.commit()
        return ann

    @classmethod
    def get_announcements(cls, limit: int = 10) -> list[Announcement]:
        return db.session.query(Announcement).filter_by(is_published=True).order_by(
            Announcement.is_pinned.desc(),
            Announcement.created_at.desc()
        ).limit(limit).all()

    # =========================================================================
    # CONTENT REPORTING & MODERATION
    # =========================================================================

    @classmethod
    def submit_report(cls, user_id: str, pdf_id: str, category: str, description: str) -> ContentReport:
        pdf = db.session.get(PdfMaterial, pdf_id)
        if not pdf or pdf.deleted_at is not None:
            raise ValueError("PDF document not found.")

        # Rate limit: max 2 pending reports from the same user for this PDF
        recent_count = db.session.query(ContentReport).filter(
            ContentReport.user_id == user_id,
            ContentReport.pdf_id == pdf_id,
            ContentReport.status == "pending"
        ).count()
        if recent_count >= 2:
            raise ValueError("You already have a pending report under review for this document.")

        report = ContentReport(
            user_id=user_id,
            pdf_id=pdf_id,
            category=category,
            description=description.strip(),
            status="pending"
        )
        db.session.add(report)
        db.session.commit()
        return report

    @classmethod
    def get_reports_for_admin_uploads(cls, admin_id: str) -> list[ContentReport]:
        """Returns reports submitted on PDFs uploaded by this specific admin."""
        return db.session.query(ContentReport).join(
            PdfMaterial, ContentReport.pdf_id == PdfMaterial.id
        ).filter(
            PdfMaterial.uploaded_by_admin_id == admin_id
        ).order_by(ContentReport.created_at.desc()).all()

    @classmethod
    def get_all_reports(cls, status: str = None) -> list[ContentReport]:
        """Returns all reports across the platform for Main Admin moderation."""
        query = db.session.query(ContentReport)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(ContentReport.created_at.desc()).all()

    @classmethod
    def resolve_report(cls, report_id: str, resolver_user: User, action: str, admin_notes: str = None):
        report = db.session.get(ContentReport, report_id)
        if not report:
            raise ValueError("Report not found.")

        pdf = report.pdf_material

        # Check permissions: Main Admin can resolve anything; Admin can resolve if it's their uploaded PDF
        if not resolver_user.is_main_admin() and pdf.uploaded_by_admin_id != resolver_user.id:
            raise PermissionError("Access denied.")

        if action == "unpublish_pdf" and pdf:
            pdf.is_published = False
            report.status = "action_taken"
        elif action == "delete_pdf" and pdf:
            pdf.deleted_at = datetime.now(timezone.utc)
            report.status = "action_taken"
        elif action in ["resolve", "resolved"]:
            report.status = "resolved"
        elif action in ["approve", "reviewed"]:
            report.status = "reviewed"
        elif action in ["dismiss", "dismissed"]:
            report.status = "dismissed"
        elif action == "under_review":
            report.status = "under_review"
        else:
            report.status = "reviewed"

        report.admin_notes = admin_notes.strip() if admin_notes else None
        report.resolved_by_id = resolver_user.id
        db.session.commit()
