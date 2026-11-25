#!/usr/bin/env python3
"""Foto Fikir offline duman testi (TestClient, mock modu).

Ana uygulama import edilmez; yalnız foto_fikir_router minimal bir FastAPI
uygulamasına bağlanır. Kimlik doğrulama, sahte main modülü ile taklit edilir.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["FOTO_FIKIR_MOCK"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.foto_fikir_api as ff
from app.foto_fikir_api import (
    FF_STYLE_NAMES,
    FOTO_FIKIR_MEVZUAT_DISCLAIMER,
    FOTO_FIKIR_QUOTA_LIMIT,
    FotoFikirJob,
    foto_fikir_quota_used,
    mevzuat_local_check,
    foto_fikir_router,
)
from sqlmodel import select

app = FastAPI()
app.include_router(foto_fikir_router)
client = TestClient(app)

failures = []


def check(name, function):
    try:
        function()
        print("OK  ", name)
    except Exception as exc:  # noqa: BLE001 — smoke: her hatayı raporla
        failures.append((name, exc))
        print("FAIL", name, "->", repr(exc))


def test_unauthenticated_bootstrap_is_rejected():
    ff._ff_auth = REAL_AUTH
    try:
        response = client.get("/api/foto-fikir/bootstrap")
        assert response.status_code in (401, 403), response.status_code
        assert "Oturum gerekli" in response.json()["detail"]
    finally:
        ff._ff_auth = lambda request: (fake_main, fake_user, None)


def _recursive_paths(routes):
    """FastAPI >=0.141 include_router yolları düzleştirmez; _IncludedRouter
    mount'larının içini de gez (daha eski sürümlerde iç içe liste boştur)."""
    paths = set()
    for route in routes:
        path = getattr(route, "path", "")
        if path:
            paths.add(path)
        sub = getattr(route, "routes", None)
        if sub:
            paths |= _recursive_paths(sub)
        original = getattr(route, "original_router", None)
        if original is not None:
            paths |= _recursive_paths(getattr(original, "routes", []))
    return paths


def test_route_list_contains_all_endpoints():
    paths = _recursive_paths(app.routes)
    expected = {
        "/api/foto-fikir/bootstrap",
        "/api/foto-fikir/ideas",
        "/api/foto-fikir/slides",
        "/api/foto-fikir/mevzuat-check",
        "/api/foto-fikir/generate-image",
        "/api/foto-fikir/brand-kit",
        "/api/foto-fikir/brand-kit/generate",
        "/api/foto-fikir/ig-profile",
        "/api/foto-fikir/reels",
        "/api/foto-fikir/history",
        "/uploads/foto_fikir/{owner_id}/{name}",
    }
    missing = expected - paths
    assert not missing, missing


def test_mevzuat_rule_levels():
    assert mevzuat_local_check("Dünyanın en iyi kliniği")["level"] == "DIKKAT"
    assert mevzuat_local_check("Tedavi öncesi sonrası karşılaştırma")["level"] == "KALDIR"
    assert mevzuat_local_check("%100 garanti sonuç")["level"] == "KALDIR"
    assert mevzuat_local_check("İndirimli kampanya")["level"] == "DIKKAT"
    assert mevzuat_local_check("Düzenli kontrol önemlidir.") is None
    assert FOTO_FIKIR_MEVZUAT_DISCLAIMER.endswith("paylaşımı yapan hekimdedir.")
    assert len(FF_STYLE_NAMES) == 15
    assert FOTO_FIKIR_QUOTA_LIMIT == 30


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(engine)
tmpdir = tempfile.mkdtemp(prefix="ff_smoke_")
fake_main = SimpleNamespace(engine=engine, Session=Session, UPLOAD_DIR=Path(tmpdir))
fake_user = SimpleNamespace(id=42, role="DENTIST", display_name="Dr. Örnek Hekim", username="hekim")
REAL_AUTH = ff._ff_auth
ff._ff_auth = lambda request: (fake_main, fake_user, None)


def _add_jobs(user_id, kind, count, *, created_at=None):
    with Session(engine) as session:
        for _ in range(count):
            session.add(FotoFikirJob(id=os.urandom(16).hex(), user_id=user_id, kind=kind, topic="t",
                                     payload="{}", provider="mock", model="mock",
                                     created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None)))
        session.commit()


def test_quota_counts_current_month_only():
    with Session(engine) as session:
        assert foto_fikir_quota_used(session, 77) == 0
    last_month = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=35)
    _add_jobs(77, "IMAGE", 5, created_at=last_month)
    _add_jobs(77, "IMAGE", 7)
    _add_jobs(77, "BRAND", 3)
    _add_jobs(88, "IMAGE", 9)
    with Session(engine) as session:
        assert foto_fikir_quota_used(session, 77) == 10, foto_fikir_quota_used(session, 77)
        assert foto_fikir_quota_used(session, 88) == 9


