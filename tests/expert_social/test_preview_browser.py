"""Link preview failures must preserve only links the server did not reject."""

import os

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session

from app import expert_social_safety, main
from test_browser import browser_app


@pytest.fixture
def preview_page(browser_app):
    base, _ = browser_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox", "--single-process", "--no-zygote"],
        )
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = context.new_page()
        page.goto(base + "/expert-support/profile")
        expect(page.locator(".ds-inline-composer")).to_be_visible()
        page.locator("[data-post-text]").fill("Bilimsel kaynak paylaşımı")
        yield page, context, base
        browser.close()


def add_link(page, url):
    page.locator("[data-link]").click()
    page.locator("[data-link-input]").fill(url)
    with page.expect_response(
        lambda response: response.url.endswith("/api/expert-social/preview")
        and response.request.method == "POST"
    ) as pending:
        page.locator("[data-add-link]").click()
    return pending.value


@pytest.mark.parametrize("rejection", [400, 401, 403])
def test_rejected_link_is_removed_and_not_restored(preview_page, rejection):
    page, context, base = preview_page
    if rejection == 401:
        context.clear_cookies()
    elif rejection == 403:
        with Session(main.engine) as session:
            profile = session.get(main.ExpertProfile, 1)
            profile.availability = "PASSIVE"
            session.add(profile)
            session.commit()

    url = "https://127.0.0.1/" if rejection == 400 else "https://example.org/paper"
    response = add_link(page, url)
    assert response.status == rejection
    notice = page.locator("[data-notice]")
    expect(notice).to_be_visible()
    expect(page.locator("[data-preview] .ds-link-card")).to_have_count(0)
    expect(notice).not_to_contain_text("önizlemesiz paylaşabilirsiniz")

    if rejection == 401:
        context.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
    elif rejection == 403:
        with Session(main.engine) as session:
            profile = session.get(main.ExpertProfile, 1)
            profile.availability = "AVAILABLE"
            session.add(profile)
            session.commit()
    page.reload()
    expect(page.locator(".ds-inline-composer")).to_be_visible()
    expect(page.locator("[data-preview] .ds-link-card")).to_have_count(0)
    expect(page.locator("[data-post-text]")).to_have_value("Bilimsel kaynak paylaşımı")


def test_successful_preview_clears_previous_link_error(preview_page):
    page, _, _ = preview_page
    assert add_link(page, "https://127.0.0.1/").status == 400
    notice = page.locator("[data-notice]")
    expect(notice).to_be_visible()

    response = add_link(page, "https://pubmed.ncbi.nlm.nih.gov/123/")
    assert response.status == 200 and response.json()["available"] is True
    expect(page.locator("[data-preview] .ds-link-card strong")).to_contain_text(
        "Uzun makale başlığı"
    )
    expect(notice).not_to_be_visible()


def test_safe_link_remains_publishable_when_external_metadata_is_unavailable(
    preview_page, monkeypatch
):
    page, _, _ = preview_page

    async def unavailable(_):
        raise ValueError("External source unavailable")

    monkeypatch.setattr(expert_social_safety, "preview", unavailable)
    url = "https://example.org/paper"
    response = add_link(page, url)
    assert response.status == 200 and response.json()["available"] is False
    expect(page.locator("[data-preview] .ds-link-card")).to_have_attribute("href", url)
    page.locator("[data-publish]").click()
    expect(page.locator("[data-feed] .ds-link-card")).to_have_attribute("href", url)
    expect(page.locator("[data-compose-error]")).not_to_be_visible()


def test_temporary_offline_preview_preserves_link_and_draft(preview_page):
    page, context, _ = preview_page
    url = "https://example.org/paper"
    page.locator("[data-link]").click()
    page.locator("[data-link-input]").fill(url)
    context.set_offline(True)
    page.locator("[data-add-link]").click()
    expect(page.locator("[data-notice]")).to_contain_text("önizlemesiz paylaşabilirsiniz")
    expect(page.locator("[data-preview] .ds-link-card")).to_have_attribute("href", url)
    context.set_offline(False)
    page.reload()
    expect(page.locator("[data-preview] .ds-link-card")).to_have_attribute("href", url)
    expect(page.locator("[data-post-text]")).to_have_value("Bilimsel kaynak paylaşımı")
