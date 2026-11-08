"""Real Chromium flows on the existing app. External metadata uses deterministic fixtures."""

import io
import os
import socket
import threading
import time
from datetime import timedelta
from pathlib import Path
import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from sqlmodel import SQLModel, Session, create_engine
from app import main, expert_social_safety


@pytest.fixture
def browser_app(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "browser.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setenv("R2_ENABLED", "0")
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    with Session(engine) as s:
        for i in (1, 2):
            s.add(
                main.User(
                    id=i,
                    username="browser" + str(i),
                    role="DOCTOR",
                    display_name="Test Uzman" if i == 1 else "Test Üye",
                    email_verified_at=main._utcnow_naive(),
                )
            )
            s.add(
                main.SessionToken(
                    user_id=i,
                    token_hash=main.hash_session_token("browser" + str(i)),
                    expires_at=main._utcnow_naive() + timedelta(days=1),
                )
            )
        s.add(
            main.ExpertProfile(
                user_id=1,
                specialty="Ortodonti",
                institution="Test Kurumu",
                bio="Bilimsel araştırmalar ve güncel tedavi yaklaşımları.",
                application_status="APPROVED",
                verification_status="VERIFIED",
                specialty_verified=True,
                credential_document_path="private/document.pdf",
                phone="05300000000",
                availability="AVAILABLE",
                consultation_price=500,
            )
        )
        s.add(main.DoctorProfile(user_id=1, is_specialist=True, specialty="Ortodonti"))
        s.add(main.UserAccountMeta(user_id=1, professional_title="Uzman Diş Hekimi"))
        s.commit()

    async def preview(url):
        return {
            "url": url,
            "domain": "pubmed.ncbi.nlm.nih.gov",
            "site_name": "PubMed",
            "title": "Uzun makale başlığı: " + ("ortodonti araştırması " * 12),
            "description": "Bilimsel yayın özeti",
            "image_url": None,
        }

    monkeypatch.setattr(expert_social_safety, "preview", preview)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(
            main.app, host="127.0.0.1", port=port, lifespan="off", log_level="error"
        )
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}", tmp_path
    server.should_exit = True
    t.join(5)


