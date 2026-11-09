"""Private relationship lists and the feed of followed, verified experts."""

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import event
from sqlmodel import Session, select

from app import main
from app.expert_social_models import (
    SocialComment,
    SocialFollow,
    SocialLike,
    SocialMedia,
    SocialPost,
)
from test_api import env
from test_browser import browser_app


PREFIX = "/api/expert-social"


def test_following_page_requires_an_active_member(env):
    _, engine = env
    client = TestClient(main.app)
    try:
        assert client.get("/expert-support/following").status_code == 401
        client.cookies.set(main.SESSION_COOKIE, "t2")
        response = client.get("/expert-support/following")
        assert response.status_code == 200, response.text
        assert "<title>Dental Akış</title>" in response.text
        assert '<h1>Dental Akış</h1>' in response.text
        assert response.text.count('id="expertSocial"') == 1
        assert 'data-feed-mode="following"' in response.text
        assert 'data-user-id="2"' in response.text
        assert 'data-owner="0"' in response.text
        assert 'data-expert-id="0"' in response.text
        assert 'data-feed ' in response.text
        assert 'data-more-posts' in response.text
        assert '/static/expert-social.css?v=20261109-2' in response.text
        assert '/static/expert-social.js?v=20261109-2' in response.text
        assert '/static/expert-media-viewer.js?' in response.text
        assert 'href="/expert-support"' in response.text
        assert 'data-composer' not in response.text
        assert 'data-publications' not in response.text
        assert response.headers["cache-control"] == "private, no-store"
        with Session(engine) as session:
            viewer = session.get(main.User, 2)
            viewer.is_active = False
            session.add(viewer)
            session.commit()
        assert client.get("/expert-support/following").status_code == 401
    finally:
        client.close()


def test_dashboard_links_to_following_without_mounting_its_feed(env):
    client = TestClient(main.app)
    client.cookies.set(main.SESSION_COOKIE, "t2")
    try:
        response = client.get("/")
        assert response.status_code == 200, response.text
        assert 'href="/dental-akis"' in response.text
        assert "Dental Akış" in response.text
        assert "expert-social.js" not in response.text
        assert "data-expert-social" not in response.text
    finally:
        client.close()


