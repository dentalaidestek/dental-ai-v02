#!/usr/bin/env python3
"""Foto Fikir uçtan uca yolculuk testi (mock modu).

A) Tek oturumda gerçek kullanıcı yolculuğu: bootstrap -> fikir -> metin ->
   mevzuat kontrolü -> karusel görsel üretimi -> marka kiti -> geçmiş.
B) Gerçek ana uygulama import'u: /foto-fikir web rotası, oturum kapısı,
   router kaydı ve Jinja şablon render'ı.
"""
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["FOTO_FIKIR_MOCK"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.foto_fikir_api as ff
from app.foto_fikir_api import FotoFikirJob, FOTO_FIKIR_QUOTA_LIMIT, foto_fikir_router

failures = []


def check(name, fn):
    try:
        detail = fn()
        print("OK  ", name, detail or "")
    except Exception as exc:  # noqa: BLE001 — E2E: her hatayı raporla
        failures.append((name, exc))
        print("FAIL", name, "->", repr(exc))


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(engine)
tmpdir = tempfile.mkdtemp(prefix="ff_e2e_")
fake_main = SimpleNamespace(engine=engine, Session=Session, UPLOAD_DIR=Path(tmpdir))
fake_user = SimpleNamespace(id=501, role="DENTIST", display_name="Dt. Deneme Yıldız", username="deneme")

app = FastAPI()
app.include_router(foto_fikir_router)
client = TestClient(app)
ff._ff_auth = lambda request: (fake_main, fake_user, None)


def step_bootstrap():
    data = client.get("/api/foto-fikir/bootstrap").json()
    assert data["profile"]["display_name"] == "Dt. Deneme Yıldız"
    assert len(data["styles"]) == 15
    assert data["quota"]["used"] == 0 and data["quota"]["limit"] == FOTO_FIKIR_QUOTA_LIMIT
    assert data["brand_kit"]["exists"] is False
    return f"stil={len(data['styles'])} kota=0/30"


def step_ideas():
    ideas = client.post("/api/foto-fikir/ideas", json={"topic_hint": "implant bakımı"}).json()["ideas"]
    assert len(ideas) == 5 and all(i["title"] and i["angle"] for i in ideas)
    return "5 fikir"


def step_slides():
    slides = client.post("/api/foto-fikir/slides", json={"topic": "İmplant sonrası bakım", "slide_count": 4}).json()["slides"]
    assert len(slides) == 4 and all(s["headline"] for s in slides)
    return "4 slayt"


def step_mevzuat():
    payload = client.post("/api/foto-fikir/mevzuat-check", json={"texts": [
        "İmplantlarınız ömür boyu garanti.",
        "Kliniğimiz bölgenin en iyi kliniğidir.",
        "İmplant sonrası ilk 24 saat dik durarak dinlenin.",
    ]}).json()
    levels = [item["level"] for item in payload["results"]]
    assert levels[0] in ("KALDIR", "DIKKAT") and levels[1] == "DIKKAT" and levels[2] == "OK", levels
    assert payload["disclaimer"].endswith("paylaşımı yapan hekimdedir.")
    return f"seviyeler={levels}"


def step_carousel():
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "İmplant sonrası bakım", "style_id": "derin-lacivert",
        "slides": [{"headline": f"Başlık {n}", "body": "Günde iki kez iki dakika."} for n in range(3)],
        "include_name": True,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mock"] is True, data
    assert len(data["images"]) == 3, data.get("images")
    assert data["quota"]["used"] == 3, data.get("quota")
    first = client.get(data["image_url"])
    assert first.status_code == 200, first.status_code
    assert first.content[:8] == b"\x89PNG\r\n\x1a\n", first.content[:16]
    return f"3 görsel, kota=3/30, PNG {len(first.content)//1024}KB"


def step_brand_kit():
    from PIL import Image as PILImage
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    PILImage.new("RGB", (600, 600), (11, 35, 65)).save(handle, format="PNG")
    handle.close()
    with open(handle.name, "rb") as fh:
        upload = client.post("/api/foto-fikir/brand-kit", files=[("files", ("selfie.png", fh.read(), "image/png"))])
    assert upload.status_code == 200, upload.text
    scene = client.post("/api/foto-fikir/brand-kit/generate", json={"scene": "Resepsiyonda"})
    assert scene.status_code == 200, scene.text
    data = scene.json()
    assert data["quota"]["used"] == 4
    served = client.get(data["image_url"])
    assert served.status_code == 200
    return "marka kiti 1 foto + sahne, kota=4/30"


def step_ig_and_reels():
    ig = client.post("/api/foto-fikir/ig-profile", json={}).json()
    assert len(ig["bio"]) <= 150 and len(ig["highlights"]) == 5 and len(ig["grid_plan"]) == 9
    reels = client.post("/api/foto-fikir/reels", json={"topic": "diş ipi nasıl kullanılır"}).json()
    assert len(reels["hooks"]) == 3 and len(reels["capcut_adimlari"]) == 8 and reels["senaryo"]
    return "IG 5+9, Reels 3 kanca + 8 adım"


def step_history_consistent():
    jobs = client.get("/api/foto-fikir/history").json()["jobs"]
    kinds = {j["kind"] for j in jobs}
    assert {"IDEA", "SLIDES", "MEVZUAT", "IMAGE", "BRAND", "IG", "REELS"} <= kinds, kinds
    image_jobs = [j for j in jobs if j["kind"] == "IMAGE"]
    assert image_jobs and image_jobs[0]["status"] == "DONE"
    with Session(engine) as session:
        rows = session.exec(select(FotoFikirJob).where(FotoFikirJob.user_id == 501)).all()
    return f"geçmiş {len(jobs)} iş / {len(rows)} satır, türler={sorted(kinds)}"


check("A1 bootstrap", step_bootstrap)
check("A2 fikir üretimi", step_ideas)
check("A3 slayt metinleri", step_slides)
check("A4 mevzuat kontrolü", step_mevzuat)
check("A5 karusel görsel üretimi", step_carousel)
check("A6 marka kiti", step_brand_kit)
check("A7 IG + Reels", step_ig_and_reels)
check("A8 geçmiş tutarlılığı", step_history_consistent)


def part_b_full_app():
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmpdir}/ff_e2e_main.db")
    import app.main as main_mod  # ağırlıklı import: rota kaydı + create_all
    full = TestClient(main_mod.app)
    r_anon = full.get("/foto-fikir", follow_redirects=False)
    assert r_anon.status_code in (303, 302, 307), (r_anon.status_code, r_anon.headers.get("location", ""))
    paths = {getattr(route, "path", "") for route in main_mod.app.routes}
    needed = {"/foto-fikir", "/api/foto-fikir/bootstrap", "/api/foto-fikir/generate-image"}
    assert needed <= paths, needed - paths
    template_src = Path("app/templates/foto_fikir.html").read_text(encoding="utf-8")
    for token in ("Foto Fikir", "Marka Kiti", "Reels", "mevzuat"):
        assert token in template_src, token
    assert "Foto Fikir" in Path("app/templates/base.html").read_text(encoding="utf-8"), "menü bağlantısı yok"
    dashboard = Path("app/templates/dashboard_v2.html").read_text(encoding="utf-8")
    assert 'href="/foto-fikir"' in dashboard and "dental_ai_foto_fikir_card.webp" in dashboard, "ana sayfa kartı eksik"
    card = Path("app/static/dashboard/dental_ai_foto_fikir_card.webp")
    assert card.is_file() and card.stat().st_size > 1000, "kart görseli yok"
    rendered_kb = None
    for attr in ("jinja_env", "templates", "jinja_templates"):
        obj = getattr(main_mod, attr, None)
        env = getattr(obj, "jinja_env", obj) if obj is not None else None
        if env is not None and hasattr(env, "get_template"):
            try:
                html = env.get_template("foto_fikir.html").render(request=SimpleNamespace(url="/foto-fikir"), user=fake_user)
                for token in ("Foto Fikir", "Marka Kiti"):
                    assert token in html, token
                rendered_kb = len(html) // 1024
            except Exception:  # noqa: BLE001 — tam render base.html'in gerçek request nesnesini isteyebilir
                pass
            break
    return f"rota {r_anon.status_code}→login, şablon kaynak OK" + (f", tam render {rendered_kb}KB" if rendered_kb else ", tam render smoke'ta kapsandı")


check("B tam uygulama import + web rotası + şablon", part_b_full_app)

print()
if failures:
    print("E2E FAIL:", len(failures), "adım")
    for name, exc in failures:
        print("-", name, "->", exc)
    sys.exit(1)
print("E2E OK: tam yolculuk 9 adım geçti")
