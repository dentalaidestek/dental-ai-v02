"""Publication sharing stays compact and reports the persisted post outcome."""

import io
import os
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session, select

from app import main
from app.expert_social_models import Publication, SocialMedia, SocialPost
from test_browser import browser_app

TITLE = "Sentetik bilimsel araştırma: çok uzun bir yayın başlığı " * 3
URL = "https://example.org/research/synthetic"


@pytest.fixture(params=[(360, False), (430, False), (360, True), (430, True)])
def publication_page(browser_app, request):
    base, tmp = browser_app
    width, management = request.param
    with Session(main.engine) as session:
        session.add(Publication(id=1, expert_id=1, title=TITLE, journal="Sentetik Bilim Dergisi", year=2026, url=URL, source="ORCID", fingerprint="share-feedback", title_key="share-feedback", status="PUBLISHED"))
        session.commit()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"), args=["--no-sandbox", "--single-process", "--no-zygote"])
        context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
        context.add_cookies([{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + ("/expert-support/profile" if management else "/expert-support/expert/1"))
        page.locator("[data-manage-tab=publications]" if management else "[data-tab=publications]").click()
        page.locator("[data-publications]").get_by_role("button", name="Gönderi olarak paylaş").click()
        expect(page.locator("[data-preview] .ds-link-card strong")).to_have_text(TITLE)
        expect(page.locator("[data-composer]")).to_be_visible()
        yield page, context, base, tmp, width, management
        assert not errors, errors
        browser.close()


def cover_file(color="#1d7c86"):
    raw = io.BytesIO()
    Image.new("RGB", (600, 1000), color).save(raw, "PNG")
    return {"name": "synthetic-cover.png", "mimeType": "image/png", "buffer": raw.getvalue()}


def attach_cover(page, color="#1d7c86"):
    with page.expect_file_chooser() as chooser:
        page.locator("[data-cover]").click()
    with page.expect_response(lambda response: response.url.endswith("/api/expert-social/media") and response.request.method == "POST") as uploaded:
        chooser.value.set_files(cover_file(color))
    assert uploaded.value.status == 200
    expect(page.locator("[data-preview] img")).to_have_attribute("src", uploaded.value.json()["url"])
    expect(page.locator("[data-composer]")).to_be_visible()
    return uploaded.value.json()["id"]


def visible_status(page, message):
    expect(page.locator("[data-notice]")).to_contain_text(message)
    assert page.locator("[data-notice]").evaluate("node => {const r=node.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight-65 && r.height>0}")


def test_publication_is_one_card_with_optional_comment_and_one_replaceable_cover(publication_page):
    page, _, _, tmp, width, management = publication_page
    expect(page.locator("[data-post-text]")).to_have_value("")
    expect(page.locator("[data-preview] .ds-link-card")).to_have_attribute("href", URL)
    assert page.locator("[data-preview]").inner_text().count("Sentetik Bilim Dergisi") == 1
    first_id = attach_cover(page)
    expect(page.locator("[data-composer] img[alt='Bağlantı kapağı']")).to_have_count(1)
    expect(page.locator("[data-attachments] img")).to_have_count(0)
    assert page.locator("[data-preview] img").bounding_box()["height"] <= 180
    second_id = attach_cover(page, "#508c47")
    assert first_id != second_id
    expect(page.locator("[data-composer] img[alt='Bağlantı kapağı']")).to_have_count(1)
    expect(page.locator("[data-attachments] img")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
    dest.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(dest / f"publication-composer-{'manager' if management else 'profile'}-{width}.png"), animations="disabled")
    page.get_by_role("button", name="Kapağı kaldır", exact=True).click()
    expect(page.locator("[data-preview] img")).to_have_count(0)
    expect(page.locator("[data-preview] .ds-link-card strong")).to_have_text(TITLE)


def test_publish_shows_destination_status_and_preserves_draft_on_failure(publication_page):
    page, _, _, _, _, _ = publication_page
    area = page.locator("[data-post-text]")
    area.fill("Bu bilimsel çalışma üzerine açıklamam.")
    cover_id = attach_cover(page)
    held = []
    page.route("**/api/expert-social/posts", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
    page.locator("[data-publish]").evaluate("button => { button.click(); button.click(); }")
    expect(page.locator("[data-publish]")).to_be_disabled()
    expect(page.locator("[data-publish]")).to_have_text("Paylaşılıyor…")
    assert len(held) == 1
    held.pop().fulfill(status=503, json={"detail": "Bağlantı geçici olarak kesildi. Yeniden deneyin."})
    expect(page.locator("[data-compose-error]")).to_contain_text("Yeniden deneyin")
    expect(page.locator("[data-compose-error]")).to_be_in_viewport()
    expect(area).to_have_value("Bu bilimsel çalışma üzerine açıklamam.")
    expect(page.locator("[data-preview] img")).to_have_count(1)
    expect(page.locator("[data-publish]")).to_be_enabled()
    page.unroute("**/api/expert-social/posts")
    with page.expect_response(lambda response: response.url.endswith("/api/expert-social/posts") and response.request.method == "POST") as created:
        page.locator("[data-publish]").click()
    row = created.value.json()
    assert created.value.status == 200 and row["status"] == "PENDING"
    post = page.locator(f'[data-post-id="{row["id"]}"]')
    expect(post.locator(".ds-status")).to_have_text("İncelemede")
    visible_status(page, "İncelemeye alındı")
    page.get_by_role("button", name="Gönderiye git", exact=True).click()
    expect(post.locator(".ds-author")).to_be_in_viewport()
    with Session(main.engine) as session:
        rows = session.exec(select(SocialPost)).all()
        assert len(rows) == 1
        assert rows[0].text == "Bu bilimsel çalışma üzerine açıklamam."
        assert rows[0].link_url == URL and rows[0].cover_media_id == cover_id
        assert len(session.exec(select(SocialMedia).where(SocialMedia.post_id == row["id"])).all()) == 1
    page.reload()
    expect(post.locator(".ds-status")).to_have_text("İncelemede")


def test_link_only_publication_publishes_without_duplicating_title(publication_page):
    page, _, _, _, _, _ = publication_page
    expect(page.locator("[data-post-text]")).to_have_value("")
    with page.expect_response(lambda response: response.url.endswith("/api/expert-social/posts") and response.request.method == "POST") as created:
        page.locator("[data-publish]").click()
    row = created.value.json()
    assert created.value.status == 200 and row["status"] == "PUBLISHED"
    post = page.locator(f'[data-post-id="{row["id"]}"]')
    expect(post.locator(".ds-link-card strong")).to_have_text(TITLE)
    expect(post.locator(".ds-post-text")).to_have_count(0)
    visible_status(page, "Yayımlandı")
    expect(page.get_by_role("button", name="Gönderiye git", exact=True)).to_be_in_viewport()
    with Session(main.engine) as session:
        persisted = session.get(SocialPost, row["id"])
        assert persisted.text == "" and persisted.link_url == URL
        # Existing posts created by the old auto-fill should also read as one card.
        persisted.text = TITLE.strip() + "\n" + URL
        session.add(persisted)
        session.commit()
    page.reload()
    expect(post.locator(".ds-post-text")).to_have_count(0)
    with Session(main.engine) as session:
        persisted = session.get(SocialPost, row["id"])
        assert persisted.text == TITLE.strip() + "\n" + URL
        persisted.text = "Uzmanın kendi açıklaması.\n" + persisted.text
        session.add(persisted)
        session.commit()
    page.reload()
    expect(post.locator(".ds-post-text")).to_contain_text("Uzmanın kendi açıklaması.")


def test_removing_a_preparing_publication_restores_publish_and_ignores_late_result(publication_page):
    page, _, _, _, _, management = publication_page
    page.get_by_role("button", name="Bağlantı önizlemesini kaldır").click()
    if not management:
        page.locator("[data-composer] [data-close]").click()
        page.wait_for_function("!history.state?.dsDialog")
    held = []
    page.route("**/api/expert-social/publications/1/share-preview", lambda route: held.append(route))
    page.locator("[data-publications]").get_by_role("button", name="Gönderi olarak paylaş").click()
    submit = page.locator("[data-publish]")
    expect(submit).to_have_text("Hazırlanıyor…")
    expect(submit).to_be_disabled()
    assert len(held) == 1
    page.get_by_role("button", name="Bağlantı önizlemesini kaldır").click()
    expect(submit).to_have_text("Paylaş")
    expect(submit).to_be_enabled()
    page.locator("[data-post-text]").fill("Bağlantısız yeni paylaşımım.")
    with page.expect_response("**/api/expert-social/publications/1/share-preview"):
        held[0].fulfill(status=200, json={"id": 12345, "title": "Eski yayın kartı", "available": True})
    expect(page.locator("[data-preview] .ds-link-card")).to_have_count(0)
    expect(submit).to_have_text("Paylaş")
    with page.expect_response(lambda response: response.url.endswith("/api/expert-social/posts") and response.request.method == "POST") as created:
        submit.click()
    row = created.value.json()
    assert row["text"] == "Bağlantısız yeni paylaşımım." and not row["link_url"]
    visible_status(page, "Yayımlandı")
