"""Actual browser retries only an explicit pre-admission busy response."""
import io
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from test_browser import browser_app
from test_dental_flow_browser import start
from test_dental_flow import seed
from sqlmodel import Session
from app import main
from app.expert_social_models import SocialMedia


def test_busy_upload_waits_then_uses_the_real_server_without_losing_preview(browser_app):
    base,_=browser_app
    raw=io.BytesIO();Image.new('RGB',(24,24),'blue').save(raw,format='JPEG')
    with sync_playwright() as pw:
        browser,page=start(pw,base,390,user=1)
        calls=[]
        def busy_once(route):
            calls.append(route.request.method)
            if len(calls)==1:route.fulfill(status=503,headers={'Retry-After':'1'},json={'detail':'Sunucu yoğun'})
            else:route.continue_()
        try:
            page.goto(base+'/expert-support/expert/1')
            page.locator('[data-compose]').click()
            page.route('**/api/expert-social/media',busy_once)
            page.locator('[data-file]').set_input_files({'name':'synthetic.jpg','mimeType':'image/jpeg','buffer':raw.getvalue()})
            expect(page.locator('[data-attachments]')).to_contain_text('Sıra bekliyor')
            expect(page.locator('[data-attachments]')).to_contain_text('Hazır',timeout=10000)
            assert calls==['POST','POST']
            expect(page.locator('[data-attachments] img')).to_have_count(1)
            expect(page.locator('[data-compose-error]')).to_be_hidden()
        finally:browser.close()


def test_busy_feed_image_retries_without_losing_the_post(browser_app):
    base,_=browser_app
    with Session(main.engine) as session:
        post=seed(session,1)
        media=SocialMedia(owner_id=1,post_id=post.id,reference='private/synthetic.jpg')
        session.add(media);session.commit();ident=media.id
    raw=io.BytesIO();Image.new('RGB',(24,24),'blue').save(raw,format='JPEG')
    with sync_playwright() as pw:
        browser,page=start(pw,base,390,user=2);calls=[]
        def image(route):
            calls.append(route.request.url)
            if len(calls)==1:route.fulfill(status=503,headers={'Retry-After':'3'},body='busy')
            else:route.fulfill(status=200,content_type='image/jpeg',body=raw.getvalue())
        try:
            page.route('**/api/expert-social/media/'+str(ident)+'*',image)
            page.goto(base+'/dental-akis')
            img=page.locator('[data-feed] .ds-gallery-open img')
            expect(img).to_have_js_property('naturalWidth',24,timeout=10000)
            assert len(calls)==2 and calls[-1].endswith('retry=1')
            expect(page.locator('[data-feed] > article')).to_have_count(1)
        finally:browser.close()


def test_logout_stops_remaining_selected_uploads(browser_app):
    base,_=browser_app
    raw=io.BytesIO();Image.new('RGB',(24,24),'blue').save(raw,format='JPEG')
    with sync_playwright() as pw:
        browser,page=start(pw,base,390,user=1);calls=[]
        def busy(route):
            calls.append(route.request.method)
            route.fulfill(status=503,headers={'Retry-After':'1'},json={'detail':'Sunucu yoğun'})
        try:
            page.goto(base+'/expert-support/expert/1');page.locator('[data-compose]').click()
            page.route('**/api/expert-social/media',busy)
            page.locator('[data-file]').set_input_files([{'name':f'synthetic-{i}.jpg','mimeType':'image/jpeg','buffer':raw.getvalue()} for i in range(2)])
            expect(page.locator('[data-attachments]')).to_contain_text('Sıra bekliyor')
            page.evaluate("window.dispatchEvent(new Event('dai:session-ending'))")
            expect(page.locator('[data-attachments] img')).to_have_count(0)
            page.wait_for_timeout(2000)
            assert calls==['POST']
        finally:browser.close()
