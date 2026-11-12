import json
import pytest
from studyhub.models.user import User
from studyhub.services.communication_service import CommunicationService
from studyhub.services.backup_service import BackupService

def test_announcements_and_notifications(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        owner = env["owner"]
        student = env["student_a1"]

        # 1. Main Admin creates broadcast announcement
        ann = CommunicationService.create_announcement(
            author_id=owner.id,
            title="Winter Exam Guidelines 2026",
            content="Please review chapter 4 for final examinations.",
            is_pinned=True
        )
        assert ann.title == "Winter Exam Guidelines 2026"
        assert ann.is_pinned is True

        active_announcements = CommunicationService.get_announcements()
        assert len(active_announcements) >= 1
        assert active_announcements[0].title == "Winter Exam Guidelines 2026"

        # 2. Targeted In-App Notification
        note = CommunicationService.send_notification(
            user_id=student.id,
            title="Assignment Graded",
            message="Your DSA homework 1 has been reviewed.",
            notification_type="academic"
        )
        assert note.user_id == student.id
        assert note.is_read is False

        # Student checks unread notifications
        unreads = CommunicationService.get_user_notifications(student.id, unread_only=True)
        assert any(n.id == note.id for n in unreads)

        # Mark as read
        CommunicationService.mark_as_read(note.id, student.id)
        assert len(CommunicationService.get_user_notifications(student.id, unread_only=True)) == 0

def test_content_reporting_and_moderation_queue(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        student = env["student_a1"]
        admin_a = env["admin_a"]
        owner = env["owner"]
        pdf_b = env["pdf_b"]

        # Student reports a document
        report = CommunicationService.submit_report(
            user_id=student.id,
            pdf_id=pdf_b.id,
            category="incorrect_content",
            description="Formula on slide 14 has a sign error."
        )
        assert report.status == "pending"

        # Rate limit: duplicate pending report rejected if attempted 3 times
        CommunicationService.submit_report(
            user_id=student.id,
            pdf_id=pdf_b.id,
            category="incorrect_content",
            description="Second confirmation report."
        )
        with pytest.raises(ValueError, match="already have a pending report under review"):
            CommunicationService.submit_report(
                user_id=student.id,
                pdf_id=pdf_b.id,
                category="incorrect_content",
                description="Third report attempt"
            )

        # Admin Bob (uploader) reviews reports on his content
        bob_reports = CommunicationService.get_reports_for_admin_uploads(env["admin_b"].id)
        assert len(bob_reports) >= 1

        # Main Admin resolves report
        CommunicationService.resolve_report(
            report_id=report.id,
            resolver_user=owner,
            action="resolve",
            admin_notes="Verified and instructor uploaded revision."
        )
        assert report.status == "resolved"

def test_backup_metadata_export(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        json_str = BackupService.export_metadata_json()
        data = json.loads(json_str)

        assert "platform" in data
        assert data["platform"] == "StudyHub V2"
        assert "subjects" in data
        assert len(data["subjects"]) >= 2
        assert "categories" in data
        assert "total_records" in data
