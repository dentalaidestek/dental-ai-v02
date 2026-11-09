"""Compact comment threads: lazy replies, reactions, menus and a small composer."""

import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session

from app import main
from app.expert_social_models import SocialComment, SocialPost
from test_browser import browser_app


@pytest.fixture
def comment_app(browser_app):
    base, tmp = browser_app
    with Session(main.engine) as session:
        session.add(SocialPost(id=1, author_id=1, text="Sentetik bilimsel tartışma", status="PUBLISHED", idempotency_key="compact-thread-post", request_hash="synthetic"))
        for ident, author, parent, text in (
            (1, 1, None, "Bilimsel kaynak önerisi."),
            (2, 2, None, "İkinci bilimsel görüş."),
            (3, 2, 1, "İlk yanıt: kaynak için teşekkürler."),
            (4, 1, 1, "İkinci yanıt: güncel yayın eklendi."),
        ):
            session.add(SocialComment(id=ident, post_id=1, author_id=author, parent_id=parent, text=text, status="PUBLISHED", idempotency_key=f"compact-thread-{ident}"))
        session.commit()
    return base, tmp


def open_comments(pw, base, width=360, user=1):
    browser = pw.chromium.launch(executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"), args=["--no-sandbox", "--single-process", "--no-zygote"])
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=width < 600, has_touch=width < 600)
    context.add_cookies([{"name": main.SESSION_COOKIE, "value": f"browser{user}", "url": base}])
    page = context.new_page()
    page.set_default_timeout(5000)
    requests = []
    page.on("request", lambda request: requests.append(request.url) if request.method == "GET" and urlsplit(request.url).path == "/api/expert-social/posts/1/comments" else None)
    page.goto(base + "/expert-support/expert/1")
    page.locator("[data-comments-toggle]").click()
    sheet = page.get_by_role("dialog", name="Yorumlar", exact=True)
    expect(sheet.locator('[data-comment-id="1"]')).to_be_visible()
    return browser, context, page, sheet, requests


def response_is(response, path, method="GET"):
    return urlsplit(response.url).path == path and response.request.method == method


@pytest.mark.parametrize("target", ["reply", "edit"])
def test_delayed_submit_preserves_newer_composer_target(comment_app, target):
    base, _ = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base)
        try:
            held = []

            def hold_submit(route):
                held.append((route, route.fetch()))
                page.evaluate("window.newerTargetSubmitHeld = true")

            pattern = "**/api/expert-social/posts/1/comments"
            page.route(pattern, hold_submit)
            area = sheet.get_by_role("textbox", name="Yorum metni")
            area.fill("İlk gönderilen bilimsel yorum.")
            sheet.get_by_role("button", name="Gönder", exact=True).click()
            page.wait_for_function("window.newerTargetSubmitHeld === true")
            row = sheet.locator('[data-comment-id="1"]')
            if target == "reply":
                row.get_by_role("button", name="Yanıtla", exact=True).click()
            else:
                row.get_by_label("Yorum seçenekleri", exact=True).click()
                row.get_by_role("button", name="Düzenle", exact=True).click()
            area.fill("Korunacak yeni bilimsel taslak.")
            route, response = held[0]
            assert response.status == 200
            route.fulfill(response=response)
            page.wait_for_function("!document.querySelector('.ds-comment-send').hasAttribute('aria-busy')")
            expect(area).to_have_value("Korunacak yeni bilimsel taslak.")
            expect(sheet.locator(".ds-comment-context")).to_be_visible()
            page.unroute(pattern, hold_submit)
            path = "/api/expert-social/posts/1/comments" if target == "reply" else "/api/expert-social/comments/1"
            method = "POST" if target == "reply" else "PATCH"
            with page.expect_response(lambda result: response_is(result, path, method)) as saved:
                sheet.get_by_role("button", name="Gönder", exact=True).click()
            assert saved.value.status == 200
            result = saved.value.json()
            assert result["text"] == "Korunacak yeni bilimsel taslak."
            if target == "reply":
                assert result["parent_id"] == 1
            else:
                assert result["id"] == 1
            expect(area).to_have_value("")
        finally:
            browser.close()


def expand_replies(page, root):
    with page.expect_response(lambda response: response_is(response, "/api/expert-social/posts/1/comments") and parse_qs(urlsplit(response.url).query).get("parent_id") == ["1"]) as result:
        root.locator("[data-replies-toggle]").click()
    assert result.value.status == 200


