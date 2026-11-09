"""Bounded root/reply pagination and a fresh reply in a partially loaded thread."""

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialComment, SocialPost
from test_browser import browser_app
from test_compact_comments_browser import open_comments


def test_long_thread_pages_without_duplicates_and_new_reply_has_exact_count(browser_app):
    base, _ = browser_app
    with Session(main.engine) as session:
        session.add(SocialPost(id=1, author_id=1, text="Sentetik kaynak tartışması", status="PUBLISHED", idempotency_key="thread-pages", request_hash="synthetic"))
        for ident in range(1, 36):
            text = f"Bilimsel görüş {ident}."
            if ident == 2:
                text = "\n".join(f"Kaynak değerlendirmesi, bölüm {part}." for part in range(15))
            session.add(SocialComment(id=ident, post_id=1, author_id=1, text=text, status="PUBLISHED", idempotency_key=f"thread-root-{ident}"))
        for ident in range(101, 116):
            session.add(SocialComment(id=ident, post_id=1, parent_id=1, author_id=2, text=f"Kaynak yanıtı {ident}.", status="PUBLISHED", idempotency_key=f"thread-reply-{ident}"))
        session.commit()
    with sync_playwright() as pw:
        browser, _, page, sheet, requests = open_comments(pw, base, 360)
        expect(sheet.locator('.ds-comment-thread')).to_have_count(30)
        root = sheet.locator('[data-comment-id="1"]')
        expect(root.locator('[data-replies-toggle]')).to_have_text("15 yanıtı görüntüle")
        # Posting to a collapsed thread shows the new reply and lazily loads a page.
        root.get_by_role("button", name="Yanıtla", exact=True).click()
        sheet.get_by_role("textbox", name="Yorum metni").fill("Yeni bilimsel yanıtım.")
        sheet.get_by_role("button", name="Gönder", exact=True).click()
        expect(sheet.locator('[data-comment-id="116"]')).to_contain_text("Yeni bilimsel yanıtım.")
        expect(page.locator('[data-comments-toggle]')).to_contain_text("51 yorum")
        thread = sheet.locator('.ds-comment-thread').first
        expect(thread.locator('[data-reply="true"]')).to_have_count(11)
        thread.get_by_role("button", name="Diğer yanıtlar", exact=True).click()
        expect(thread.locator('[data-reply="true"]')).to_have_count(16)
        ids = thread.locator('[data-reply="true"]').evaluate_all("nodes => nodes.map(n => n.dataset.commentId)")
        assert len(ids) == len(set(ids)) == 16
        toggle = root.locator('[data-replies-toggle]')
        toggle.click()
        expect(toggle).to_have_text("16 yanıtı görüntüle")
        request_count = len(requests)
        toggle.click()
        expect(sheet.locator('[data-comment-id="116"]')).to_be_visible()
        assert len(requests) == request_count
        long = sheet.locator('[data-comment-id="2"]')
        expect(long.locator('.ds-comment-text')).to_have_class('ds-comment-text is-collapsed')
        long.get_by_role("button", name="daha fazla", exact=True).click()
        expect(long.locator('.ds-comment-text')).not_to_have_class('ds-comment-text is-collapsed')
        long.get_by_role("button", name="daha az", exact=True).click()
        sheet.get_by_role("button", name="Diğer yorumlar", exact=True).click()
        expect(sheet.locator('.ds-comment-thread')).to_have_count(35)
        expect(sheet.get_by_role("button", name="Diğer yorumlar", exact=True)).not_to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


@pytest.mark.parametrize('reply', [False, True])
def test_retry_after_lost_write_response_keeps_the_authoritative_count(browser_app, reply):
    base, _ = browser_app
    with Session(main.engine) as session:
        session.add(SocialPost(id=1, author_id=1, text="Sentetik bilimsel konu", status="PUBLISHED", idempotency_key="lost-response-post", request_hash="synthetic"))
        session.add(SocialComment(id=1, post_id=1, author_id=1, text="İlk bilimsel yorum.", status="PUBLISHED", idempotency_key="lost-response-existing"))
        session.commit()
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base, 430)
        def lose_response(route):
            if route.request.method == 'POST':
                committed = route.fetch()
                assert committed.status == 200
                route.fulfill(status=503, json={"detail": "Yanıt alınamadı; taslağı yeniden gönderebilirsiniz."})
            else:
                route.continue_()
        page.route('**/api/expert-social/posts/1/comments', lose_response)
        area = sheet.get_by_role('textbox', name='Yorum metni')
        if reply:
            sheet.locator('[data-comment-id="1"]').get_by_role('button', name='Yanıtla', exact=True).click()
        area.fill('Güvenle yeniden gönderilecek bilimsel yorum.')
        sheet.get_by_role('button', name='Gönder', exact=True).click()
        expect(sheet.get_by_text('Yanıt alınamadı; taslağı yeniden gönderebilirsiniz.', exact=True)).to_be_visible()
        sheet.get_by_role('button', name='Yorumları kapat', exact=True).click()
        page.locator('[data-comments-toggle]').click()
        expect(sheet.locator('.ds-comment')).to_have_count(1 if reply else 2)
        if reply:
            sheet.locator('[data-replies-toggle]').click()
            expect(sheet.locator('.ds-comment')).to_have_count(2)
        expect(page.locator('[data-comments-toggle]')).to_contain_text('2 yorum')
        page.unroute('**/api/expert-social/posts/1/comments')
        sheet.get_by_role('button', name='Gönder', exact=True).click()
        expect(area).to_have_value('')
        expect(page.locator('[data-comments-toggle]')).to_contain_text('2 yorum')
        expect(sheet.locator('.ds-comment')).to_have_count(2)
        if reply:
            sheet.locator('[data-replies-toggle]').click()
            expect(sheet.locator('[data-replies-toggle]')).to_have_text('1 yanıtı görüntüle')
        with Session(main.engine) as session:
            assert len(session.exec(select(SocialComment)).all()) == 2
        browser.close()
