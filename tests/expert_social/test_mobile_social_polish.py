"""Real mobile profile density, comment visibility and native image carousels."""

import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session

from app import main
from app.expert_social_models import SocialComment, SocialFollow, SocialMedia, SocialPost
from test_browser import browser_app


@pytest.fixture(params=[360, 390, 430, 1280])
def social_page(browser_app, request):
    base, tmp = browser_app
    with Session(main.engine) as session:
        session.add(SocialPost(id=1, author_id=1, text="Dört sentetik eğitim görseli.\nBilimsel kaynaklar üzerine bir paylaşım.", status="PUBLISHED", pinned=True, idempotency_key="mobile-polish-live", request_hash="synthetic"))
        session.add(SocialPost(id=2, author_id=1, text="İncelemede olan bilimsel paylaşım.", status="PENDING", reasons_json='["IMAGE_REVIEW"]', idempotency_key="mobile-polish-pending", request_hash="synthetic"))
        session.add(SocialComment(id=1, post_id=1, author_id=2, text="Mevcut bilimsel yorum korunuyor.", status="PUBLISHED", idempotency_key="mobile-polish-comment"))
        session.add(SocialFollow(follower_id=2, expert_id=1))
        for i, color in enumerate(("#8bb8be", "#c0c8d8", "#a9bd9b", "#d6bb92"), 1):
            path = tmp / "uploads" / f"synthetic-polish-{i}.jpg"
            path.parent.mkdir(exist_ok=True)
            image = Image.new("RGB", (900, 600) if i % 2 else (600, 900), color)
            ImageDraw.Draw(image).text((30, 30), f"SENTETIK {i} / 4", fill="black", font_size=36)
            image.save(path)
            session.add(SocialMedia(id=i, owner_id=1, post_id=1, reference=str(path), position=i-1))
        session.commit()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"), args=["--no-sandbox", "--single-process", "--no-zygote"])
        context = browser.new_context(viewport={"width": request.param, "height": 844}, is_mobile=request.param < 600, has_touch=request.param < 600)
        context.add_cookies([{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/expert-support/expert/1")
        expect(page.locator('[data-post-id="1"]')).to_be_visible()
        yield page, context, tmp, request.param
        assert not errors, errors
        browser.close()


def screenshot(page, tmp, width, name, full_page=True):
    dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
    dest.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(dest / f"mobile-polish-{name}-{width}.png"), full_page=full_page, animations="disabled")


def test_profile_counts_and_feed_are_compact(social_page):
    page, _, tmp, width = social_page
    expect(page.locator('[data-stat="followers"]')).to_have_text("1")
    expect(page.locator('[data-stat="posts"]')).to_have_text("1")
    stats = page.locator(".ds-stat-open").first
    assert stats.evaluate("n => getComputedStyle(n).backgroundColor") == "rgba(0, 0, 0, 0)"
    assert stats.evaluate("n => getComputedStyle(n).boxShadow") == "none"
    assert 44 <= stats.bounding_box()["height"] <= 52
    expect(stats.locator("b")).to_have_css("color", "rgb(20, 32, 51)")
    launch = page.locator("[data-compose]")
    assert 52 <= launch.bounding_box()["height"] <= 68
    expect(launch.locator("small")).to_have_count(0)
    assert launch.inner_text().count("Bir şey paylaş…") == 1
    tabs, compose, first = (page.locator(selector).bounding_box() for selector in (".ds-tabs", "[data-compose]", '[data-feed] article:first-child'))
    assert 0 <= compose["y"] - tabs["y"] - tabs["height"] <= 12
    assert 0 <= first["y"] - compose["y"] - compose["height"] <= 12
    published = page.locator('[data-post-id="1"]')
    expect(published.locator(".ds-status.is-published")).to_have_text("Yayında")
    expect(published.get_by_label("Sabitlenmiş gönderi")).to_be_visible()
    pending = page.locator('[data-post-id="2"]')
    reason = pending.locator(".ds-moderation-reason")
    expect(reason).to_contain_text("incele")
    assert float(reason.evaluate("n => parseFloat(getComputedStyle(n).marginBottom)")) <= 8
    pending_text, reason_box = pending.locator(".ds-post-text").bounding_box(), reason.bounding_box()
    assert 0 <= pending_text["y"] - reason_box["y"] - reason_box["height"] <= 12
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.evaluate("scrollTo(0, 0)")
    screenshot(page, tmp, width, "profile")


def test_closing_comments_hides_action_and_sheet_but_reopening_keeps_draft(social_page):
    page, _, tmp, width = social_page
    post = page.locator('[data-post-id="1"]')
    post.locator("[data-comments-toggle]").click()
    sheet = page.get_by_role("dialog", name="Yorumlar", exact=True)
    expect(sheet.locator(".ds-comment")).to_have_count(1)
    sheet.get_by_role("textbox", name="Yorum metni").fill("Kapanınca korunacak yorum taslağı")
    # Exercise the owner action while a comment sheet is already open.
    post.get_by_role("button", name="Yorumları kapat", exact=True, include_hidden=True).dispatch_event("click")
    expect(sheet).not_to_be_visible()
    expect(post.locator("[data-comments-toggle]")).to_have_count(0)
    expect(post.locator("[data-comments-state]")).to_have_text("Yorumlar kapalı")
    assert page.evaluate("document.body.style.overflow") != "hidden"
    screenshot(page, tmp, width, "comments-closed")
    post.locator(".ds-menu summary").click()
    post.get_by_role("button", name="Yorumları aç", exact=True).click()
    expect(post.locator("[data-comments-toggle]")).to_have_count(1)
    post.locator("[data-comments-toggle]").click()
    expect(sheet.get_by_role("textbox", name="Yorum metni")).to_have_value("Kapanınca korunacak yorum taslağı")
    expect(sheet.locator(".ds-comment")).to_contain_text("Mevcut bilimsel yorum korunuyor.")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, tmp, width, "comments-open")


def test_post_images_scroll_sideways_and_keep_the_same_page_viewer(social_page):
    page, context, tmp, width = social_page
    post = page.locator('[data-post-id="1"]')
    gallery = post.locator(".ds-gallery")
    assert gallery.evaluate("n => n.scrollWidth > n.clientWidth")
    if width < 600:
        assert gallery.evaluate("n => n.clientHeight") <= 280
    expect(gallery).to_have_css("scroll-snap-type", "x mandatory")
    expect(gallery.locator("img").first).to_have_css("object-fit", "contain")
    position = post.locator(".ds-carousel-position")
    expect(position).to_have_text("1 / 4")
    post.scroll_into_view_if_needed()
    gallery.evaluate("n => n.scrollTo({left: n.clientWidth + 8, behavior: 'instant'})")
    expect(position).to_have_text("2 / 4")
    assert gallery.evaluate("n => n.scrollLeft > 0")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # Mobile full-page capture resizes the viewport and changes native snap positions.
    screenshot(page, tmp, width, "gallery", full_page=False)
    expect(position).to_have_text("2 / 4")
    url = page.url
    gallery.get_by_role("button", name="Gönderi görselini aç: 2 / 4", exact=True).click()
    viewer = page.get_by_role("dialog", name="Gönderi görselleri")
    expect(viewer.locator("[data-media-position]")).to_have_text("2 / 4")
    expect(viewer.locator("img")).to_be_visible()
    assert page.url == url and len(context.pages) == 1


def test_upload_previews_scroll_sideways_and_keep_reorder_controls(social_page):
    page, _, tmp, width = social_page
    page.locator("[data-compose]").click()
    files = []
    for color in ("red", "green", "blue", "yellow"):
        raw = io.BytesIO()
        Image.new("RGB", (900, 600), color).save(raw, "JPEG")
        files.append({"name": color + ".jpg", "mimeType": "image/jpeg", "buffer": raw.getvalue()})
    page.locator("[data-file]").set_input_files(files)
    expect(page.locator(".ds-attachment small", has_text="Hazır")).to_have_count(4, timeout=20000)
    track = page.locator(".ds-attachments-track")
    expect(track).to_have_count(1)
    assert track.evaluate("n => n.scrollWidth > n.clientWidth")
    track.evaluate("n => n.scrollTo({left: n.clientWidth + 8, behavior: 'instant'})")
    position = page.locator("[data-attachments] .ds-carousel-position")
    expect(position).to_have_text("2 / 4")
    second = page.locator(".ds-attachment").nth(1)
    source = second.locator("img").get_attribute("src")
    second.get_by_role("button", name="Fotoğrafı önceye taşı").click()
    expect(page.locator(".ds-attachment img").first).to_have_attribute("src", source)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, tmp, width, "composer")


def test_single_portrait_keeps_a_readable_full_image(social_page):
    page, _, _, _ = social_page
    with Session(main.engine) as session:
        for ident in (1, 3, 4):
            session.delete(session.get(SocialMedia, ident))
        session.commit()
    page.reload()
    image = page.locator('[data-post-id="1"] .ds-gallery img')
    expect(image).to_have_count(1)
    expect(image).to_have_css("object-fit", "contain")
    assert image.bounding_box()["height"] >= 320
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
