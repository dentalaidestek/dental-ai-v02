"""Real comment sheet: mobile back/close, drafts, delete and verified profile links."""
import os
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialComment, SocialPost
from test_browser import browser_app
from test_social_completion_browser import browser_context
from test_api import env, post


def test_comment_profile_identity_and_thread_deletion_counts(env):
    c,engine=env
    p=post(c).json()
    endpoint=f"/api/expert-social/posts/{p['id']}/comments"
    parent=c.post(endpoint,json={'text':'Bilimsel kaynak önerisi','idempotency_key':str(uuid.uuid4())}).json()
    assert parent['author_profile_url']=='/expert-support/expert/1'
    assert parent['author_verified'] is True
    c.cookies.set(main.SESSION_COOKIE,'t2')
    reply=c.post(endpoint,json={'text':'Kaynak için teşekkürler.','parent_id':parent['id'],'idempotency_key':str(uuid.uuid4())}).json()
    assert reply['author_profile_url'] is None and reply['author_verified'] is False
    assert c.delete(f"/api/expert-social/comments/{parent['id']}").status_code==403
    c.cookies.set(main.SESSION_COOKIE,'t1')
    deleted=c.delete(f"/api/expert-social/comments/{parent['id']}")
    assert deleted.status_code==200,deleted.text
    assert deleted.json()['comment_count']==0 and deleted.json()['removed_count']==2
    assert c.get(endpoint).json()['items']==[]
    with Session(engine) as s:
        for ident in (parent['id'],reply['id']):
            row=s.get(SocialComment,ident)
            assert row.status=='DELETED' and row.text==''


@pytest.mark.parametrize('width',[360,430,1280])
def test_comments_sheet_delete_draft_back_and_profile_navigation(browser_app,width):
    base,tmp=browser_app
    with Session(main.engine) as s:
        s.add(main.User(id=3,username='comment-expert',display_name='Diğer Uzman',role='DOCTOR',email_verified_at=main._utcnow_naive()))
        s.add(main.ExpertProfile(user_id=3,specialty='Periodontoloji',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='private/synthetic.pdf',phone='05300000000',availability='AVAILABLE'))
        s.add(SocialPost(id=1,author_id=1,text='Bilimsel tartışma',status='PUBLISHED',idempotency_key='comment-sheet',request_hash='synthetic'))
        s.flush()
        s.add(SocialComment(id=1,post_id=1,author_id=3,text='Kaynak üzerine görüşleriniz?',status='PUBLISHED',idempotency_key='comment-seed'))
        s.commit()
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base,user=2)
        page=ctx.new_page();page.set_viewport_size({'width':width,'height':844})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/expert-support/expert/1')
        toggle=page.locator('[data-comments-toggle]');toggle.click()
        sheet=page.get_by_role('dialog',name='Yorumlar',exact=True)
        expect(sheet).to_be_visible()
        area=sheet.get_by_role('textbox',name='Yorum metni')
        area.fill('Saklanan kısa yorum taslağım')
        sheet.get_by_role('button',name='Yorumları kapat',exact=True).click()
        expect(sheet).not_to_be_visible();toggle.click()
        expect(area).to_have_value('Saklanan kısa yorum taslağım')
        area.fill('Bilimsel katkı için teşekkür ederim.')
        sheet.get_by_role('button',name='Gönder',exact=True).dblclick()
        expect(sheet.locator('.ds-comment')).to_have_count(2)
        expect(toggle).to_contain_text('2 yorum')
        own=sheet.locator('.ds-comment').last
        own.get_by_label('Yorum seçenekleri',exact=True).click()
        page.once('dialog',lambda d:d.accept())
        own.get_by_role('button',name='Sil',exact=True).click()
        expect(sheet.locator('.ds-comment')).to_have_count(1)
        expect(toggle).to_contain_text('1 yorum')
        area.fill('Geri tuşunda korunacak taslak')
        page.go_back();expect(sheet).not_to_be_visible()
        toggle.click();expect(area).to_have_value('Geri tuşunda korunacak taslak')
        expect(sheet).to_have_css('opacity','1')
        expect(sheet).to_have_css('background-color','rgb(255, 255, 255)')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        dest=Path(os.getenv('TEST_ARTIFACT_DIR',str(tmp/'screenshots')));dest.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(dest/f'comments-sheet-{width}.png'),animations='disabled')
        profile=sheet.get_by_role('link',name='Uzm. Dt. Diğer Uzman',exact=True)
        expect(profile).to_have_attribute('href','/expert-support/expert/3')
        profile.click();page.wait_for_url('**/expert-support/expert/3')
        expect(page.locator('h1')).to_contain_text('Diğer Uzman')
        expect(page.locator('[data-comments-sheet][open]')).to_have_count(0)
        with Session(main.engine) as s:
            comments=s.exec(select(SocialComment).where(SocialComment.status=='PUBLISHED')).all()
            assert len(comments)==1
        assert not errors,errors
        browser.close()


def test_delayed_submission_does_not_erase_later_closed_draft(browser_app):
    base,_=browser_app
    with Session(main.engine) as s:
        s.add(SocialPost(id=1,author_id=1,text='Bilimsel tartışma',status='PUBLISHED',idempotency_key='late-comment',request_hash='synthetic'));s.commit()
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base,user=2)
        page=ctx.new_page();page.goto(base+'/expert-support/expert/1')
        held=[]
        def delay(route):
            if route.request.method=='POST':held.append((route,route.fetch()))
            else:route.continue_()
        page.route('**/api/expert-social/posts/1/comments',delay)
        page.locator('[data-comments-toggle]').click()
        sheet=page.get_by_role('dialog',name='Yorumlar',exact=True);area=sheet.get_by_role('textbox',name='Yorum metni')
        area.fill('Gönderilen bilimsel yorum')
        original_submit=sheet.get_by_role('button',name='Gönder',exact=True).element_handle()
        sheet.get_by_role('button',name='Gönder',exact=True).click()
        sheet.get_by_role('button',name='Yorumları kapat',exact=True).click()
        page.locator('[data-comments-toggle]').click();expect(area).to_have_value('Gönderilen bilimsel yorum')
        area.fill('En son yazılan ve korunması gereken taslak')
        sheet.get_by_role('button',name='Yorumları kapat',exact=True).click()
        assert len(held)==1
        route,response=held[0];route.fulfill(response=response)
        page.wait_for_function('(button) => !button.hasAttribute("aria-busy")',arg=original_submit)
        page.locator('[data-comments-toggle]').click();expect(area).to_have_value('En son yazılan ve korunması gereken taslak')
        expect(page.locator('[data-comments-sheet] .ds-comment')).to_have_count(1)
        expect(page.locator('[data-comments-toggle]')).to_contain_text('1 yorum')
        browser.close()