def test_mock_generate_image_saves_file():
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Diş fırçalama", "style_id": "sade-klinik",
        "slides": [{"headline": "Sabah rutini", "body": "Günde iki kez iki dakika."}],
        "include_name": True,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["image_url"] and data["image_url"].startswith(f"/uploads/foto_fikir/{fake_user.id}/")
    assert data["images"] and data["mock"] is True
    assert data["quota"]["used"] == 1 and data["quota"]["limit"] == FOTO_FIKIR_QUOTA_LIMIT
    file_response = client.get(data["image_url"])
    assert file_response.status_code == 200, file_response.status_code
    assert file_response.content[:8] == b"\x89PNG\r\n\x1a\n"
    saved = Path(tmpdir) / "foto_fikir" / str(fake_user.id) / Path(data["image_url"]).name
    assert saved.is_file() and saved.stat().st_size > 0


def test_overlay_handles_turkish_name():
    import io

    from PIL import Image
    png = ff.foto_fikir_overlay_name(ff._ff_mock_image("konu", "Başlık", "Sade Klinik"), "Dr. Örnek Hekim İÖŞĞÇÜ")
    image = Image.open(io.BytesIO(png))
    assert image.size[0] <= 1080 and image.format == "PNG"
    with Session(engine) as session:
        job = session.exec(select(FotoFikirJob).where(FotoFikirJob.user_id == fake_user.id)).first()
    assert job is not None and job.kind == "IMAGE"


def test_quota_blocks_at_limit():
    _add_jobs(fake_user.id, "IMAGE", FOTO_FIKIR_QUOTA_LIMIT)
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Kontrol", "style_id": "sade-klinik",
        "slides": [{"headline": "Başlık", "body": "Metin"}],
    })
    assert response.status_code == 429, response.status_code
    assert "görsel üretim hakkı doldu" in response.json()["detail"]


def test_mock_ideas_and_history():
    response = client.post("/api/foto-fikir/ideas", json={"topic_hint": "ağız kuruluğu"})
    assert response.status_code == 200, response.text
    ideas = response.json()["ideas"]
    assert len(ideas) == 5 and all(idea["title"] for idea in ideas)
    history = client.get("/api/foto-fikir/history")
    assert history.status_code == 200 and len(history.json()["jobs"]) >= 1


def test_mock_brand_kit_flow():
    from PIL import Image as PILImage
    upload = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    PILImage.new("RGB", (64, 64), (11, 35, 65)).save(upload, format="PNG")
    upload.close()
    fake_user.id = 99  # kota kuyruğundan bağımsız taze kullanıcı
    try:
        with open(upload.name, "rb") as handle:
            response = client.post("/api/foto-fikir/brand-kit",
                                   files=[("files", ("ben.png", handle.read(), "image/png"))])
        assert response.status_code == 200, response.text
        assert response.json()["photos_count"] == 1
        scene = client.post("/api/foto-fikir/brand-kit/generate", json={"scene": "Loupe takarken"})
        assert scene.status_code == 200, scene.text
        assert scene.json()["image_url"] and scene.json()["quota"]["used"] == 1
        bad_scene = client.post("/api/foto-fikir/brand-kit/generate", json={"scene": "yok böylesi"})
        assert bad_scene.status_code == 400
    finally:
        fake_user.id = 42


def test_unavailable_without_key_and_mock_off():
    previous = os.environ.get("FOTO_FIKIR_MOCK")
    os.environ["FOTO_FIKIR_MOCK"] = "0"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        response = client.post("/api/foto-fikir/slides", json={"topic": "kurator konu", "slide_count": 3})
        assert response.status_code == 503, response.status_code
        assert response.json()["detail"] == ff.FOTO_FIKIR_UNAVAILABLE
    finally:
        os.environ["FOTO_FIKIR_MOCK"] = previous or "1"


check("oturumsuz bootstrap 401", test_unauthenticated_bootstrap_is_rejected)
check("endpoint listesi", test_route_list_contains_all_endpoints)
check("mevzuat kuralları", test_mevzuat_rule_levels)
check("kota sayımı", test_quota_counts_current_month_only)
check("mock görsel üretimi dosya kaydeder", test_mock_generate_image_saves_file)
check("isim overlay", test_overlay_handles_turkish_name)
check("kota sınırı 429", test_quota_blocks_at_limit)
check("mock fikirler ve geçmiş", test_mock_ideas_and_history)
check("marka kiti akışı", test_mock_brand_kit_flow)
check("anahtar yoksa 503", test_unavailable_without_key_and_mock_off)

print()
if failures:
    print("SMOKE FAIL:", len(failures), "test")
    for name, exc in failures:
        print("-", name, "->", exc)
    sys.exit(1)
print("SMOKE OK: 10 test geçti")
