import io
import uuid
from datetime import timedelta
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from app import main
from app.expert_social_api import register
from app.expert_social_models import (
    SocialPost,
    SocialComment,
    SocialDecision,
    Publication,
)


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "social.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ENABLED", "0")
    with Session(engine) as s:
        for i, role in [(1, "DOCTOR"), (2, "DOCTOR"), (3, "DOCTOR"), (4, "ADMIN")]:
            s.add(
                main.User(
                    id=i,
                    username="u" + str(i),
                    role=role,
                    display_name="Üye " + str(i),
                    email=main.ADMIN_FIXED_EMAIL if i == 4 else None,
                    email_verified_at=main._utcnow_naive(),
                )
            )
            s.add(
                main.SessionToken(
                    token_hash=main.hash_session_token("t" + str(i)),
                    user_id=i,
                    expires_at=main._utcnow_naive() + timedelta(days=1),
                )
            )
        s.add(
            main.AdminVerifiedSession(
                token_hash=main.hash_session_token("t4"), user_id=4
            )
        )
        for i in (1, 3):
            s.add(
                main.ExpertProfile(
                    user_id=i,
                    specialty="Ortodonti",
                    application_status="APPROVED",
                    verification_status="VERIFIED",
                    specialty_verified=True,
                    credential_document_path="private/document.pdf",
                    phone="05300000000",
                    availability="AVAILABLE",
                )
            )
        s.commit()
    app = FastAPI()
    register(app, main)
    c = TestClient(app)
    c.cookies.set(main.SESSION_COOKIE, "t1")
    c.headers.update({"Origin": "http://testserver", "X-Dental-Social": "1"})
    return c, engine


def post(c, **kw):
    return c.post(
        "/api/expert-social/posts",
        json={
            "text": "Bilimsel bir paylaşım",
            "idempotency_key": str(uuid.uuid4()),
            **kw,
        },
    )


def test_auth_visibility_and_idempotency(env):
    c, e = env
    key = str(uuid.uuid4())
    r = post(c, idempotency_key=key)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["status"] == "PUBLISHED"
    assert post(c, idempotency_key=key).json()["id"] == p["id"]
    assert post(c, idempotency_key=key, text="değişik").status_code == 409
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert post(c).status_code == 403
    assert (
        c.get("/api/expert-social/experts/1/posts").json()["items"][0]["id"] == p["id"]
    )
    assert (
        c.patch(
            "/api/expert-social/posts/" + str(p["id"]),
            json={"text": "başka", "version": 1},
        ).status_code
        == 403
    )
    c.cookies.clear()
    assert c.get("/api/expert-social/experts/1/posts").status_code == 401


