import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session, select

from app import main, voice_exam_core, voice_exam_final
from app.work_jobs import WorkJob
from test_browser import browser_app


@pytest.fixture
def voice_feedback_app(browser_app, monkeypatch):
    base, tmp = browser_app
    monkeypatch.setenv('VOICE_EXAM_ENABLED', '1')
    with Session(main.engine) as session:
        session.add(main.Patient(id=1, owner_user_id=1, anonymous_id='SYNTHETIC-MOBILE'))
        session.commit()
    fields = {'chief_complaint': {'value': 'Soğuk suyla kısa süreli ağrı',
                                  'quote': 'Soğuk suyla kısa süreli ağrı'}}
    monkeypatch.setattr(voice_exam_core, 'extract', lambda **kwargs: {
        'fields': fields, 'teeth': [], 'insights': [], 'uncertain': [],
        'follow_up_questions': [], 'source_requests': [], 'literature_topics': [],
        'appointment': {'quote': 'Yarın 11.00 gelebilir misiniz?',
                        'acceptance_quote': 'Evet gelebilirim.',
                        'start_at': '2026-12-14T11:00', 'agreed': True},
    })
    reviews = []

    def finalize(*args, **kwargs):
        reviews.append(kwargs.get('conversation_text'))
        return {'summary': [], 'questions': [], 'contradictions': [],
                'clinical_items': [], 'references': [], 'unavailable': [],
                'notice': 'Sentetik test', 'review_status': {}}

    monkeypatch.setattr(voice_exam_final, 'finalize', finalize)
    return base, tmp, reviews


def start_review(page, base):
    page.goto(base + '/voice-exams/1/session')
    page.locator('[data-voice-consent]').check()
    page.get_by_text('Alternatif: ses dosyası, bölüm kaydı veya metin', exact=True).click()
    page.locator('[data-voice-transcript]').fill(
        'Sentetik yazılım testi. Soğuk suyla kısa süreli ağrı. '
        'Hekim: Yarın 11.00 gelebilir misiniz? Hasta: Evet gelebilirim.')
    page.locator('[data-voice-text]').click()
    expect(page.locator('[data-voice-save]')).to_be_enabled(timeout=10000)


@pytest.mark.parametrize('width', [360, 430])
def test_calendar_edit_keeps_clinical_review_and_save_reports_result(voice_feedback_app, width):
    base, tmp, reviews = voice_feedback_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM', '/tmp/chromium'),
                                     args=['--no-sandbox', '--single-process', '--no-zygote'])
        context = browser.new_context(viewport={'width': width, 'height': 844},
                                      is_mobile=True, has_touch=True)
        context.add_cookies([{'name': main.SESSION_COOKIE, 'value': 'browser1', 'url': base}])
        page = context.new_page()
        start_review(page, base)
        page.locator('[data-voice-record-fields] > summary').click()
        # Calendar corrections do not change clinical facts or require a second paid review.
        page.locator('[data-voice-appointment-start]').fill('2026-12-15T11:30')
        expect(page.locator('[data-voice-save]')).to_be_enabled()
        expect(page.locator('[data-voice-finalize]')).to_be_hidden()
        assert len(reviews) == 1
        page.locator('[data-field-row=chief_complaint] input').check()
        requests = []

        def fail_once(route):
            requests.append(route.request.post_data_json)
            if len(requests) == 1:
                route.fulfill(status=409, content_type='application/json',
                              body=json.dumps({'ok': False, 'error': 'Bu randevu saati dolu. Başka bir saat seçin.'}))
            else:
                route.continue_()

        page.route('**/voice-exam/apply', fail_once)
        page.locator('[data-voice-save]').click()
        feedback = page.locator('[data-voice-save-status]')
        expect(feedback).to_be_visible()
        expect(feedback).to_contain_text('Bu randevu saati dolu')
        expect(page.locator('#voice-exam')).to_have_attribute('data-save-state', 'error')
        expect(page.locator('[data-voice-save]')).to_be_enabled()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        dest = Path(os.getenv('TEST_ARTIFACT_DIR', str(tmp / 'screenshots')))
        dest.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest / f'voice-save-feedback-{width}.png'), full_page=True)
        page.locator('[data-voice-appointment-start]').fill('2026-12-15T12:00')
        page.locator('[data-voice-save]').click()
        page.wait_for_url('**/patients/1?voice_saved=1')
        expect(page.get_by_role('status')).to_contain_text('kaydedildi')
        expect(page.locator('.patient-history-title')).to_have_text('Sesli muayene #1')
        expect(page.locator('.patient-history-row')).to_contain_text('Kaydedildi')
        assert 'Yarım kaldı' not in page.locator('.patient-history-row').inner_text()
        page.screenshot(path=str(dest / f'voice-saved-{width}.png'), full_page=True)
        assert requests[-1]['appointment']['start_at'] == '2026-12-15T12:00'
        assert len(reviews) == 1
        with Session(main.engine) as session:
            assert session.get(main.Patient, 1).chief_complaint == 'Soğuk suyla kısa süreli ağrı'
            assert len(session.exec(select(WorkJob).where(WorkJob.kind == 'VOICE_REVIEW')).all()) == 1
            assert len(session.exec(select(main.ScheduleEvent)).all()) == 1
        browser.close()


def test_empty_selection_is_explained_before_request(voice_feedback_app):
    base, tmp, reviews = voice_feedback_app
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM', '/tmp/chromium'),
                                     args=['--no-sandbox', '--single-process', '--no-zygote'])
        context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
        context.add_cookies([{'name': main.SESSION_COOKIE, 'value': 'browser1', 'url': base}])
        page = context.new_page()
        start_review(page, base)
        page.locator('[data-voice-record-fields] > summary').click()
        page.locator('[data-voice-save-appointment]').uncheck()
        applies = []
        page.on('request', lambda request: applies.append(request.url)
                if request.url.endswith('/voice-exam/apply') else None)
        page.locator('[data-voice-save]').click()
        expect(page.locator('[data-voice-save-status]')).to_contain_text('en az bir')
        expect(page.locator('[data-voice-record-fields]')).to_have_attribute('open', '')
        assert applies == []
        browser.close()


def test_approximate_spoken_time_is_prefilled_but_requires_booking_opt_in(voice_feedback_app, monkeypatch):
    base, tmp, reviews = voice_feedback_app
    extract = voice_exam_core.extract

    def approximate(**kwargs):
        data = extract(**kwargs)
        data['appointment'] = {**data['appointment'], 'agreed': False,
                               'resolution_status': 'time_confirmation_required'}
        return data

    monkeypatch.setattr(voice_exam_core, 'extract', approximate)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM', '/tmp/chromium'),
                                     args=['--no-sandbox', '--single-process', '--no-zygote'])
        context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
        context.add_cookies([{'name': main.SESSION_COOKIE, 'value': 'browser1', 'url': base}])
        page = context.new_page()
        start_review(page, base)
        page.locator('[data-voice-record-fields] > summary').click()
        expect(page.locator('[data-voice-appointment-start]')).to_have_value('2026-12-14T11:00')
        expect(page.locator('[data-voice-save-appointment]')).not_to_be_checked()
        expect(page.locator('[data-voice-appointment-quote]')).to_contain_text('yaklaşık saat dolduruldu')
        browser.close()
