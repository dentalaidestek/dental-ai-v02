"""A delayed thread snapshot cannot overwrite a newly persisted reply."""

from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session

from app import main
from app.expert_social_models import SocialComment, SocialPost
from test_browser import browser_app
from test_compact_comments_browser import open_comments, response_is


def seed_thread():
    with Session(main.engine) as session:
        session.add(SocialPost(
            id=1, author_id=1, text="Sentetik bilimsel tartışma",
            status="PUBLISHED", idempotency_key="snapshot-post", request_hash="synthetic",
        ))
        session.add(SocialComment(
            id=1, post_id=1, author_id=1, text="Bilimsel kaynak önerisi.",
            status="PUBLISHED", idempotency_key="snapshot-root",
        ))
        session.add(SocialComment(
            id=2, post_id=1, author_id=2, parent_id=1, text="Önceden eklenen bilimsel yanıt.",
            status="PUBLISHED", idempotency_key="snapshot-reply",
        ))
        session.commit()


def test_late_reply_snapshot_preserves_new_reply_and_authoritative_counts(browser_app):
    base, _ = browser_app
    seed_thread()
    with sync_playwright() as pw:
        browser, _, page, sheet, requests = open_comments(pw, base, 360)
        try:
            held = []
            pattern = "**/api/expert-social/posts/1/comments?*"

            def hold_reply_snapshot(route):
                if not held and parse_qs(urlsplit(route.request.url).query).get("parent_id") == ["1"]:
                    snapshot = route.fetch()
                    assert snapshot.status == 200
                    assert snapshot.json()["reply_count"] == 1
                    assert snapshot.json()["comment_count"] == 2
                    held.append((route, snapshot))
                    page.evaluate("window.commentSnapshotHeld = true")
                else:
                    route.continue_()

            page.route(pattern, hold_reply_snapshot)
            root = sheet.locator('[data-comment-id="1"]')
            replies_toggle = root.locator("[data-replies-toggle]")
            expect(replies_toggle).to_have_text("1 yanıtı görüntüle")
            replies_toggle.click()
            expect(replies_toggle).to_be_disabled()
            page.wait_for_function("window.commentSnapshotHeld === true")
            assert len(held) == 1

            root.get_by_role("button", name="Yanıtla", exact=True).click()
            sheet.get_by_role("textbox", name="Yorum metni").fill("Sonradan eklenen bilimsel yanıt.")
            with page.expect_response(lambda response: response_is(
                response, "/api/expert-social/posts/1/comments", "POST",
            )) as submitted:
                sheet.get_by_role("button", name="Gönder", exact=True).click()
            assert submitted.value.status == 200
            new_reply = submitted.value.json()
            assert new_reply["comment_count"] == 3
            expect(sheet.locator(f'[data-comment-id="{new_reply["id"]}"]')).to_be_visible()
            expect(page.locator("[data-comments-toggle]")).to_contain_text("3 yorum")

            # Capture only the first response so a corrective fetch can pass.
            # Unrouting a suspended handler would resume its request before
            # this explicit fulfillment in the installed Playwright version.
            route, snapshot = held[0]
            route.fulfill(response=snapshot)
            page.unroute(pattern, hold_reply_snapshot)

            thread = sheet.locator(".ds-comment-thread").first
            expect(thread.locator('[data-reply="true"]')).to_have_count(2)
            expect(replies_toggle).to_be_enabled()
            expect(page.locator("[data-comments-toggle]")).to_contain_text("3 yorum")
            replies_toggle.click()
            expect(replies_toggle).to_have_text("2 yanıtı görüntüle")
            reply_ids = thread.locator('[data-reply="true"]').evaluate_all(
                "nodes => nodes.map(node => Number(node.dataset.commentId))"
            )
            assert sorted(reply_ids) == [2, new_reply["id"]]
            reply_requests = [url for url in requests
                              if parse_qs(urlsplit(url).query).get("parent_id") == ["1"]]
            assert len(reply_requests) <= 2
        finally:
            browser.close()


def test_pending_reply_like_survives_a_corrective_thread_snapshot(browser_app):
    base, _ = browser_app
    seed_thread()
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base, 360)
        try:
            held_replies = []
            held_likes = []

            def hold_first_reply_snapshot(route):
                if not held_replies and parse_qs(urlsplit(route.request.url).query).get("parent_id") == ["1"]:
                    snapshot = route.fetch()
                    assert snapshot.status == 200
                    held_replies.append((route, snapshot))
                    page.evaluate("window.pendingLikeReplySnapshotHeld = true")
                else:
                    route.continue_()

            def hold_like(route):
                held_likes.append(route)
                page.evaluate("window.pendingLikeWriteHeld = true")

            page.route("**/api/expert-social/posts/1/comments?*", hold_first_reply_snapshot)
            root = sheet.locator('[data-comment-id="1"]')
            root.get_by_role("button", name="Yanıtla", exact=True).click()
            sheet.get_by_role("textbox", name="Yorum metni").fill("Beğenilecek yeni bilimsel yanıt.")
            with page.expect_response(lambda response: response_is(
                response, "/api/expert-social/posts/1/comments", "POST",
            )) as submitted:
                sheet.get_by_role("button", name="Gönder", exact=True).click()
            assert submitted.value.status == 200
            reply_id = submitted.value.json()["id"]
            page.wait_for_function("window.pendingLikeReplySnapshotHeld === true")
            like = sheet.locator(f'[data-comment-id="{reply_id}"] [data-comment-like]')
            expect(like).to_have_attribute("aria-pressed", "false")
            page.route(f"**/api/expert-social/comments/{reply_id}/like", hold_like)
            like.click()
            page.wait_for_function("window.pendingLikeWriteHeld === true")
            expect(like).to_be_disabled()

            # The old GET triggers a corrective snapshot while this like is
            # pending. The visible reaction must still reflect its eventual
            # successful response, even if a reply row was replaced.
            route, snapshot = held_replies[0]
            route.fulfill(response=snapshot)
            expect(sheet.get_by_role("button", name="Gönder", exact=True)).not_to_have_attribute("aria-busy", "true")
            with page.expect_response(lambda response: response_is(
                response, f"/api/expert-social/comments/{reply_id}/like", "PUT",
            )) as liked:
                held_likes[0].continue_()
            assert liked.value.status == 200
            assert liked.value.json() == {"liked": True, "like_count": 1}
            expect(like).to_have_attribute("aria-pressed", "true")
            expect(like).to_have_text("1")
            expect(sheet.locator('[data-reply="true"]')).to_have_count(2)
        finally:
            browser.close()
