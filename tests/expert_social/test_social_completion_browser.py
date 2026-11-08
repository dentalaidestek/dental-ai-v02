"""Incident regressions: published/pending states, media history and owner controls."""
import io
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from PIL import Image
from sqlmodel import Session, select
from app import main
from app.expert_social_models import SocialPost, SocialMedia
from test_browser import browser_app


def seed_posts(tmp):
    from app import object_storage
    for i in range(1,3):
        path=tmp/'uploads'/f'viewer-{i}.jpg';path.parent.mkdir(exist_ok=True)
        Image.new('RGB',(1000,700),('#8bb8be' if i==1 else '#c0c8d8')).save(path)
        with Session(main.engine) as s:
            if i==1:s.add(SocialPost(id=1,author_id=1,text='Klinikteyiz — güvenli test görseli',status='PUBLISHED',idempotency_key='viewer-seed',request_hash='synthetic'))
            s.commit()
            s.add(SocialMedia(id=i,owner_id=1,post_id=1,reference=str(path),position=i-1));s.commit()


def browser_context(pw,base,user=1):
    browser=pw.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM','/tmp/chromium'),args=['--no-sandbox','--single-process','--no-zygote'])
    ctx=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    ctx.add_cookies([{'name':main.SESSION_COOKIE,'value':f'browser{user}','url':base}])
    return browser,ctx


def test_image_viewer_stays_in_page_slides_zooms_and_restores_history(browser_app):
    base,tmp=browser_app;seed_posts(tmp)
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base)
        page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/expert-support')
        page.goto(base+'/expert-support/expert/1')
        photo=page.get_by_role('button',name='Gönderi görselini aç: 1 / 2')
        expect(photo).to_be_visible()
        photo.scroll_into_view_if_needed();before=page.evaluate('scrollY');url=page.url
        photo.click();viewer=page.get_by_role('dialog',name='Gönderi görselleri')
        expect(viewer).to_be_visible();expect(viewer.locator('img')).to_be_visible()
        expect(viewer.locator('[data-media-position]')).to_have_text('1 / 2')
        assert page.url==url and len(ctx.pages)==1
        viewer.get_by_role('button',name='Sonraki görsel',exact=True).click()
        expect(viewer.locator('[data-media-position]')).to_have_text('2 / 2')
        viewer.get_by_role('button',name='Yakınlaştır',exact=True).click()
        expect(viewer.locator('[data-media-zoom]')).to_have_text('150%')
        dest=Path(os.getenv('TEST_ARTIFACT_DIR',str(tmp/'screenshots')));dest.mkdir(exist_ok=True,parents=True)
        page.screenshot(path=str(dest/'same-page-image-viewer-390.png'))
        page.go_back();expect(viewer).not_to_be_visible()
        assert abs(page.evaluate('scrollY')-before)<3
        assert page.url==url and not errors,errors
        photo.click()
        viewer.get_by_role('button',name='Görseli kapat',exact=True).evaluate('button=>{button.click();button.click();}')
        expect(viewer).not_to_be_visible();page.wait_for_timeout(150)
        assert page.url==url
        browser.close()


def test_pin_comments_and_visitor_support_follow_persist(browser_app):
    base,tmp=browser_app;seed_posts(tmp)
    with Session(main.engine) as s:
        s.add(SocialPost(id=2,author_id=1,text='Yeni bilimsel gönderi',status='PUBLISHED',idempotency_key='second-seed',request_hash='synthetic'));s.commit()
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base)
        page=ctx.new_page();page.goto(base+'/expert-support/expert/1')
        expect(page.locator('[data-follow-expert]')).to_have_count(0)
        expect(page.get_by_role('link',name='Uzmandan Destek Al',exact=True)).to_have_count(0)
        first=page.locator('[data-post-id="1"]')
        first.locator('.ds-menu summary').click();first.get_by_role('button',name='Profilde sabitle',exact=True).click()
        expect(page.locator('[data-feed] article').first).to_have_attribute('data-post-id','1')
        expect(first.get_by_label('Sabitlenmiş gönderi')).to_be_visible()
        page.reload();expect(first.get_by_label('Sabitlenmiş gönderi')).to_be_visible()
        first.locator('.ds-menu summary').click();first.get_by_role('button',name='Yorumları kapat',exact=True).click()
        expect(first.locator('[data-comments-state]')).to_have_text('Yorumlar kapalı')
        first.locator('[data-comments-toggle]').click();expect(page.locator('[data-comments-sheet] .ds-comment-form textarea')).to_be_disabled()
        page.get_by_role('button',name='Yorumları kapat',exact=True).click()
        first.locator('.ds-menu summary').click();first.get_by_role('button',name='Yorumları aç',exact=True).click()
        first.locator('[data-comments-toggle]').click();expect(page.locator('[data-comments-sheet] .ds-comment-form textarea')).to_be_enabled()
        page.get_by_role('button',name='Yorumları kapat',exact=True).click()
        first.locator('.ds-menu summary').click();first.get_by_role('button',name='Sabitlemeyi kaldır',exact=True).click()
        expect(first.get_by_label('Sabitlenmiş gönderi')).to_have_count(0)
        ctx.clear_cookies();ctx.add_cookies([{'name':main.SESSION_COOKIE,'value':'browser2','url':base}]);page.reload()
        follow=page.locator('[data-follow-expert]');expect(follow).to_be_visible();follow.click();expect(follow).to_have_attribute('aria-pressed','true')
        expect(page.locator('[data-stat=followers]')).to_have_text('1')
        page.reload();expect(follow).to_have_attribute('aria-pressed','true')
        support=page.get_by_role('link',name='Uzmandan Destek Al',exact=True);expect(support).to_be_visible();support.click()
        page.wait_for_url('**/expert-support/request/1')
        assert 'Test Uzman' in page.locator('body').inner_text()
        expect(page.locator('[name=request_key]')).to_have_value(__import__('re').compile(r'^[0-9a-f-]{36}$'))
        page.locator('[name=clinical_summary]').fill('Kimliksiz sentetik bilimsel danışma senaryosu.')
        page.locator('[name=question]').fill('Bu eğitim senaryosunda değerlendirme nasıl planlanır?')
        page.get_by_role('button',name='Talebi Gönder',exact=True).click()
        page.wait_for_url('**/expert-support/cases/1')
        with Session(main.engine) as s:
            from app.expert_consultation_requests import ConsultationRequestReceipt
            cases=s.exec(select(main.ConsultationCase)).all()
            assert len(cases)==1 and cases[0].expert_user_id==1 and cases[0].requester_user_id==2
            assert len(s.exec(select(ConsultationRequestReceipt)).all())==1
        browser.close()


