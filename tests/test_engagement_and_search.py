import pytest
from studyhub.services.engagement_service import EngagementService

def test_bookmark_toggle_and_retrieval(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        student_a1_id = two_tenants["student_a1"].id
        pdf_a_id = two_tenants["pdf_a"].id

        # Initial check
        assert not EngagementService.is_bookmarked(tenant_a_id, student_a1_id, pdf_a_id)

        # Toggle on
        bookmarked = EngagementService.toggle_bookmark(tenant_a_id, student_a1_id, pdf_a_id)
        assert bookmarked is True
        assert EngagementService.is_bookmarked(tenant_a_id, student_a1_id, pdf_a_id)

        user_bookmarks = EngagementService.get_user_bookmarks(tenant_a_id, student_a1_id)
        assert len(user_bookmarks) == 1
        assert user_bookmarks[0].id == pdf_a_id

        # Toggle off
        bookmarked = EngagementService.toggle_bookmark(tenant_a_id, student_a1_id, pdf_a_id)
        assert bookmarked is False
        assert not EngagementService.is_bookmarked(tenant_a_id, student_a1_id, pdf_a_id)

def test_cannot_bookmark_foreign_pdf(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        student_a1_id = two_tenants["student_a1"].id
        pdf_b_id = two_tenants["pdf_b"].id

        with pytest.raises(ValueError, match="PDF not found in your institution"):
            EngagementService.toggle_bookmark(tenant_a_id, student_a1_id, pdf_b_id)

def test_viewing_history(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        student_a1_id = two_tenants["student_a1"].id
        pdf_a_id = two_tenants["pdf_a"].id

        EngagementService.record_view(tenant_a_id, student_a1_id, pdf_a_id)
        history = EngagementService.get_user_viewing_history(tenant_a_id, student_a1_id)

        assert len(history) == 1
        assert history[0].id == pdf_a_id

def test_tenant_isolated_search(app, two_tenants):
    with app.app_context():
        tenant_a_id = two_tenants["tenant_a"].id
        tenant_b_id = two_tenants["tenant_b"].id

        # Search for "Calculus" in Tenant A
        results_a = EngagementService.search_tenant_materials(tenant_a_id, "Calculus")
        assert len(results_a) == 1
        assert results_a[0].title == "Calculus Notes A"

        # Searching for "Calculus" in Tenant B returns empty list
        results_b = EngagementService.search_tenant_materials(tenant_b_id, "Calculus")
        assert len(results_b) == 0

        # Searching for "Mechanics" in Tenant A returns empty list
        results_a_mech = EngagementService.search_tenant_materials(tenant_a_id, "Mechanics")
        assert len(results_a_mech) == 0

        # Searching for "Mechanics" in Tenant B returns Mechanics Notes B
        results_b_mech = EngagementService.search_tenant_materials(tenant_b_id, "Mechanics")
        assert len(results_b_mech) == 1
        assert results_b_mech[0].title == "Mechanics Notes B"
