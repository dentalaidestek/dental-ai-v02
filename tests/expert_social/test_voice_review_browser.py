import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from sqlmodel import Session, select
from app import main, voice_exam_core, voice_exam_final
from test_browser import browser_app


def test_voice_single_confirmation_and_compact_fields(browser_app, monkeypatch):
    base, tmp = browser_app
    monkeypatch.setenv("VOICE_EXAM_ENABLED", "1")
    with Session(main.engine) as s:
        s.add(main.Patient(id=1, owner_user_id=1, anonymous_id="VOICE-TEST"))
        s.commit()
    fields = {
        "first_name": {"value": "Ayşe", "quote": "Merhaba Ayşe Hanım."},
        "chief_complaint": {
            "value": "Sağ üst bölgede ağrı",
            "quote": "Sağ üst bölgede ağrı",
        },
        "medical_history": {
            "value": "Geçmiş: Anjiyo geçirmiş",
            "quote": "Daha önce anjiyo geçirdim.",
        },
    }
    monkeypatch.setattr(
        voice_exam_core,
        "extract",
        lambda **kwargs: {
            "fields": fields,
            "teeth": [],
            "insights": [],
            "uncertain": [],
            "follow_up_questions": [],
            "source_requests": [],
            "literature_topics": [],
        },
    )
    calls = []

    def finalize(*args, **kwargs):
        calls.append("finalize")
        return {
            "summary": [
                {"field": k, "text": v["value"], "quote": v["quote"]}
                for k, v in fields.items()
            ],
            "questions": [],
            "contradictions": [],
            "clinical_items": [],
            "references": [],
            "unavailable": [],
            "notice": "Test değerlendirmesi",
            "review_status": {},
        }

    monkeypatch.setattr(voice_exam_final, "finalize", finalize)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox", "--single-process", "--no-zygote"],
        )
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = ctx.new_page()
        page.goto(base + "/voice-exams/1/session")
        page.locator("[data-voice-consent]").check()
        page.get_by_text(
            "Alternatif: ses dosyası, bölüm kaydı veya metin", exact=True
        ).click()
        page.locator("[data-voice-transcript]").fill(
            "Merhaba Ayşe Hanım. Sağ üst bölgede ağrı. Daha önce anjiyo geçirdim."
        )
        page.locator("[data-voice-text]").click()
        expect(page.locator("[data-voice-save]")).to_be_enabled(timeout=10000)
        page.locator("[data-voice-record-fields]").evaluate("n=>n.open=true")
        page.locator("[data-field-row=first_name] input[type=checkbox]").check()
        page.locator("[data-field-row=chief_complaint] input[type=checkbox]").check()
        assert page.locator("[data-voice-confirm]").is_hidden()
        assert (
            page.locator("[data-field-row=first_name] textarea").bounding_box()[
                "height"
            ]
            < 90
        )
        assert (
            page.locator("[data-field-row=chief_complaint]").evaluate(
                "n=>getComputedStyle(n).borderLeftWidth"
            )
            == "0px"
        )
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp / "screenshots")))
        dest.mkdir(exist_ok=True, parents=True)
        page.screenshot(path=str(dest / "voice-compact-review.png"), full_page=True)
        page.locator("[data-voice-save]").click()
        page.wait_for_url("**/patients/1?voice_saved=1")
        assert len(calls) == 1
        with Session(main.engine) as s:
            patient = s.get(main.Patient, 1)
            assert (
                patient.first_name == "Ayşe"
                and patient.chief_complaint == "Sağ üst bölgede ağrı"
            )
            assert (
                len(
                    s.exec(
                        select(main.Analysis).where(main.Analysis.patient_id == 1)
                    ).all()
                )
                == 1
            )
        browser.close()


def test_history_import_and_unfinished_draft_keep_microphone_available(
    browser_app, monkeypatch
):
    import json

    base, tmp = browser_app
    monkeypatch.setenv("VOICE_EXAM_ENABLED", "1")
    with Session(main.engine) as s:
        s.add(main.Patient(id=1, owner_user_id=1, anonymous_id="HISTORY-TEST"))
        s.commit()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox", "--single-process", "--no-zygote"],
        )
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        ctx.add_cookies(
            [{"name": main.SESSION_COOKIE, "value": "browser1", "url": base}]
        )
        page = ctx.new_page()
        page.route(
            "**/voice-exam/history",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "ok": True,
                        "fields": {
                            "medications": {
                                "value": "Hasta beyanı: Test ilaç",
                                "quote": "Test ilaç kullanıyorum",
                                "analysis_id": 1,
                            }
                        },
                        "revision": "a" * 64,
                        "notice": "Önceki hekim onaylı kayıtlar",
                    }
                ),
            ),
        )
        page.goto(base + "/voice-exams/1/session")
        page.locator("[data-voice-consent]").check()
        page.locator(".voice-history>summary").click()
        page.locator("[data-voice-history]").click()
        page.locator("[data-voice-history-confirm]").check()
        page.locator("[data-voice-use-history]").click()
        expect(page.locator("[data-live-start]")).to_be_visible()
        expect(page.locator("[data-live-start]")).to_be_enabled()
        page.on("dialog", lambda dialog: dialog.accept())
        page.reload()
        page.locator("[data-voice-consent]").check()
        expect(page.locator("[data-live-start]")).to_be_visible()
        expect(page.locator("[data-live-start]")).to_be_enabled()
        browser.close()
