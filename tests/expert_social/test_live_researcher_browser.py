"""Opt-in real public ORCID import through the actual manager UI; local account only."""

import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect
from sqlmodel import Session, select
from app import main
from app.expert_social_models import Publication
from test_browser import browser_app


@pytest.mark.skipif(
    os.getenv("TEST_LIVE_ORCID") != "1",
    reason="Set TEST_LIVE_ORCID=1 for live researcher UI integration",
)
def test_aziz_sancar_orcid_manager_import_and_duplicate(browser_app):
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
        page.goto(base + "/expert-support/profile")
        page.locator("[data-manage-tab=publications]").click()
        page.locator("[data-orcid]").fill("https://orcid.org/0000-0001-6469-4900")
        page.locator("[data-sync]").click()
        expect(page.locator("[data-sync-state]")).to_contain_text(
            "Son aktarım", timeout=25000
        )
        with Session(main.engine) as s:
            rows = s.exec(select(Publication).where(Publication.expert_id == 1)).all()
            assert len(rows) > 0 and all(
                p.source == "ORCID" and p.source_orcid == "0000-0001-6469-4900"
                for p in rows
            )
            total = len(rows)
            paper = next(p for p in rows if p.doi)
        print(f"Live researcher ORCID imported {total} works")
        expect(page.locator("[data-publications] .ds-card")).to_have_count(
            min(30, total)
        )
        page.locator("[data-sync]").click()
        expect(page.locator("[data-sync]")).to_be_enabled(timeout=25000)
        with Session(main.engine) as s:
            assert (
                len(s.exec(select(Publication).where(Publication.expert_id == 1)).all())
                == total
            )
        page.locator("[data-add-publication]").click()
        form = page.locator("[data-publication-form]")
        form.locator("[name=title]").fill(paper.title)
        form.locator("[name=doi]").fill(paper.doi)
        form.get_by_role("button", name="Kaydet").click()
        expect(page.locator("[data-publication-error]")).to_contain_text(
            "zaten kayıtlı"
        )
        page.locator("[data-publication-dialog] [data-close]").click()
        page.locator("[data-publications] .ds-card").first.get_by_role(
            "button", name="Gönderi olarak paylaş"
        ).click()
        expect(page.locator("[data-manage-tab=posts]")).to_have_attribute(
            "aria-selected", "true"
        )
        expect(page.locator("[data-preview]")).to_contain_text(
            page.locator("[data-post-text]").input_value().split("\n")[0], timeout=10000
        )
        page.locator("[data-post-text]").fill(
            "Bilimsel çalışma hakkında değerlendirmem.\n"
            + page.locator("[data-post-text]").input_value()
        )
        page.locator("[data-publish]").click()
        expect(page.locator("[data-feed] article")).to_have_count(1)
        page.locator("[data-manage-tab=publications]").click()
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(exist_ok=True, parents=True)
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(dest / "aziz-sancar-orcid-import.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()
