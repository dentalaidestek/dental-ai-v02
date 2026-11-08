"""Real like persistence and visible feedback on owner/member profile pages."""

import io
import os

import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session

from app import main
from app.expert_social_models import SocialPost
from test_browser import browser_app


@pytest.fixture
def like_app(browser_app):
    base, _ = browser_app
    with Session(main.engine) as session:
        session.add(SocialPost(id=1, author_id=1, text="\n\n".join(f"Bilimsel kaynak üzerine görüş {i}." for i in range(30)), status="PUBLISHED", link_url="https://doi.org/10.1000/synthetic", preview_json='{"title":"Sentetik ORCID yayını","site_name":"ORCID"}', idempotency_key="like-feedback", request_hash="synthetic"))
        session.commit()
    return base


def profile(pw, base, user_id):
    browser = pw.chromium.launch(executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"), args=["--no-sandbox", "--single-process", "--no-zygote"])
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    context.add_cookies([{"name": main.SESSION_COOKIE, "value": f"browser{user_id}", "url": base}])
    page = context.new_page()
    page.goto(base + "/expert-support/expert/1")
    like = page.locator('[data-post-id="1"] .ds-actions button[aria-pressed]')
    expect(like).to_be_enabled()
    like.scroll_into_view_if_needed()
    return browser, context, page, like


def click_like(page, like):
    with page.expect_response(lambda response: response.url.endswith("/posts/1/like") and response.request.method == "PUT") as response:
        like.click()
    return response.value


def heart_interior_pixels(like):
    """A filled heart paints its center; an outline leaves the center white."""
    pixels = Image.open(io.BytesIO(like.locator(".ds-action-icon").screenshot())).convert("RGB")
    middle = pixels.crop((pixels.width // 3, pixels.height // 3, pixels.width * 2 // 3, pixels.height * 2 // 3))
    return sum(max(middle.getpixel((x, y))) < 235 for y in range(middle.height) for x in range(middle.width))


@pytest.mark.parametrize("user_id", [1, 2])
def test_owner_and_member_like_counts_persist_through_reload(like_app, user_id):
    with sync_playwright() as pw:
        browser, _, page, like = profile(pw, like_app, user_id)
        expect(like).to_have_text("0")
        response = click_like(page, like)
        assert response.status == 200 and response.json() == {"liked": True, "like_count": 1}
        expect(like).to_have_text("1")
        page.reload()
        expect(like).to_have_text("1")
        expect(like).to_have_attribute("aria-pressed", "true")
        response = click_like(page, like)
        assert response.status == 200 and response.json() == {"liked": False, "like_count": 0}
        expect(like).to_have_text("0")
        page.reload()
        expect(like).to_have_text("0")
        expect(like).to_have_attribute("aria-pressed", "false")
        browser.close()


@pytest.mark.parametrize("user_id", [1, 2])
def test_liked_heart_is_visibly_filled_and_accessibly_named(like_app, user_id):
    with sync_playwright() as pw:
        browser, _, page, like = profile(pw, like_app, user_id)
        outline = heart_interior_pixels(like)
        assert click_like(page, like).status == 200
        expect(like).to_have_text("1")
        expect(like).to_have_attribute("aria-pressed", "true")
        assert heart_interior_pixels(like) >= outline + 12
        expect(like).to_have_attribute("aria-label", "Beğenmekten vazgeç")
        page.reload()
        expect(like).to_have_text("1")
        like.scroll_into_view_if_needed()
        assert heart_interior_pixels(like) >= outline + 12
        assert click_like(page, like).status == 200
        expect(like).to_have_text("0")
        expect(like).to_have_attribute("aria-label", "Beğen")
        assert heart_interior_pixels(like) <= outline + 3
        browser.close()


def test_like_double_click_sends_one_request_while_in_flight(like_app):
    with sync_playwright() as pw:
        browser, _, page, like = profile(pw, like_app, 1)
        held = []
        page.route("**/api/expert-social/posts/1/like", lambda route: held.append(route))
        with page.expect_request(lambda request: request.url.endswith("/posts/1/like")):
            like.evaluate("button => { button.click(); button.click(); }")
        expect(like).to_be_disabled()
        assert len(held) == 1
        with page.expect_response(lambda response: response.url.endswith("/posts/1/like")) as response:
            held[0].continue_()
        assert response.value.status == 200
        expect(like).to_have_text("1")
        expect(like).to_be_enabled()
        page.reload()
        expect(like).to_have_text("1")
        browser.close()


@pytest.mark.parametrize("user_id,status", [(1, 401), (2, 503)])
def test_like_failure_is_visible_beside_the_bottom_action(like_app, user_id, status):
    with sync_playwright() as pw:
        browser, context, page, like = profile(pw, like_app, user_id)
        if status == 401:
            context.clear_cookies()
            message = "Üye girişi gerekiyor."
        else:
            message = "İşlem yoğunluğu nedeniyle biraz sonra yeniden deneyin."
            page.route("**/api/expert-social/posts/1/like", lambda route: route.fulfill(status=503, json={"detail": message}))
        response = click_like(page, like)
        assert response.status == status
        expect(like).to_be_enabled()
        expect(like).to_have_text("0")
        expect(like).to_have_attribute("aria-pressed", "false")
        assert page.evaluate("""message => [...document.querySelectorAll('[role="status"], [role="alert"]')].some(node => {
          const rect = node.getBoundingClientRect(), style = getComputedStyle(node);
          return node.textContent.includes(message) && rect.top >= 0 && rect.bottom <= innerHeight - 65 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        })""", message)
        browser.close()