def test_owner_relationship_lists_and_following_state(browser_app):
    base,tmp=browser_app
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base,user=2)
        page=ctx.new_page();page.goto(base+'/expert-support/expert/1')
        follow=page.locator('[data-follow-expert]');follow.click();expect(follow).to_have_attribute('aria-pressed','true')
        page.reload();expect(follow).to_have_attribute('aria-pressed','true')
        ctx.clear_cookies();ctx.add_cookies([{'name':main.SESSION_COOKIE,'value':'browser1','url':base}]);page.reload()
        page.get_by_role('button',name='Takipçi listesini aç',exact=True).click()
        dialog=page.get_by_role('dialog',name='Takipçiler',exact=True)
        expect(dialog.locator('.ds-relationship-row')).to_have_count(1)
        expect(dialog).to_contain_text('Test Üye')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        dialog.get_by_role('button',name='Listeyi kapat',exact=True).click();expect(dialog).not_to_be_visible()
        page.get_by_role('button',name='Takip edilenleri aç',exact=True).click()
        following=page.get_by_role('dialog',name='Takip edilenler',exact=True)
        expect(following).to_contain_text('Henüz bir uzmanı takip etmiyorsunuz.')
        page.go_back();expect(following).not_to_be_visible()
        ctx.clear_cookies();ctx.add_cookies([{'name':main.SESSION_COOKIE,'value':'browser2','url':base}]);page.reload()
        follow.click();expect(follow).to_have_attribute('aria-pressed','false')
        expect(page.locator('[data-stat=followers]')).to_have_text('0')
        browser.close()