@pytest.mark.parametrize("width", [360, 430, 1280])
def test_compact_roots_load_replies_only_after_expansion(comment_app, width):
    base, tmp = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, requests = open_comments(pw, base, width)
        expect(sheet.locator(".ds-comment")).to_have_count(2)
        assert any(parse_qs(urlsplit(url).query).get("threaded") == ["true"] for url in requests)
        assert not any("parent_id" in parse_qs(urlsplit(url).query) for url in requests)
        root = sheet.locator('[data-comment-id="1"]')
        expect(root.get_by_text("Bilimsel kaynak önerisi.", exact=True)).to_have_css("font-size", "14px")
        assert root.bounding_box()["height"] <= 116
        expect(root.locator(".ds-comment-avatar")).to_have_css("width", "32px")
        expect(root.get_by_role("button", name="Düzenle", exact=True)).to_have_count(0)
        expect(root.get_by_role("button", name="Sil", exact=True)).to_have_count(0)
        expect(root.get_by_role("button", name="Bildir", exact=True)).to_have_count(0)
        expect(root.get_by_label("Yorum seçenekleri", exact=True)).to_be_visible()
        toggle = root.locator("[data-replies-toggle]")
        expect(toggle).to_have_text("2 yanıtı görüntüle")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expand_replies(page, root)
        expect(sheet.locator('[data-comment-id="3"]')).to_be_visible()
        expect(sheet.locator('[data-comment-id="4"]')).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        for ident in (3, 4):
            reply = sheet.locator(f'[data-comment-id="{ident}"]')
            expect(reply.locator(".ds-comment-avatar")).to_have_css("width", "24px")
            expect(reply).to_have_css("border-left-width", "0px")
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(sheet.locator('[data-comment-id="3"]')).not_to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest / f"compact-comments-{width}.png"), animations="disabled")
        browser.close()


def test_small_composer_inserts_emoji_at_caret_and_survives_short_viewport(comment_app):
    base, _ = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base)
        area = sheet.get_by_role("textbox", name="Yorum metni")
        submit = sheet.get_by_role("button", name="Gönder", exact=True)
        expect(submit).to_be_disabled()
        expect(area).to_have_attribute("rows", "1")
        assert area.bounding_box()["height"] <= 48
        expect(submit.locator("svg")).to_have_count(1)
        expect(submit).to_have_text("")
        expect(sheet.locator(".ds-comment-input .ds-comment-send")).to_have_count(1)
        expect(submit).to_have_css("background-color", "rgb(17, 17, 17)")
        assert submit.bounding_box()["width"] == submit.bounding_box()["height"] == 34
        area.fill("Kaynak önerisi")
        area.evaluate("node => node.setSelectionRange(7, 7)")
        sheet.get_by_role("button", name="Emoji ekle", exact=True).click()
        sheet.get_by_role("button", name="😊", exact=True).click()
        expect(area).to_have_value("Kaynak 😊önerisi")
        page.set_viewport_size({"width": 360, "height": 600})
        area.focus()
        page.wait_for_function("document.querySelector('[data-comments-sheet] .ds-comment-form').getBoundingClientRect().bottom <= innerHeight + 1")
        assert sheet.locator(".ds-comments-scroll").bounding_box()["height"] >= 120
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/posts/1/comments", "POST")) as result:
            submit.click()
        assert result.value.status == 200
        ident = result.value.json()["id"]
        expect(sheet.locator(f'[data-comment-id="{ident}"]')).to_contain_text("Kaynak 😊önerisi")
        expect(page.locator("[data-comments-toggle]")).to_contain_text("5 yorum")
        expect(area).to_have_value("")
        expect(submit).to_be_disabled()
        browser.close()


