"""Dental Akış uses the real pages, API, follow relations and comment composer."""
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session, select
from app import main
from app.expert_social_models import SocialFollow
from test_browser import browser_app
from test_dental_flow import seed


def start(pw, base, width, user=2):
    browser = pw.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM','/usr/bin/chromium'), args=['--no-sandbox','--single-process','--no-zygote'])
    context = browser.new_context(viewport={'width':width,'height':844}, is_mobile=width<600, has_touch=width<600)
    context.add_cookies([{'name':main.SESSION_COOKIE,'value':f'browser{user}','url':base}])
    page = context.new_page()
    page.set_default_timeout(7000)
    return browser, page


@pytest.mark.parametrize('width', [360,390,430,1280])
def test_discovery_follow_filter_comment_profile_and_support(browser_app, width):
    base, tmp = browser_app
    with Session(main.engine) as session:
        seed(session, 1, text='Kaynaklı bilimsel paylaşım.')
        seed(session, 1, text='İkinci mesleki paylaşım.')
        seed(session, 1, status='PENDING', text='GİZLİ İNCELEME METNİ')
        session.commit()
    with sync_playwright() as pw:
        browser, page = start(pw, base, width)
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        requests = []
        page.on('request', lambda req: requests.append(req.url) if '/api/expert-social/' in req.url else None)
        try:
            page.goto(base+'/dental-akis')
            expect(page.get_by_role('heading',name='Dental Akış',exact=True)).to_be_visible()
            expect(page.locator('[data-feed] > article')).to_have_count(2)
            expect(page.locator('.dental-flow-filters a[aria-current=true]')).to_have_css('color','rgb(255, 255, 255)')
            expect(page.get_by_text('GİZLİ İNCELEME METNİ',exact=True)).to_have_count(0)
            expect(page.locator('[data-feed-loading]')).to_be_hidden()
            cards=page.locator('[data-feed] > article')
            avatar=cards.first.locator('.ds-author-avatar')
            expect(avatar).to_have_attribute('href','/expert-support/expert/1')
            avatar.click();page.wait_for_url('**/expert-support/expert/1')
            page.go_back();expect(cards).to_have_count(2)
            follow=cards.first.locator('[data-author-follow]')
            follow.click()
            expect(page.locator('[data-author-follow][aria-pressed=true]')).to_have_count(2)
            with Session(main.engine) as session:
                assert len(session.exec(select(SocialFollow)).all()) == 1
            card=cards.first
            expect(card.locator('.ds-author-avatar')).to_have_attribute('href','/expert-support/expert/1')
            expect(card.get_by_role('link',name='Uzman profili',exact=True)).to_have_attribute('href','/expert-support/expert/1')
            expect(card.get_by_role('link',name='Uzmandan Destek Al',exact=True)).to_have_attribute('href','/expert-support/request/1')
            card.get_by_role('button',name='Beğen',exact=True).click()
            expect(card.get_by_role('button',name='Beğenmekten vazgeç',exact=True)).to_have_attribute('aria-pressed','true')
            card.locator('[data-comments-toggle]').click()
            sheet=page.get_by_role('dialog',name='Yorumlar',exact=True)
            sheet.get_by_role('textbox',name='Yorum metni').fill('Bilimsel kaynak için teşekkürler.')
            sheet.get_by_role('button',name='Gönder',exact=True).click()
            expect(sheet.locator('.ds-comment')).to_contain_text('Bilimsel kaynak için teşekkürler.')
            sheet.get_by_role('button',name='Yorumları kapat',exact=True).click()
            page.get_by_role('navigation',name='Branşa göre filtrele').get_by_role('link',name='Endodonti',exact=True).click()
            expect(page.locator('[data-feed] .ds-empty')).to_contain_text('Bu branşta')
            page.get_by_role('navigation',name='Dental Akış bölümleri').get_by_role('link',name='Takip Ettiklerim',exact=True).click()
            assert parse_qs(urlsplit(page.url).query) == {'tab':['following'],'specialty':['Endodonti']}
            page.get_by_role('navigation',name='Branşa göre filtrele').get_by_role('link',name='Tümü',exact=True).click()
            expect(page.locator('[data-feed] > article')).to_have_count(2)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
            dest=Path(os.getenv('TEST_ARTIFACT_DIR',str(tmp/'screenshots')));dest.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(dest/f'dental-flow-{width}.png'),animations='disabled')
            page.locator('[data-feed] > article').first.locator('[data-author-follow]').click()
            expect(page.locator('[data-feed] > article')).to_have_count(0)
            expect(page.locator('[data-feed] .ds-empty')).to_be_visible()
            assert not any('/experts/0/' in url or '/publications' in url for url in requests)
            assert not errors,errors
        finally:
            browser.close()


def test_own_discovery_post_opens_existing_manager_instead_of_empty_composer(browser_app):
    base, _ = browser_app
    with Session(main.engine) as session:
        seed(session,1);session.commit()
    with sync_playwright() as pw:
        browser,page=start(pw,base,390,user=1)
        try:
            page.goto(base+'/dental-akis')
            card=page.locator('[data-post-id="1"]')
            card.locator('.ds-menu summary').click()
            card.get_by_role('button',name='Profilimde yönet',exact=True).click()
            page.wait_for_url('**/expert-support/profile?post=1')
            expect(page.locator('[data-composer]')).to_be_visible()
        finally:
            browser.close()


def test_failed_discovery_load_shows_working_retry_without_a_false_empty_state(browser_app):
    base, _ = browser_app
    with Session(main.engine) as session:
        seed(session,1);session.commit()
    with sync_playwright() as pw:
        browser,page=start(pw,base,360)
        try:
            page.route('**/api/expert-social/feed/discover',lambda route:route.fulfill(status=503,json={'detail':'Sentetik bağlantı kesildi.'}))
            page.goto(base+'/dental-akis')
            expect(page.locator('[data-notice]')).to_contain_text('Sentetik bağlantı kesildi.')
            expect(page.locator('[data-feed] .ds-empty')).to_have_count(0)
            page.unroute('**/api/expert-social/feed/discover')
            page.get_by_role('button',name='Gönderileri yeniden yükle',exact=True).click()
            expect(page.locator('[data-feed] > article')).to_have_count(1)
        finally:
            browser.close()


def test_late_discovery_page_keeps_follow_state_for_the_same_author(browser_app):
    base, _ = browser_app
    with Session(main.engine) as session:
        for _ in range(20): seed(session,1)
        session.commit()
    with sync_playwright() as pw:
        browser,page=start(pw,base,390)
        try:
            page.goto(base+'/dental-akis')
            expect(page.locator('[data-feed] > article')).to_have_count(15)
            held=[]
            def hold(route):
                held.append((route,route.fetch()))
                page.evaluate('window.discoveryPageHeld=true')
            page.route('**/api/expert-social/feed/discover?*',hold)
            page.get_by_role('button',name='Daha fazla gönderi',exact=True).click()
            page.wait_for_function('window.discoveryPageHeld === true')
            page.locator('[data-author-follow]').first.click()
            expect(page.locator('[data-author-follow][aria-pressed=true]')).to_have_count(15)
            route,response=held[0]
            route.fulfill(response=response)
            expect(page.locator('[data-feed] > article')).to_have_count(20)
            expect(page.locator('[data-author-follow][aria-pressed=true]')).to_have_count(20)
            assert len({int(value) for value in page.locator('[data-feed] > article').evaluate_all('rows => rows.map(row => row.dataset.postId)')}) == 20
        finally:
            browser.close()
