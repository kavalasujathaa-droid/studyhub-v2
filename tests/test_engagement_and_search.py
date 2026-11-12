import pytest
from studyhub.services.engagement_service import EngagementService

def test_global_bookmarking_and_collections(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        user = env["student_a1"]
        pdf_a = env["pdf_a"]
        pdf_b = env["pdf_b"]

        # Student A can bookmark both Admin A's and Admin B's PDFs (global shared library)
        assert not EngagementService.is_bookmarked(user.id, pdf_a.id)
        assert EngagementService.toggle_bookmark(user.id, pdf_a.id) is True
        assert EngagementService.is_bookmarked(user.id, pdf_a.id)

        # Create Collection
        col = EngagementService.create_bookmark_collection(user.id, "Finals Revision")
        assert col.name == "Finals Revision"

        # Bookmark PDF B into collection
        assert EngagementService.toggle_bookmark(user.id, pdf_b.id, collection_id=col.id) is True

        bookmarks_all = EngagementService.get_user_bookmarks(user.id)
        assert len(bookmarks_all) == 2

        bookmarks_col = EngagementService.get_user_bookmarks(user.id, collection_id=col.id)
        assert len(bookmarks_col) == 1
        assert bookmarks_col[0].id == pdf_b.id

def test_reading_progress_and_history(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        user = env["student_a1"]
        pdf_a = env["pdf_a"]

        EngagementService.record_view(user.id, pdf_a.id, page_number=5, reading_status="in_progress")
        history = EngagementService.get_user_viewing_history(user.id)
        assert len(history) == 1
        assert history[0]["pdf"].id == pdf_a.id
        assert history[0]["last_page"] == 5
        assert history[0]["reading_status"] == "in_progress"

        continue_list = EngagementService.get_continue_reading_materials(user.id)
        assert len(continue_list) == 1
        assert continue_list[0].id == pdf_a.id

        # Mark completed
        EngagementService.record_view(user.id, pdf_a.id, page_number=12, reading_status="completed")
        history_updated = EngagementService.get_user_viewing_history(user.id)
        assert history_updated[0]["reading_status"] == "completed"

def test_private_study_notes_crud(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        user = env["student_a1"]
        other_user = env["student_b1"]
        pdf_a = env["pdf_a"]

        # Create note
        note = EngagementService.create_study_note(
            user_id=user.id,
            pdf_id=pdf_a.id,
            title="Tree Balancing Lemma",
            content="AVL balance factor must be in [-1, 0, 1].",
            page_number=3
        )
        assert note.title == "Tree Balancing Lemma"

        # User notes list
        notes = EngagementService.get_user_notes(user.id, pdf_id=pdf_a.id)
        assert len(notes) == 1

        # Other user cannot see note
        assert len(EngagementService.get_user_notes(other_user.id, pdf_id=pdf_a.id)) == 0

        # Other user cannot modify or delete note
        with pytest.raises(PermissionError):
            EngagementService.update_study_note(note.id, other_user.id, "Hacked", "Hacked")

        with pytest.raises(PermissionError):
            EngagementService.delete_study_note(note.id, other_user.id)

        # Original owner updates and deletes
        EngagementService.update_study_note(note.id, user.id, "Updated Lemma", "New content")
        assert EngagementService.get_user_notes(user.id)[0].title == "Updated Lemma"

        EngagementService.delete_study_note(note.id, user.id)
        assert len(EngagementService.get_user_notes(user.id)) == 0

def test_interest_recommendations_and_global_search(app, setup_shared_environment):
    env = setup_shared_environment
    with app.app_context():
        user = env["student_a1"]
        subject_a = env["subject_a"]
        cat_cs = env["category"]

        # Set interests
        EngagementService.set_user_interests(
            user_id=user.id,
            subject_ids=[subject_a.id],
            category_ids=[cat_cs.id],
            tag_names=["algorithms"]
        )

        rec_subjects = EngagementService.get_recommended_subjects(user.id)
        assert len(rec_subjects) >= 1
        assert any(s.id == subject_a.id for s in rec_subjects)

        rec_pdfs = EngagementService.get_recommended_pdfs(user.id)
        assert len(rec_pdfs) >= 1
        assert any(p.id == env["pdf_a"].id for p in rec_pdfs)

        # Global search
        results = EngagementService.search_library(query_str="BST")
        assert results.total >= 1
        assert results.items[0].id == env["pdf_a"].id

        results_vm = EngagementService.search_library(query_str="Memory")
        assert results_vm.total >= 1
        assert results_vm.items[0].id == env["pdf_b"].id