def test_comment_menus_edit_report_and_delete_parent_with_replies(comment_app):
    base, _ = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base, 430)
        root = sheet.locator('[data-comment-id="1"]')
        root.get_by_label("Yorum seçenekleri", exact=True).click()
        root.get_by_role("button", name="Düzenle", exact=True).click()
        area = sheet.get_by_role("textbox", name="Yorum metni")
        expect(area).to_have_value("Bilimsel kaynak önerisi.")
        area.fill("Düzenlenmiş bilimsel görüş.")
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1", "PATCH")) as result:
            sheet.get_by_role("button", name="Gönder", exact=True).click()
        assert result.value.status == 200
        expect(root).to_contain_text("Düzenlenmiş bilimsel görüş.")
        other = sheet.locator('[data-comment-id="2"]')
        other.get_by_label("Yorum seçenekleri", exact=True).click()
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/reports", "POST")) as result:
            other.get_by_role("button", name="Bildir", exact=True).click()
        assert result.value.status == 200
        expect(sheet.get_by_text("Bildiriminiz inceleme için alındı.", exact=True)).to_be_visible()
        expand_replies(page, root)
        expect(sheet.locator('[data-comment-id="3"]')).to_be_visible()
        root.get_by_label("Yorum seçenekleri", exact=True).click()
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1", "DELETE")) as result:
            root.get_by_role("button", name="Sil", exact=True).click()
        assert result.value.status == 200
        for ident in (1, 3, 4):
            expect(sheet.locator(f'[data-comment-id="{ident}"]')).to_have_count(0)
        expect(page.locator("[data-comments-toggle]")).to_contain_text("1 yorum")
        browser.close()


@pytest.mark.parametrize("user,width", [(1, 360), (2, 1280)])
def test_comment_likes_persist_and_block_double_submission_with_visible_errors(comment_app, user, width):
    base, _ = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base, width, user)
        like = sheet.locator('[data-comment-id="1"] [data-comment-like]')
        expect(like.locator("svg")).to_have_count(1)
        expect(like).to_have_text("0")
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1/like", "PUT")) as result:
            like.click()
        assert result.value.status == 200
        expect(like).to_have_text("1")
        expect(like).to_have_attribute("aria-pressed", "true")
        page.reload()
        page.locator("[data-comments-toggle]").click()
        expect(like).to_have_text("1")
        expect(like).to_have_attribute("aria-pressed", "true")
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1/like", "PUT")) as result:
            like.click()
        assert result.value.status == 200
        expect(like).to_have_text("0")
        held = []
        pattern = "**/api/expert-social/comments/1/like"
        page.route(pattern, lambda route: held.append(route))
        with page.expect_request(lambda request: urlsplit(request.url).path == "/api/expert-social/comments/1/like"):
            like.evaluate("button => { button.click(); button.click(); }")
        expect(like).to_be_disabled()
        assert len(held) == 1
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1/like", "PUT")) as result:
            held[0].continue_()
        assert result.value.status == 200
        expect(like).to_have_text("1")
        page.unroute(pattern)
        message = "Yorum beğenisi şu anda kaydedilemiyor."
        page.route(pattern, lambda route: route.fulfill(status=503, json={"detail": message}))
        with page.expect_response(lambda response: response_is(response, "/api/expert-social/comments/1/like", "PUT")):
            like.click()
        expect(like).to_be_enabled()
        expect(like).to_have_text("1")
        expect(like).to_have_attribute("aria-pressed", "true")
        feedback = sheet.get_by_text(message, exact=True)
        expect(feedback).to_be_visible()
        bounds = feedback.bounding_box()
        assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= page.viewport_size["height"] + 1
        browser.close()


def test_close_and_back_keep_draft_and_verified_profile_links_work(comment_app):
    base, _ = comment_app
    with sync_playwright() as pw:
        browser, _, page, sheet, _ = open_comments(pw, base, 430, 2)
        area = sheet.get_by_role("textbox", name="Yorum metni")
        area.fill("Korunan kısa yorum 😊")
        sheet.get_by_role("button", name="Yorumları kapat", exact=True).click()
        expect(sheet).not_to_be_visible()
        page.locator("[data-comments-toggle]").click()
        expect(area).to_have_value("Korunan kısa yorum 😊")
        page.go_back()
        expect(sheet).not_to_be_visible()
        page.locator("[data-comments-toggle]").click()
        expect(area).to_have_value("Korunan kısa yorum 😊")
        link = sheet.locator('[data-comment-id="1"]').get_by_role("link", name="Uzm. Dt. Test Uzman", exact=True)
        expect(link).to_have_attribute("href", "/expert-support/expert/1")
        with page.expect_navigation(wait_until="domcontentloaded"):
            link.click()
        expect(page.locator("[data-comments-sheet][open]")).to_have_count(0)
        expect(page.locator("h1")).to_contain_text("Test Uzman")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