def test_pending_image_admin_approval_refresh_and_member_visibility(browser_app):
    from datetime import timedelta
    from app.expert_social_models import SocialDecision, SocialModerationTask
    base,tmp=browser_app
    with Session(main.engine) as s:
        s.add(main.User(id=4,username='moderator',display_name='Test Yönetici',role='ADMIN',email=main.ADMIN_FIXED_EMAIL,email_verified_at=main._utcnow_naive()))
        token=main.hash_session_token('browser4')
        s.add(main.SessionToken(user_id=4,token_hash=token,expires_at=main._utcnow_naive()+timedelta(days=1)))
        s.add(main.AdminVerifiedSession(token_hash=token,user_id=4));s.commit()
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base)
        owner=ctx.new_page();errors=[];owner.on('pageerror',lambda e:errors.append(str(e)))
        owner.goto(base+'/expert-support/expert/1');owner.locator('[data-compose]').click()
        owner.locator('[data-post-text]').fill('Klinikteyiz — kimliksiz test görseli')
        raw=io.BytesIO();Image.new('RGB',(900,600),'#a7c9d2').save(raw,'JPEG')
        owner.locator('[data-file]').set_input_files({'name':'test.jpg','mimeType':'image/jpeg','buffer':raw.getvalue()})
        expect(owner.locator('.ds-attachment small',has_text='Hazır')).to_have_count(1)
        owner.locator('[data-publish]').click()
        card=owner.locator('[data-post-id="1"]');expect(card.locator('.ds-status')).to_have_text('İncelemede')
        expect(card).to_contain_text('yönetici incelemesi bekliyor')
        card.locator('.ds-menu summary').click();expect(card.get_by_role('button',name='Profilde sabitle',exact=True)).to_have_count(0)
        card.locator('.ds-menu summary').click()
        # Human approval through the real admin screen, using a separate test account.
        # Single-process Chromium does not isolate fetch cookies across contexts.
        # A second process represents a genuinely separate moderator browser.
        adminbrowser,adminctx=browser_context(pw,base,user=4)
        admin=adminctx.new_page();admin.set_viewport_size({'width':1280,'height':900})
        admin.on('pageerror',lambda e:errors.append(str(e)))
        admin.goto(base+main.ADMIN_CENTER_PATH+'/social')
        moderation=admin.locator('[data-admin-list] .ds-card').first
        expect(moderation).to_contain_text('Klinikteyiz')
        expect(admin.locator('[data-queue-aging]')).to_contain_text('Yönetici bekleyen: 1')
        moderation.get_by_role('button',name='İncelenecek görseli aç: 1').click()
        viewer=admin.get_by_role('dialog',name='Gönderi görselleri');expect(viewer).to_be_visible()
        viewer.get_by_role('button',name='Görseli kapat',exact=True).click();expect(viewer).not_to_be_visible()
        dest=Path(os.getenv('TEST_ARTIFACT_DIR',str(tmp/'screenshots')));dest.mkdir(parents=True,exist_ok=True)
        admin.evaluate('window.scrollTo(0,0)')
        admin.screenshot(path=str(dest/'moderation-human-queue-1280.png'),full_page=True)
        moderation.get_by_role('textbox',name='Karar gerekçesi').fill('Sentetik görsel; hasta veya kişisel veri yok.')
        moderation.get_by_role('button',name='Yayınla',exact=True).click()
        expect(admin.locator('[data-admin-notice]')).to_have_text('Gönderi yayında.')
        owner.get_by_role('button',name='Durumu yenile',exact=True).click()
        expect(card.locator('.ds-status')).to_have_count(0)
        with Session(main.engine) as s:
            assert s.get(SocialPost,1).status=='PUBLISHED'
            assert s.exec(select(SocialModerationTask)).one().state=='HUMAN_DONE'
            assert len(s.exec(select(SocialDecision)).all())==2
        owner.reload();expect(card).to_be_visible();expect(card.locator('.ds-status')).to_have_count(0)
        owner.get_by_role('tab',name='Akademik Yayınlar').click();owner.locator('[data-add-publication]').click()
        publication=owner.locator('[data-publication-form]');publication.locator('[name=title]').fill('Sentetik bilimsel yayın')
        publication.get_by_role('button',name='Kaydet',exact=True).click()
        expect(owner.locator('[data-publications] .ds-card')).to_have_count(1)
        admin.locator('[data-kind]').select_option('PUBLICATION');admin.locator('[data-status]').select_option('PUBLISHED')
        admin.get_by_role('button',name='Listele',exact=True).click()
        publication_review=admin.locator('[data-admin-list] .ds-card').first
        expect(publication_review).to_contain_text('Sentetik bilimsel yayın')
        publication_review.get_by_role('textbox',name='Karar gerekçesi').fill('Yayın yılını ve kaynak bağlantısını tamamlayın.')
        publication_review.get_by_role('button',name='Düzenleme iste',exact=True).click()
        expect(admin.locator('[data-admin-notice]')).to_have_text('Düzenleme isteği iletildi.')
        owner.reload();owner.get_by_role('tab',name='Akademik Yayınlar').click()
        expect(owner.locator('[data-publications] .ds-card')).to_contain_text('Düzenleme gerekli')
        expect(owner.locator('[data-publications] .ds-card')).to_contain_text('Yayın yılını ve kaynak bağlantısını tamamlayın.')
        adminbrowser.close()
        ctx.clear_cookies();ctx.add_cookies([{'name':main.SESSION_COOKIE,'value':'browser2','url':base}])
        member=owner;member.set_viewport_size({'width':360,'height':844});member.goto(base+'/expert-support/expert/1')
        expect(member.locator('[data-post-id="1"] .ds-gallery img')).to_be_visible()
        assert member.evaluate('document.documentElement.scrollWidth<=innerWidth')
        member.screenshot(path=str(dest/'approved-image-post-360.png'),full_page=True)
        assert not errors,errors
        browser.close()


def test_unavailable_expert_has_clear_support_state(browser_app):
    base,_=browser_app
    with Session(main.engine) as s:
        profile=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==1)).one()
        profile.availability='BUSY';s.add(profile);s.commit()
    with sync_playwright() as pw:
        browser,ctx=browser_context(pw,base,user=2)
        page=ctx.new_page();page.goto(base+'/expert-support/expert/1')
        expect(page.get_by_role('link',name='Uzmandan Destek Al',exact=True)).to_have_count(0)
        expect(page.locator('.expert-support-unavailable')).to_be_visible()
        expect(page.locator('.expert-support-unavailable')).to_have_text('Şu an yeni vaka kabul etmiyor')
        browser.close()