@pytest.mark.parametrize("width", [360, 390, 430, 1280])
def test_mobile_profile_composer_publication_and_member_flow(browser_app, width):
    base, tmp = browser_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=[
                "--no-sandbox",
                "--no-zygote",
                "--single-process",
                "--in-process-gpu",
                "--use-gl=angle",
                "--use-angle=swiftshader",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": width, "height": 844},
            is_mobile=width < 600,
            has_touch=width < 600,
        )
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/expert-support/expert/1")
        expect(page.locator("[data-compose]")).to_be_visible()
        assert (
            page.locator("[data-tab=posts]").evaluate(
                "n=>getComputedStyle(n).backgroundColor"
            )
            == "rgba(0, 0, 0, 0)"
        )
        page.locator("[data-compose]").click()
        area = page.locator("[data-post-text]")
        area.fill("Taslak: Türkçe çığöşü 🦷\nİkinci paragraf")
        page.locator("[data-composer] [data-close]").click()
        page.reload()
        page.locator("[data-compose]").click()
        expect(area).to_have_value("Taslak: Türkçe çığöşü 🦷\nİkinci paragraf")
        area.fill(
            "Erken müdahale üzerine bir araştırma.\nhttps://pubmed.ncbi.nlm.nih.gov/123/"
        )
        expect(page.locator("[data-preview] .ds-link-card strong")).to_contain_text(
            "Uzun makale başlığı", timeout=10000
        )
        page.locator("[data-publish]").dblclick()
        expect(page.locator("[data-composer]")).not_to_be_visible()
        expect(page.locator("[data-feed] .ds-card")).to_have_count(1)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.get_by_role("tab", name="Akademik Yayınlar").click()
        page.locator("[data-add-publication]").click()
        form = page.locator("[data-publication-form]")
        form.locator("[name=title]").fill(
            "Test bilimsel makalesi " + ("uzun başlık " * 15)
        )
        form.locator("[name=doi]").fill("10.1000/mobile")
        form.locator("[name=year]").fill("2026")
        form.get_by_role("button", name="Kaydet").click()
        expect(page.locator("[data-publications] .ds-card")).to_have_count(1)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.locator("[data-publications]").get_by_role(
            "button", name="Gönderi olarak paylaş"
        ).click()
        expect(area).to_have_value(__import__("re").compile("Test bilimsel makalesi"))
        page.locator("[data-composer] [data-close]").click()
        page.get_by_role("tab", name="Gönderiler", exact=True).click()
        # Existing profile shell elements remain present.
        expect(page.locator("#notificationBell")).to_be_visible()
        expect(page.locator(".menu-toggle")).to_be_visible()
        assert not errors, errors
        # Normal member sees the published link and can comment/reply/like.
        ctx.clear_cookies()
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser2", "url": base}]
        )
        page.reload()
        expect(page.locator("[data-compose]")).to_have_count(0)
        expect(
            page.get_by_role("link", name="Uzmandan Destek Al", exact=True)
        ).to_have_attribute(
            "href", __import__("re").compile("/expert-support/request/1")
        )
        page.locator("[data-comments-toggle]").click()
        page.locator(".ds-comment-form textarea").fill("Kaynak için teşekkürler.")
        page.locator(".ds-comment-form").get_by_role(
            "button", name="Gönder", exact=True
        ).click()
        expect(page.locator(".ds-comment")).to_have_count(1)
        page.locator(".ds-comment-tools").get_by_role("button", name="Yanıtla").click()
        page.locator(".ds-comment-form textarea").fill("Bilimsel tartışmaya katkı.")
        page.locator(".ds-comment-form").get_by_role(
            "button", name="Gönder", exact=True
        ).click()
        expect(page.locator(".ds-comment")).to_have_count(2)
        page.locator(".ds-comment").first.get_by_role(
            "button", name="Düzenle", exact=True
        ).click()
        page.locator(".ds-comment-form textarea").fill("Düzenlenmiş bilimsel yorum.")
        page.locator(".ds-comment-form").get_by_role(
            "button", name="Gönder", exact=True
        ).click()
        expect(page.locator(".ds-comment").first).to_contain_text(
            "Düzenlenmiş bilimsel yorum."
        )
        expect(page.locator("[data-comments-toggle]")).to_contain_text("2 yorum")
        page.get_by_role('button',name='Yorumları kapat',exact=True).click()
        page.get_by_role("button", name="Beğen", exact=True).click()
        expect(page.get_by_role("button", name="Beğen", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        # Screenshots are test artifacts, never seeded into production UI.
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(exist_ok=True)
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(dest / f"profile-member-{width}.png"), full_page=True)
        assert not errors, errors
        browser.close()


def test_four_images_upload_reorder_offline_retry_and_pending_visibility(browser_app):
    base, tmp = browser_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=[
                "--no-sandbox",
                "--no-zygote",
                "--single-process",
                "--in-process-gpu",
                "--use-gl=angle",
                "--use-angle=swiftshader",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = ctx.new_page()
        page.goto(base + "/expert-support/expert/1")
        page.locator("[data-compose]").click()
        page.locator("[data-post-text]").fill("Eğitim amaçlı dört görsel")
        files = []
        for color in ("red", "green", "blue", "yellow"):
            image = Image.new("RGB", (900, 500), color)
            raw = io.BytesIO()
            image.save(raw, "JPEG")
            files.append(
                {
                    "name": color + ".jpg",
                    "mimeType": "image/jpeg",
                    "buffer": raw.getvalue(),
                }
            )
        page.locator("[data-file]").set_input_files(files)
        expect(page.locator(".ds-attachment small", has_text="Hazır")).to_have_count(
            4, timeout=20000
        )
        sources = page.locator(".ds-attachment img").evaluate_all(
            'nodes=>nodes.map(n=>n.getAttribute("src"))'
        )
        page.locator(".ds-attachment").nth(1).get_by_role(
            "button", name="Fotoğrafı önceye taşı"
        ).click()
        assert (
            page.locator(".ds-attachment img").first.get_attribute("src") == sources[1]
        )
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(exist_ok=True)
        page.screenshot(path=str(dest / "composer-four-images.png"))
        ctx.set_offline(True)
        page.locator("[data-publish]").click()
        expect(page.locator("[data-compose-error]")).to_be_visible()
        expect(page.locator("[data-post-text]")).to_have_value(
            "Eğitim amaçlı dört görsel"
        )
        ctx.set_offline(False)
        page.locator("[data-publish]").click()
        expect(page.locator("[data-composer]")).not_to_be_visible()
        expect(page.locator("[data-feed] .ds-card")).to_have_count(1)
        expect(page.locator("[data-feed] .ds-status")).to_have_text("İncelemede")
        expect(page.locator(".ds-gallery img")).to_have_count(4)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        ctx.clear_cookies()
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser2", "url": base}]
        )
        page.reload()
        expect(page.locator("[data-feed] .ds-card")).to_have_count(0)
        browser.close()


def test_management_inline_editor_tabs_and_settings(browser_app):
    base, tmp = browser_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox", "--single-process", "--no-zygote"],
        )
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            permissions=["notifications"],
        )
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/expert-support/profile")
        expect(page.locator(".ds-inline-composer")).to_be_visible()
        expect(page.locator("[data-publications] .ds-empty")).to_be_visible()
        empty_dest=Path(os.getenv("TEST_ARTIFACT_DIR",str(tmp/"screenshots")))
        empty_dest.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(empty_dest/"expert-management-empty-390.png"),full_page=True)
        page.locator("[data-post-text]").fill("Yönetim ekranından bilimsel paylaşım")
        page.locator("[data-publish]").click()
        expect(page.locator("[data-feed] .ds-card")).to_have_count(1)
        expect(page.locator("[data-post-text]")).to_have_value("")
        page.locator("[data-post-text]").fill("Korunacak yeni gönderi taslağı")
        page.locator('[data-post-id="1"] .ds-menu summary').click()
        page.locator('[data-post-id="1"]').get_by_role(
            "button", name="Gönderiyi düzenle", exact=True
        ).click()
        expect(page.locator("[data-edit-cancel]")).to_be_visible()
        page.locator("[data-edit-cancel]").click()
        expect(page.locator("[data-post-text]")).to_have_value(
            "Korunacak yeni gönderi taslağı"
        )
        expect(page.locator("[data-publish]")).to_have_text("Paylaş")
        page.locator("[data-post-text]").fill("Yeni ikinci gönderi")
        page.locator("[data-publish]").click()
        expect(page.locator("[data-feed] .ds-card")).to_have_count(2)

        page.locator("[data-manage-tab=general]").click()
        expect(page.locator("[data-manage-pane=general]")).to_be_visible()
        expect(page.locator(".expert-publication-editor")).to_have_count(0)
        expect(
            page.locator("input[type=hidden][name=publications_text]")
        ).to_have_count(1)
        expect(page.locator(".ds-inline-composer")).not_to_be_visible()
        page.locator("[data-manage-tab=settings]").click()
        expect(page.locator(".expert-availability-switch")).to_be_visible()
        page.locator(".expert-availability-switch").click()
        expect(page.locator("#availabilityText")).to_have_text("Meşgul")
        page.locator("[data-manage-tab=publications]").click()
        expect(page.locator("[data-orcid]")).to_be_visible()
        expect(page.locator(".ds-inline-composer")).not_to_be_visible()
        page.locator("[data-manage-tab=posts]").click()
        expect(page.locator(".ds-inline-composer")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(exist_ok=True, parents=True)
        expect(page.locator("[data-manage-tab=posts]")).to_have_css(
            "background-color", "rgb(9, 39, 71)"
        )
        page.screenshot(path=str(dest / "expert-management-390.png"), full_page=True)
        assert not errors, errors
        browser.close()
