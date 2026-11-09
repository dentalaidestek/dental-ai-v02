"""The real caption editor keeps existing content and survives a failed save."""
import json
import uuid
import pytest
from playwright.sync_api import expect, sync_playwright
from sqlmodel import Session
from app import main
from app.expert_social_models import SocialLike, SocialComment
from test_browser import browser_app
from test_dental_flow import seed
from test_dental_flow_browser import start


@pytest.mark.parametrize('width',[390,1280])
def test_home_card_and_existing_post_caption_edit_retry(browser_app,width):
    base, _ = browser_app
    with Session(main.engine) as session:
        row=seed(session,1,text='İlk bilimsel açıklama.')
        row.link_url='https://pubmed.ncbi.nlm.nih.gov/123/'
        row.preview_json=json.dumps({'title':'Bilimsel kaynak','site_name':'PubMed'})
        ident=row.id;session.add(row)
        session.add(SocialLike(post_id=ident,user_id=2))
        session.add(SocialComment(post_id=ident,author_id=2,text='Bilimsel katkı.',status='PUBLISHED',idempotency_key=str(uuid.uuid4())))
        session.commit()
    with sync_playwright() as pw:
        browser,page=start(pw,base,width,user=1)
        try:
            page.goto(base+'/')
            card=page.locator('main .visual-flow')
            expect(card).to_be_visible()
            expect(card.locator('img')).to_have_attribute('height','576')
            card.click()
            expect(page.get_by_role('heading',name='Dental Akış',exact=True)).to_be_visible()
            page.goto(base+'/expert-support/expert/1')
            page.locator('.ds-card .ds-menu summary').click()
            page.get_by_role('button',name='Gönderiyi düzenle',exact=True).click()
            composer=page.locator('[data-composer]')
            expect(composer.locator('[data-edit-preview]')).to_contain_text('Bilimsel kaynak')
            expect(composer.locator('[data-edit-help]')).to_contain_text('Beğeniler ve yorumlar korunur')
            area=composer.locator('[data-post-text]');area.fill('Güncellenmiş bilimsel açıklama.')
            pattern='**/api/expert-social/posts/'+str(ident)
            page.route(pattern,lambda route:route.fulfill(status=503,json={'detail':'Sentetik bağlantı kesildi.'}))
            composer.get_by_role('button',name='Kaydet',exact=True).click()
            expect(composer.locator('[data-compose-error]')).to_contain_text('Sentetik bağlantı kesildi.')
            expect(area).to_have_value('Güncellenmiş bilimsel açıklama.')
            page.unroute(pattern)
            composer.get_by_role('button',name='Kaydet',exact=True).click()
            expect(composer).not_to_be_visible()
            expect(page.locator('[data-feed] > article')).to_have_count(1)
            expect(page.locator(f'[data-post-id="{ident}"]')).to_contain_text('Güncellenmiş bilimsel açıklama.')
            expect(page.locator('[data-notice]')).to_contain_text('Beğeniler ve yorumlar korundu')
            expect(page.locator('[data-feed]').get_by_role('button',name='Beğen',exact=True)).to_contain_text('1')
            expect(page.locator('[data-comments-toggle]')).to_contain_text('1 yorum')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        finally:
            browser.close()