def test_pending_privacy_and_comments(env):
    c, e = env
    pending = post(c, text="Hasta adı: Ayşe Yılmaz, 0532 123 45 67").json()
    p = post(c).json()
    c.cookies.set(main.SESSION_COOKIE, "t2")
    ids = [x["id"] for x in c.get("/api/expert-social/experts/1/posts").json()["items"]]
    assert pending["id"] not in ids
    url = f"/api/expert-social/posts/{p['id']}/comments"
    comment = c.post(
        url,
        json={"text": "Kaynak için teşekkürler", "idempotency_key": str(uuid.uuid4())},
    ).json()
    reply = c.post(
        url,
        json={
            "text": "İyi çalışmalar",
            "parent_id": comment["id"],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert reply.status_code == 200, reply.text
    assert len(c.get(url).json()["items"]) == 2
    private = c.post(
        url, json={"text": "hasta@example.org", "idempotency_key": str(uuid.uuid4())}
    ).json()
    assert private["status"] == "PENDING"
    c.cookies.set(main.SESSION_COOKIE, "t3")
    assert len(c.get(url).json()["items"]) == 2


def test_likes_pins_and_comment_closure(env):
    c, e = env
    p = post(c).json()
    q = post(c, text="Diğer konu").json()
    for row in (p, q):
        assert (
            c.patch(
                f"/api/expert-social/posts/{row['id']}",
                json={"pinned": True, "version": row["version"]},
            ).status_code
            == 200
        )
    rows = c.get("/api/expert-social/experts/1/posts").json()["items"]
    assert rows[0]["id"] == q["id"]
    assert sum(x["pinned"] for x in rows) == 1
    c.cookies.set(main.SESSION_COOKIE, "t2")
    for _ in range(2):
        assert (
            c.put(
                f"/api/expert-social/posts/{p['id']}/like", json={"liked": True}
            ).status_code
            == 200
        )
    assert c.get(f"/api/expert-social/posts/{p['id']}").json()["like_count"] == 1
    c.cookies.set(main.SESSION_COOKIE, "t1")
    version = c.get(f"/api/expert-social/posts/{p['id']}").json()["version"]
    c.patch(
        f"/api/expert-social/posts/{p['id']}",
        json={"comments_closed": True, "version": version},
    )
    assert (
        c.post(
            f"/api/expert-social/posts/{p['id']}/comments",
            json={"text": "Yorum", "idempotency_key": str(uuid.uuid4())},
        ).status_code
        == 409
    )


def test_csrf_and_expert_revocation(env):
    c, e = env
    c.headers["Origin"] = "https://evil.example"
    assert post(c).status_code == 403
    c.headers["Origin"] = "http://testserver"
    del c.headers["X-Dental-Social"]
    assert post(c).status_code == 403
    c.headers["X-Dental-Social"] = "1"
    with Session(e) as s:
        p = s.exec(
            select(main.ExpertProfile).where(main.ExpertProfile.user_id == 1)
        ).one()
        p.verification_status = "PENDING"
        s.add(p)
        s.commit()
    assert post(c).status_code == 403


def test_manual_publications_unique_doi_and_edits(env):
    c, e = env
    data = {
        "title": "Makale",
        "authors": "Bir Yazar",
        "year": 2026,
        "doi": "https://doi.org/10.1000/ABC",
        "journal": "Dergi",
    }
    r = c.post("/api/expert-social/publications", json=data)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["source"] == "MANUAL"
    assert (
        c.post(
            "/api/expert-social/publications", json={**data, "doi": "10.1000/abc"}
        ).status_code
        == 409
    )
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert (
        c.get("/api/expert-social/experts/1/publications").json()["items"][0]["title"]
        == "Makale"
    )
    assert (
        c.delete("/api/expert-social/publications/" + str(row["id"])).status_code == 403
    )


def test_media_is_stripped_and_pending_and_not_public(env):
    c, e = env
    b = io.BytesIO()
    Image.new("RGB", (40, 30)).save(b, "JPEG")
    upload = c.post(
        "/api/expert-social/media",
        files={"file": ("photo.jpg", b.getvalue(), "image/jpeg")},
    )
    assert upload.status_code == 200, upload.text
    media = upload.json()
    p = post(c, media_ids=[media["id"]]).json()
    assert p["status"] == "PENDING"
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert c.get(media["url"]).status_code == 404
    c.cookies.set(main.SESSION_COOKIE, "t4")
    r = c.post(
        "/api/expert-social/moderation/POST/" + str(p["id"]),
        json={
            "status": "PUBLISHED",
            "version": p["version"],
            "reason": "Eğitim görseli; hasta verisi yok.",
        },
    )
    assert r.status_code == 200, r.text
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert c.get(media["url"]).status_code == 200
    with Session(e) as s:
        assert len(s.exec(select(SocialDecision)).all()) >= 2


def test_preview_failure_does_not_block_link_post(env, monkeypatch):
    c, e = env

    async def fail(_):
        raise ValueError("unavailable")

    from app import expert_social_safety

    monkeypatch.setattr(expert_social_safety, "preview", fail)
    r = c.post(
        "/api/expert-social/preview",
        json={"url": "https://pubmed.ncbi.nlm.nih.gov/123/"},
    )
    assert r.status_code == 200 and r.json()["available"] is False
    r = post(
        c,
        text="Kaynak https://pubmed.ncbi.nlm.nih.gov/123/",
        link_url="https://pubmed.ncbi.nlm.nih.gov/123/",
    )
    assert r.status_code == 200, r.text


def test_review_version_cannot_approve_newer_content(env):
    c, e = env
    p = post(c, text="Hasta adı: Ayşe").json()
    c.patch(
        f"/api/expert-social/posts/{p['id']}",
        json={"text": "Hasta adı: Başka", "version": p["version"]},
    )
    c.cookies.set(main.SESSION_COOKIE, "t4")
    assert (
        c.post(
            "/api/expert-social/moderation/POST/" + str(p["id"]),
            json={
                "status": "PUBLISHED",
                "version": p["version"],
                "reason": "incelendi",
            },
        ).status_code
        == 409
    )


def test_orcid_import_repeated_and_failure_preserves_manual(env, monkeypatch):
    c, e = env
    from app import expert_publications

    async def sample(orcid):
        assert orcid == "0000-0002-1825-0097"
        return [
            {
                "title": "ORCID makalesi",
                "authors": "",
                "year": 2025,
                "journal": "Dergi",
                "doi": "10.1000/orcid",
                "url": "https://doi.org/10.1000/orcid",
                "source": "ORCID",
                "source_key": "42",
                "description": "",
            }
        ]

    monkeypatch.setattr(expert_publications, "orcid_works", sample)
    for expected in (1, 0):
        r = c.post(
            "/api/expert-social/orcid/sync", json={"orcid": "0000-0002-1825-0097"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["imported_count"] == expected
    rows = c.get("/api/expert-social/experts/1/publications").json()["items"]
    assert len(rows) == 1 and rows[0]["source"] == "ORCID"

    async def unavailable(_):
        raise ValueError("not available")

    monkeypatch.setattr(expert_publications, "orcid_works", unavailable)
    assert (
        c.post(
            "/api/expert-social/orcid/sync", json={"orcid": "0000-0002-1825-0097"}
        ).json()["ok"]
        is False
    )
    assert len(c.get("/api/expert-social/experts/1/publications").json()["items"]) == 1


def test_doi_match_is_issued_by_server_and_lost_on_manual_edit(env, monkeypatch):
    c, e = env
    from app import expert_publications

    async def sample(_):
        return {
            "title": "Makale",
            "authors": "Yazar",
            "year": 2025,
            "journal": "Dergi",
            "doi": "10.1000/sample",
            "url": "https://doi.org/10.1000/sample",
        }

    monkeypatch.setattr(expert_publications, "crossref", sample)
    result = c.post("/api/expert-social/doi", json={"doi": "10.1000/sample"}).json()
    row = c.post("/api/expert-social/publications", json=result).json()
    assert row["source"] == "DOI_MATCH"
    result["title"] = "Değiştirilmiş başlık"
    result["version"] = row["version"]
    updated = c.put(
        "/api/expert-social/publications/" + str(row["id"]), json=result
    ).json()
    assert updated["source"] == "MANUAL"


def test_reports_and_admin_mfa(env):
    c, e = env
    p = post(c).json()
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert (
        c.post(
            "/api/expert-social/reports",
            json={"target_type": "POST", "target_id": p["id"], "reason": "MISLEADING"},
        ).status_code
        == 200
    )
    assert c.get("/api/expert-social/reports").status_code == 403
    c.cookies.set(main.SESSION_COOKIE, "t4")
    assert len(c.get("/api/expert-social/reports").json()["items"]) == 1
    with Session(e) as s:
        auth = s.get(main.AdminVerifiedSession, main.hash_session_token("t4"))
        s.delete(auth)
        s.commit()
    assert c.get("/api/expert-social/moderation").status_code == 401


def test_comment_edit_delete_and_cross_post_reply(env):
    c, e = env
    p = post(c).json()
    q = post(c, text="İkinci bilimsel konu").json()
    a = c.post(
        f"/api/expert-social/posts/{p['id']}/comments",
        json={"text": "İlk yorum", "idempotency_key": str(uuid.uuid4())},
    ).json()
    assert (
        c.post(
            f"/api/expert-social/posts/{q['id']}/comments",
            json={
                "text": "Yanıt",
                "parent_id": a["id"],
                "idempotency_key": str(uuid.uuid4()),
            },
        ).status_code
        == 400
    )
    edited = c.patch(
        "/api/expert-social/comments/" + str(a["id"]),
        json={"text": "Düzenlenmiş yorum", "version": a["version"]},
    )
    assert edited.status_code == 200 and edited.json()["text"] == "Düzenlenmiş yorum"
    assert c.delete("/api/expert-social/comments/" + str(a["id"])).status_code == 200
    assert c.get(f"/api/expert-social/posts/{p['id']}/comments").json()["items"] == []


def test_cursor_has_no_duplicates_and_xss_remains_text(env):
    c, e = env
    p = post(c, text="<img src=x onerror=alert(1)>").json()
    q = post(c, text="İkinci gönderi").json()
    first = c.get("/api/expert-social/experts/1/posts?limit=1").json()
    assert len(first["items"]) == 1 and first["items"][0]["id"] == q["id"]
    second = c.get(
        "/api/expert-social/experts/1/posts?before="
        + str(first["next_cursor"])
        + "&limit=1"
    ).json()
    assert second["items"][0]["id"] == p["id"]
    assert second["items"][0]["text"] == "<img src=x onerror=alert(1)>"
    assert (
        c.get("/api/expert-social/experts/1/posts").headers["cache-control"]
        == "private, no-store"
    )


def test_upload_cannot_attach_other_users_media_or_svg(env):
    c, e = env
    b = io.BytesIO()
    Image.new("RGB", (4, 4)).save(b, "PNG")
    image = c.post(
        "/api/expert-social/media",
        files={"file": ("photo.png", b.getvalue(), "image/png")},
    ).json()
    c.cookies.set(main.SESSION_COOKIE, "t3")
    assert post(c, media_ids=[image["id"]]).status_code == 403
    assert (
        c.post(
            "/api/expert-social/media",
            files={"file": ("evil.svg", b"<svg/>", "image/svg+xml")},
        ).status_code
        == 400
    )


def test_body_limit_and_spam(env):
    c, e = env
    assert (
        c.post(
            "/api/expert-social/posts",
            content=b" " * 70000,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )
    assert post(c).status_code == 200
    assert post(c).status_code == 429
    p = post(c, text="siktir").json()
    assert p["status"] == "REJECTED"
    assert post(c, link_url="https://169.254.169.254/").status_code == 400


# Missing protection: clinical names in a standalone manual bibliography must
# not bypass the same privacy review enforced for posts.
def test_manual_publication_with_patient_contact_is_not_member_visible(env):
    c, e = env
    r = c.post(
        "/api/expert-social/publications",
        json={
            "title": "Hasta: Ayşe Yılmaz",
            "description": "İletişim hasta@example.org",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING"
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert c.get("/api/expert-social/experts/1/publications").json()["items"] == []


def test_same_title_year_deduplicated_when_doi_added(env):
    c, e = env
    assert (
        c.post(
            "/api/expert-social/publications",
            json={"title": "Aynı makale", "year": 2025},
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/expert-social/publications",
            json={"title": "Aynı makale", "year": 2025, "doi": "10.1000/new"},
        ).status_code
        == 409
    )


def test_preview_metadata_cannot_bypass_privacy_review(env, monkeypatch):
    c, e = env
    from app import expert_social_safety

    async def preview(url):
        return {
            "url": url,
            "domain": "example.org",
            "site_name": "Bilim",
            "title": "Hasta adı: Ayşe Yılmaz",
            "description": "Contact: hasta@example.org",
            "image_url": None,
        }

    monkeypatch.setattr(expert_social_safety, "preview", preview)
    preview = c.post(
        "/api/expert-social/preview", json={"url": "https://example.org/article"}
    ).json()
    assert preview["available"] is True
    p = post(
        c,
        text="Bilimsel kaynak",
        link_url="https://example.org/article",
        preview_id=preview["id"],
    ).json()
    assert p["status"] == "PENDING"
    c.cookies.set(main.SESSION_COOKIE, "t2")
    assert c.get("/api/expert-social/experts/1/posts").json()["items"] == []


def test_publication_stale_edit_cannot_undo_newer_review(env):
    c, e = env
    p = c.post(
        "/api/expert-social/publications", json={"title": "Bilimsel yayın"}
    ).json()
    c.cookies.set(main.SESSION_COOKIE, "t4")
    assert (
        c.post(
            "/api/expert-social/moderation/PUBLICATION/" + str(p["id"]),
            json={
                "status": "REJECTED",
                "version": p["version"],
                "reason": "İnceleme kararı",
            },
        ).status_code
        == 200
    )
    c.cookies.set(main.SESSION_COOKIE, "t1")
    r = c.put(
        "/api/expert-social/publications/" + str(p["id"]),
        json={"title": "Yeni içerik", "version": p["version"]},
    )
    assert r.status_code == 409, r.text