def test_following_page_loads_one_feed_with_working_member_actions(browser_app):
    base, temporary = browser_app
    with Session(main.engine) as session:
        session.add(SocialFollow(follower_id=2, expert_id=1))
        row = add_post(session, 1)
        post_id = row.id
        session.commit()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM", "/tmp/chromium"),
            args=["--no-sandbox", "--single-process", "--no-zygote"],
        )
        try:
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
            )
            context.add_cookies(
                [{"name": main.SESSION_COOKIE, "value": "browser2", "url": base}]
            )
            page = context.new_page()
            errors, social_requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: social_requests.append(request.url)
                if "/api/expert-social/" in request.url
                else None,
            )
            page.goto(base + "/")
            assert not social_requests
            page.locator("main .visual-following-link").click()
            page.get_by_role('navigation', name='Dental Akış bölümleri').get_by_role('link', name='Takip Ettiklerim', exact=True).click()
            expect(page.get_by_role("heading", name="Dental Akış")).to_be_visible()
            card = page.locator(f'[data-post-id="{post_id}"]')
            expect(page.locator("[data-feed] > article")).to_have_count(1)
            expect(card.locator(".ds-author a")).to_have_attribute(
                "href", "/expert-support/expert/1"
            )
            card.get_by_role("button", name="Beğen", exact=True).click()
            expect(card.get_by_role("button", name="Beğenmekten vazgeç", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            card.locator("[data-comments-toggle]").click()
            page.get_by_role("textbox", name="Yorum metni").fill("Bilimsel paylaşım için teşekkürler")
            page.get_by_role("button", name="Gönder", exact=True).click()
            expect(page.locator(".ds-comment")).to_contain_text(
                "Bilimsel paylaşım için teşekkürler"
            )
            page.get_by_role("button", name="Yorumları kapat", exact=True).click()
            for width in (390, 1280):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
            artifacts = Path(os.getenv("TEST_ARTIFACT_DIR", str(temporary / "screenshots")))
            artifacts.mkdir(parents=True, exist_ok=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(artifacts / "following-feed-390.png"))
            assert not any("/experts/0/" in url for url in social_requests)
            assert not any("/publications" in url for url in social_requests)
            assert not errors, errors
        finally:
            browser.close()


def add_account(session, user_id, *, active=True, verified=True):
    user = main.User(
        id=user_id,
        username=f"member-{user_id}",
        role="DOCTOR",
        display_name=f"Üye {user_id}",
        is_active=active,
        email=f"private-{user_id}@example.org",
    )
    session.add(user)
    session.add(
        main.ExpertProfile(
            user_id=user_id,
            specialty="Ortodonti",
            application_status="APPROVED",
            verification_status="VERIFIED" if verified else "PENDING",
            specialty_verified=True,
            credential_document_path="private/document.pdf",
            phone="05300000000",
            availability="AVAILABLE",
        )
    )
    return user


def add_post(session, author_id, *, status="PUBLISHED", **values):
    row = SocialPost(
        author_id=author_id,
        text=f"Bilimsel paylaşım {uuid.uuid4()}",
        status=status,
        idempotency_key=str(uuid.uuid4()),
        request_hash="test-request-hash",
        **values,
    )
    session.add(row)
    session.flush()
    return row


def test_relationship_reads_require_active_owner(env):
    client, engine = env
    paths = [
        f"{PREFIX}/experts/1/followers",
        f"{PREFIX}/experts/1/following",
        f"{PREFIX}/feed/following",
    ]
    client.cookies.clear()
    for path in paths:
        assert client.get(path).status_code == 401
    client.cookies.set(main.SESSION_COOKIE, "t2")
    for path in paths[:2]:
        assert client.get(path).status_code == 403
    # Private graphs are owner-only even for an otherwise authorized admin.
    client.cookies.set(main.SESSION_COOKIE, "t4")
    for path in paths[:2]:
        assert client.get(path).status_code == 403
    client.cookies.set(main.SESSION_COOKIE, "t1")
    with Session(engine) as session:
        owner = session.get(main.User, 1)
        owner.is_active = False
        session.add(owner)
        session.commit()
    for path in paths:
        assert client.get(path).status_code == 401


def test_regular_member_can_read_own_following_and_feed(env):
    client, _ = env
    client.cookies.set(main.SESSION_COOKIE, "t2")
    follow = client.put(f"{PREFIX}/experts/1/follow", json={"followed": True})
    assert follow.status_code == 200
    response = client.get(f"{PREFIX}/experts/2/following")
    assert response.status_code == 200, response.text
    assert [row["user_id"] for row in response.json()["items"]] == [1]
    assert response.json()["items"][0]["following_by_viewer"] is True
    assert client.get(f"{PREFIX}/experts/2/followers").status_code == 404
    assert client.get(f"{PREFIX}/feed/following").json()["items"] == []


def test_followers_only_include_active_members_and_verified_identity(env):
    client, engine = env
    with Session(engine) as session:
        add_account(session, 5, active=False)
        add_account(session, 6, verified=False)
        profile = session.exec(
            select(main.ExpertProfile).where(main.ExpertProfile.user_id == 3)
        ).one()
        profile.academic_title = "Prof. Dr."
        profile.academic_title_verified = True
        session.add(profile)
        for user_id in (2, 3, 5, 6):
            session.add(SocialFollow(follower_id=user_id, expert_id=1))
        session.commit()
    response = client.get(f"{PREFIX}/experts/1/followers")
    assert response.status_code == 200, response.text
    rows = {row["user_id"]: row for row in response.json()["items"]}
    assert set(rows) == {2, 3, 6}
    assert rows[3]["is_expert"] is True
    assert rows[3]["profile_url"] == "/expert-support/expert/3"
    assert "Prof. Dr." in rows[3]["name"]
    for user_id in (2, 6):
        assert rows[user_id]["is_expert"] is False
        assert rows[user_id]["profile_url"] is None
        assert rows[user_id]["specialty"] is None
    assert not any(
        field in response.text
        for field in ("private-", "document.pdf", "05300000000", "password_hash")
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Cookie"


@pytest.mark.parametrize(
    "title,title_verified,expected",
    [
        (None, False, "Uzm. Dt. Ayşe Örnek"),
        ("Profesör", True, "Uzm. Dt. Ayşe Örnek"),
        ("Doç. Dr.", True, "Doç. Dr. Ayşe Örnek"),
    ],
)
def test_relationship_expert_names_only_display_verified_supported_titles(
    env, title, title_verified, expected
):
    client, engine = env
    with Session(engine) as session:
        member = session.get(main.User, 3)
        member.display_name = "Prof. Dr. Ayşe Örnek"
        profile = session.exec(
            select(main.ExpertProfile).where(main.ExpertProfile.user_id == 3)
        ).one()
        profile.academic_title = title
        profile.academic_title_verified = title_verified
        session.add(member)
        session.add(profile)
        session.add(SocialFollow(follower_id=3, expert_id=1))
        session.commit()
    response = client.get(f"{PREFIX}/experts/1/followers")
    assert response.json()["items"][0]["name"] == expected


def test_following_excludes_inactive_and_revoked_experts(env):
    client, engine = env
    with Session(engine) as session:
        add_account(session, 5, active=False)
        add_account(session, 6, verified=False)
        for user_id in (3, 5, 6):
            session.add(SocialFollow(follower_id=1, expert_id=user_id))
        session.commit()
    response = client.get(f"{PREFIX}/experts/1/following")
    assert response.status_code == 200, response.text
    assert [row["user_id"] for row in response.json()["items"]] == [3]
    assert response.json()["next_cursor"] is None


def test_relationship_counts_match_filtered_owner_lists(env):
    from app.expert_social_relationships import relationship_counts

    client, engine = env
    with Session(engine) as session:
        add_account(session, 5, active=False)
        add_account(session, 6, verified=False)
        add_account(session, 7)
        for user_id in (2, 3, 5, 6):
            session.add(SocialFollow(follower_id=user_id, expert_id=1))
        for user_id in (3, 5, 6, 7):
            session.add(SocialFollow(follower_id=1, expert_id=user_id))
        session.add(main.UserBlock(blocker_user_id=3, blocked_user_id=1))
        session.commit()
    with Session(engine) as session:
        counts = relationship_counts(session, main, 1)
    assert counts == {"followers": 2, "following": 1}
    for kind in ("followers", "following"):
        visible = client.get(f"{PREFIX}/experts/1/{kind}").json()["items"]
        assert counts[kind] == len(visible)


@pytest.mark.parametrize("blocked_by_viewer", [True, False])
def test_existing_user_blocks_hide_relationships_and_feed_in_both_directions(
    env, blocked_by_viewer
):
    client, engine = env
    paths = [
        f"{PREFIX}/experts/1/followers",
        f"{PREFIX}/experts/1/following",
        f"{PREFIX}/feed/following",
    ]
    with Session(engine) as session:
        session.add(SocialFollow(follower_id=1, expert_id=3))
        session.add(SocialFollow(follower_id=3, expert_id=1))
        add_post(session, 3)
        session.commit()
    for path in paths:
        assert len(client.get(path).json()["items"]) == 1
    with Session(engine) as session:
        session.add(
            main.UserBlock(
                blocker_user_id=1 if blocked_by_viewer else 3,
                blocked_user_id=3 if blocked_by_viewer else 1,
            )
        )
        session.commit()
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("kind", ["followers", "following"])
def test_relationship_lists_have_stable_bounded_cursors(env, kind):
    client, engine = env
    with Session(engine) as session:
        for user_id in range(5, 24):
            add_account(session, user_id)
            session.add(
                SocialFollow(
                    follower_id=user_id if kind == "followers" else 1,
                    expert_id=1 if kind == "followers" else user_id,
                )
            )
        session.commit()
    path = f"{PREFIX}/experts/1/{kind}"
    first = client.get(path).json()
    assert len(first["items"]) == 15
    assert first["next_cursor"] == 9
    second = client.get(path, params={"before": first["next_cursor"]}).json()
    ids = [row["user_id"] for row in first["items"] + second["items"]]
    assert ids == list(range(23, 4, -1))
    assert second["next_cursor"] is None
    assert client.get(path, params={"limit": 31}).status_code == 422
    assert client.get(path, params={"before": 0}).status_code == 422


def test_followed_feed_only_returns_published_active_verified_authors(env):
    client, engine = env
    with Session(engine) as session:
        add_account(session, 5, active=False)
        add_account(session, 6, verified=False)
        for user_id in (3, 5, 6):
            session.add(SocialFollow(follower_id=1, expert_id=user_id))
        visible = add_post(session, 3).id
        for status in ("PENDING", "REJECTED", "DELETED"):
            add_post(session, 3, status=status)
        for user_id in (1, 5, 6):
            add_post(session, user_id)
        session.commit()
    response = client.get(f"{PREFIX}/feed/following")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["items"]] == [visible]
    client.put(f"{PREFIX}/experts/3/follow", json={"followed": False})
    assert client.get(f"{PREFIX}/feed/following").json()["items"] == []


@pytest.mark.parametrize(
    "model,field,value",
    [
        (main.User, "role", "STUDENT"),
        (main.ExpertProfile, "application_status", "REJECTED"),
        (main.ExpertProfile, "verification_status", "PENDING"),
        (main.ExpertProfile, "specialty_verified", False),
        (main.ExpertProfile, "credential_document_path", None),
        (main.ExpertProfile, "credential_document_path", ""),
        (main.ExpertProfile, "phone", None),
        (main.ExpertProfile, "phone", ""),
    ],
)
def test_followed_expert_revocation_takes_effect_on_the_next_read(
    env, model, field, value
):
    client, engine = env
    with Session(engine) as session:
        session.add(SocialFollow(follower_id=1, expert_id=3))
        add_post(session, 3)
        session.commit()
    assert len(client.get(f"{PREFIX}/feed/following").json()["items"]) == 1
    with Session(engine) as session:
        row = (
            session.get(main.User, 3)
            if model is main.User
            else session.exec(
                select(main.ExpertProfile).where(main.ExpertProfile.user_id == 3)
            ).one()
        )
        setattr(row, field, value)
        session.add(row)
        session.commit()
    assert client.get(f"{PREFIX}/feed/following").json()["items"] == []
    assert client.get(f"{PREFIX}/experts/1/following").json()["items"] == []


def test_followed_feed_reuses_post_metadata_and_batched_queries(env):
    client, engine = env
    with Session(engine) as session:
        for user_id in range(5, 25):
            add_account(session, user_id)
            session.add(SocialFollow(follower_id=1, expert_id=user_id))
            row = add_post(session, user_id)
        post_id = row.id
        row.preview_json = json.dumps({"title": "Kaynak", "site_name": "Dergi"})
        row.pinned = True
        session.add(row)
        session.add(SocialLike(post_id=post_id, user_id=1))
        session.add(
            SocialMedia(owner_id=24, post_id=post_id, reference="private/image.jpg")
        )
        for status in ("PUBLISHED", "PENDING", "DELETED"):
            session.add(
                SocialComment(
                    author_id=2,
                    post_id=post_id,
                    text="Kaynak için teşekkürler",
                    status=status,
                    idempotency_key=str(uuid.uuid4()),
                    request_hash="test-comment",
                )
            )
        session.commit()
    statements = []

    def observe(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = client.get(f"{PREFIX}/feed/following")
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    first = response.json()
    assert len(first["items"]) == 15
    assert len(statements) <= 10
    assert first["items"][0] == client.get(f"{PREFIX}/posts/{post_id}").json()
    assert first["items"][0]["like_count"] == 1
    assert first["items"][0]["comment_count"] == 1
    assert first["items"][0]["liked"] is True
    assert first["items"][0]["media"][0]["url"].startswith(f"{PREFIX}/media/")
    # A newly published item cannot displace or duplicate an already read page.
    with Session(engine) as session:
        add_post(session, 5)
        session.commit()
    second = client.get(
        f"{PREFIX}/feed/following", params={"before": first["next_cursor"]}
    ).json()
    ids = [row["id"] for row in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 20
    assert ids == sorted(ids, reverse=True)
    assert second["next_cursor"] is None
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(f"{PREFIX}/feed/following", params={"limit": 31}).status_code == 422
