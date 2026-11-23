#!/usr/bin/env python3
"""Foto Fikir sağlamlaştırma ve kıyas paketi (mock + gerçek-motor taklidi).

Gerçek modda paralel üretim (ThreadPoolExecutor), kısmi hata toleransı,
kota ve girdi kenarları, yaratıcı motorun belirlenimciliği ve hız kıyasları
(uretim_ms) sınanır. Duman testindeki TestClient + sahte kimlik deseni
kullanılır; hiçbir gerçek sağlayıcı çağrısı yapılmaz (sağlayıcılar taklit edilir).
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["FOTO_FIKIR_MOCK"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.foto_fikir_api as ff
import app.foto_fikir_creative as cr
from app.foto_fikir_api import (
    FF_STYLES,
    FOTO_FIKIR_QUOTA_LIMIT,
    FotoFikirJob,
    foto_fikir_quota_used,
    foto_fikir_router,
)

app = FastAPI()
app.include_router(foto_fikir_router)
client = TestClient(app)

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(engine)
tmpdir = tempfile.mkdtemp(prefix="ff_hardening_")
fake_main = SimpleNamespace(engine=engine, Session=Session, UPLOAD_DIR=Path(tmpdir))
fake_user = SimpleNamespace(id=1200, role="DENTIST", display_name="Dr. Sağlamlaştırma", username="saglam")
ff._ff_auth = lambda request: (fake_main, fake_user, None)

failures = []


def check(name, function):
    try:
        detail = function()
        print("OK  ", name, detail or "")
    except Exception as exc:  # noqa: BLE001 — sağlamlaştırma: her hatayı raporla
        failures.append((name, exc))
        print("FAIL", name, "->", repr(exc))


def _use_user(user_id):
    fake_user.id = user_id


def _add_quota_jobs(user_id, count):
    with Session(engine) as session:
        for _ in range(count):
            session.add(FotoFikirJob(
                id=os.urandom(16).hex(), user_id=user_id, kind="IMAGE", topic="t", payload="{}",
                provider="mock", model="mock",
            ))
        session.commit()


def _quota_used(user_id):
    with Session(engine) as session:
        return foto_fikir_quota_used(session, user_id)


class _RealMode:
    """Gerçek mod anahtarlarını geçici açar; sağlayıcı çağrısı yapılmaz."""

    def __enter__(self):
        self.previous_mock = os.environ.get("FOTO_FIKIR_MOCK")
        self.previous_claude = os.environ.pop("ANTHROPIC_API_KEY", None)
        self.previous_gemini = os.environ.get("GEMINI_API_KEY")
        os.environ["FOTO_FIKIR_MOCK"] = "0"
        os.environ["GEMINI_API_KEY"] = "test-key-hardening"
        return self

    def __exit__(self, *exc_info):
        if self.previous_mock is None:
            os.environ.pop("FOTO_FIKIR_MOCK", None)
        else:
            os.environ["FOTO_FIKIR_MOCK"] = self.previous_mock
        if self.previous_claude is not None:
            os.environ["ANTHROPIC_API_KEY"] = self.previous_claude
        if self.previous_gemini is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = self.previous_gemini
        return False


def _headline_from_prompt(prompt: str) -> str:
    match = re.search(r"Slayt başlığı: ([^.]+)\.", prompt)
    assert match, prompt[:200]
    return match.group(1)


IYI_KARUSEL = [
    {"headline": "3 dakikada diş ipi nasıl doğru kullanılır?", "body": "İlk 40 cm ipi parmaklarına sar; orta bölüm temiz kalsın."},
    {"headline": "1. Adım: ipi C biçiminde kıvır", "body": "Diş boşluğuna C harfi gibi sar; sert hareket yapma."},
    {"headline": "2. Adım: diş eti hizasında süpür", "body": "Dişeti çizgisini izleyerek yukarı ve aşağı süpür."},
    {"headline": "3. Adım: her ara için temiz bölüm", "body": "Her diş arası için ipin temiz bir bölümünü kaydır."},
    {"headline": "Kaydet ve randevunu planla", "body": "Sorularını yorumlara yaz; takipte kal, randevunu bugün ayır."},
]
ZAYIF_KARUSEL = [
    {"headline": "Diş sağlığı önemlidir.", "body": "Ağız sağlığına dikkat edin."},
    {"headline": "Diş sağlığı önemlidir.", "body": "Fırçalama alışkanlığı edinin."},
    {"headline": "Diş sağlığı önemlidir.", "body": "Kontrolleri aksatmayın."},
]


def test_parallel_real_mode():
    _use_user(1210)
    original_gemini = ff._ff_gemini_image
    thread_ids = []
    try:
        with _RealMode():
            def fake_gemini(prompt, reference_parts=None):
                thread_ids.append(threading.get_ident())
                time.sleep(0.05)
                return ("IMG::" + _headline_from_prompt(prompt)).encode("utf-8")

            ff._ff_gemini_image = fake_gemini
            slides = [{"headline": f"Başlık {n}", "body": "Kısa metin."} for n in range(1, 5)]
            response = client.post("/api/foto-fikir/generate-image", json={
                "topic": "implant bakımı", "style_id": "derin-lacivert", "slides": slides, "include_name": False,
            })
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["mock"] is False
            assert len(data["images"]) == 4, data.get("images")
            assert data["skipped"] == 0, data.get("skipped")
            assert isinstance(data["uretim_ms"], int) and data["uretim_ms"] < 5000, data.get("uretim_ms")
            assert len(set(thread_ids)) >= 2, thread_ids
            contents = []
            for url in data["images"]:
                name = url.rsplit("/", 1)[1]
                contents.append((Path(tmpdir) / "foto_fikir" / "1210" / name).read_text(encoding="utf-8"))
            assert contents == [f"IMG::Başlık {n}" for n in range(1, 5)], contents
            assert data["style_recommendation"]["style_id"] == "derin-lacivert"
            assert data["suggestion"]["style_id"] == "derin-lacivert"
            return f"4 slayt, iş parçacığı={len(set(thread_ids))}, uretim_ms={data['uretim_ms']}"
    finally:
        ff._ff_gemini_image = original_gemini
        _use_user(1200)


def test_partial_failure_skips_slide():
    _use_user(1220)
    original_gemini = ff._ff_gemini_image
    try:
        with _RealMode():
            def fake_gemini(prompt, reference_parts=None):
                if "Başlık 2" in prompt:
                    raise ff.FFUnavailable("sahte sağlayıcı hatası")
                return ("IMG::" + _headline_from_prompt(prompt)).encode("utf-8")

            ff._ff_gemini_image = fake_gemini
            used_before = _quota_used(1220)
            slides = [{"headline": f"Başlık {n}", "body": "Kısa metin."} for n in range(1, 4)]
            response = client.post("/api/foto-fikir/generate-image", json={
                "topic": "Kısmi hata", "style_id": "sade-klinik", "slides": slides, "include_name": False,
            })
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data["images"]) == 2, data.get("images")
            assert data["skipped"] == 1, data.get("skipped")
            assert "üretilemedi" in data.get("uyari", ""), data.get("uyari")
            assert data["quota"]["used"] == used_before + 2, data.get("quota")
            with Session(engine) as session:
                job = session.get(FotoFikirJob, data["job_id"])
            payload = json.loads(job.payload)
            assert payload["skipped"] == 1 and len(payload["image_paths"]) == 2, job.payload[:300]
            assert _quota_used(1220) == used_before + 2, "atlanan slayt kota hakkını şişirmemeli"
            return f"2 görsel kaldı, skipped=1, kota={used_before}+2"
    finally:
        ff._ff_gemini_image = original_gemini
        _use_user(1200)


def test_mock_benchmark_8_slides():
    _use_user(1230)
    slides = [{"headline": f"Kart {n}", "body": "Günde iki kez iki dakika fırçalama."} for n in range(8)]
    started = time.perf_counter()
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Hız kıyası", "style_id": "sade-klinik", "slides": slides,
    })
    wall_ms = int((time.perf_counter() - started) * 1000)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["images"]) == 8, data.get("images")
    assert isinstance(data["uretim_ms"], int), data.get("uretim_ms")
    assert wall_ms < 1500, f"duvar süresi {wall_ms} ms >= 1500 ms"
    assert data["uretim_ms"] < 1500, f"uretim_ms {data['uretim_ms']} >= 1500"
    assert data["quota"]["used"] == 8 and data["quota"]["limit"] == FOTO_FIKIR_QUOTA_LIMIT
    return f"duvar={wall_ms} ms, uretim_ms={data['uretim_ms']}"


def test_quota_429_exact_message():
    _use_user(1240)
    _add_quota_jobs(1240, FOTO_FIKIR_QUOTA_LIMIT)
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Kota", "style_id": "sade-klinik", "slides": [{"headline": "Başlık", "body": "Metin"}],
    })
    assert response.status_code == 429, response.status_code
    assert response.json()["detail"] == (
        "Bu ayın 30 görsel üretim hakkı doldu. Haklar her ayın ilk gününde yenilenir."
    )
    _use_user(1200)


def test_nine_slides_rejected():
    _use_user(1250)
    slides = [{"headline": f"Başlık {n}", "body": "Metin"} for n in range(9)]
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Çok slayt", "style_id": "sade-klinik", "slides": slides,
    })
    assert response.status_code == 400, response.status_code
    assert response.json()["detail"] == "En fazla 8 slayt gönderilebilir."
    _use_user(1200)


def test_empty_slide_filtered():
    _use_user(1251)
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Süzme", "style_id": "sade-klinik",
        "slides": [{"headline": "Dolu", "body": "Metin"}, {"headline": "   ", "body": ""}],
    })
    assert response.status_code == 200, response.text
    assert len(response.json()["images"]) == 1, response.json().get("images")
    _use_user(1200)


def test_whitespace_topic_400():
    _use_user(1252)
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "   ", "style_id": "sade-klinik", "slides": [],
    })
    assert response.status_code == 400, response.status_code
    assert response.json()["detail"] == "Konu ve en az bir slayt metni gerekli."
    _use_user(1200)


def test_long_body_trimmed():
    _use_user(1253)
    response = client.post("/api/foto-fikir/generate-image", json={
        "topic": "Kırpma", "style_id": "sade-klinik",
        "slides": [{"headline": "Başlık", "body": "uzun " * 60}],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    with Session(engine) as session:
        job = session.get(FotoFikirJob, data["job_id"])
    payload = json.loads(job.payload)
    assert len(payload["slides"][0]["body"]) == 220, len(payload["slides"][0]["body"])
    _use_user(1200)


def test_recommend_style_rules():
    assert cr.recommend_style("implant sonrası bakım") == cr.recommend_style("implant sonrası bakım")
    assert cr.recommend_style("İMPLANT sonrası bakım") == cr.recommend_style("implant sonrası bakım")
    assert cr.recommend_style("Beyazlatma ve estetik")["style_id"] == "yumusak-gul"
    assert cr.recommend_style("Çocuklarda fırçalama")["style_id"] == "nane-esintisi"
    assert cr.recommend_style("diş ipi rutini")["style_id"] == "su-cizgisi"
    assert cr.recommend_style("eğitim serisi")["style_id"] == "sade-klinik"
    unknown = cr.recommend_style("zzz bilinmeyen konu")
    assert unknown["style_id"] == "sade-klinik", unknown
    assert "eşleşme bulunamadı" in unknown["reason"], unknown
    assert set(cr.recommend_style("implant")) == {"style_id", "reason"}
    for style in FF_STYLES:
        reason = cr.recommend_style(style["id"])["reason"]
        assert reason and isinstance(reason, str)


def test_prompt_distinct_all_15_styles():
    slide = {"headline": "İmplant sonrası ilk 24 saat", "body": "Dik durun."}
    prompts = [cr.creative_prompt_for_slide("konu", style["id"], slide) for style in FF_STYLES]
    assert len(set(prompts)) == 15, len(set(prompts))
    assert all(len(prompt) < 4000 for prompt in prompts)
    assert all("yazı olmasın" in prompt for prompt in prompts)


def test_story_arc_roles_shape():
    assert cr.story_arc_roles(1) == ["Kanca + Kapanış/CTA"]
    for n in range(1, 9):
        roles = cr.story_arc_roles(n)
        assert len(roles) == n, (n, roles)
        assert "CTA" in roles[-1] or "Kapanış" in roles[-1], (n, roles)
        if n <= 4:
            assert len(set(roles)) == n, (n, roles)
    assert cr.story_arc_roles("4") == cr.story_arc_roles(4)
    assert cr.story_arc_roles(99) == cr.story_arc_roles(8)
    assert cr.story_arc_roles(None) == cr.story_arc_roles(1)


def test_audit_tips():
    zayif_audit = cr.audit_creative_output("IMAGE", {"slides": ZAYIF_KARUSEL, "style": "sade-klinik"})
    tips = cr.actionable_tips(zayif_audit)
    assert tips and all(isinstance(tip, str) and tip for tip in tips), tips
    assert len(tips) <= 2, tips
    assert cr.actionable_tips(zayif_audit) == tips, "öneriler belirlenimci olmalı"
    iyi_audit = cr.audit_creative_output("IMAGE", {"slides": IYI_KARUSEL, "style": "derin-lacivert"})
    assert iyi_audit["score"] >= 70, iyi_audit
    assert len(cr.actionable_tips(iyi_audit)) <= 2, cr.actionable_tips(iyi_audit)
    assert cr.actionable_tips({"notes": []}) == []
    assert cr.actionable_tips(None) == []
    return f"iyi karusel {iyi_audit['score']}/100, ipuçları={len(cr.actionable_tips(iyi_audit))}"


def test_audit_speed_1000_calls():
    data = {"topic": "hız", "slides": IYI_KARUSEL, "style": "derin-lacivert"}
    started = time.perf_counter()
    for _ in range(1000):
        cr.audit_creative_output("IMAGE", data)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"1000 çağrı {elapsed:.3f} sn sürdü"
    return f"1000 çağrı {elapsed * 1000:.0f} ms"


def test_api_tips_and_roles_mock():
    _use_user(1260)
    slides_resp = client.post("/api/foto-fikir/slides", json={"topic": "çocuklarda fırçalama", "slide_count": 4})
    assert slides_resp.status_code == 200, slides_resp.text
    slides = slides_resp.json()["slides"]
    assert [s["role"] for s in slides] == cr.story_arc_roles(4), slides
    ideas = client.post("/api/foto-fikir/ideas", json={"topic_hint": "implant bakımı"}).json()
    assert isinstance(ideas["tips"], list) and all(isinstance(tip, str) for tip in ideas["tips"])
    reels = client.post("/api/foto-fikir/reels", json={"topic": "diş ipi kullanımı"}).json()
    assert isinstance(reels["tips"], list) and reels["creative_audit"]["kind"] == "REELS"
    generate = client.post("/api/foto-fikir/generate-image", json={
        "topic": "implant bakımı", "style_id": "nane-esintisi",
        "slides": [{"headline": "Başlık", "body": "Metin"}],
    }).json()
    assert generate["style_recommendation"]["style_id"] == "derin-lacivert"
    assert generate["suggestion"]["style_id"] == "derin-lacivert"
    assert isinstance(generate["tips"], list) and isinstance(generate["uretim_ms"], int)
    assert isinstance(generate["skipped"], int) and generate["skipped"] == 0
    _use_user(1200)


def test_brand_scene_uretim_ms_mock():
    from PIL import Image as PILImage
    _use_user(1270)
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    PILImage.new("RGB", (64, 64), (11, 35, 65)).save(handle, format="PNG")
    handle.close()
    with open(handle.name, "rb") as fh:
        upload = client.post("/api/foto-fikir/brand-kit", files=[("files", ("kit.png", fh.read(), "image/png"))])
    assert upload.status_code == 200, upload.text
    scene = client.post("/api/foto-fikir/brand-kit/generate", json={"scene": "Loupe takarken"})
    assert scene.status_code == 200, scene.text
    assert isinstance(scene.json()["uretim_ms"], int) and scene.json()["uretim_ms"] >= 0
    _use_user(1200)


check("paralel gerçek mod: sıra korunur, eşzamanlı, uretim_ms", test_parallel_real_mode)
check("kısmi hata: slayt atlanır, Türkçe not, kota şişmez", test_partial_failure_skips_slide)
check("mock 8 slayt kıyası: 1500 ms altı", test_mock_benchmark_8_slides)
check("kota kenarı: 429 tam mesaj", test_quota_429_exact_message)
check("girdi kenarı: 9 slayt 400", test_nine_slides_rejected)
check("girdi kenarı: boş slayt metni süzülür", test_empty_slide_filtered)
check("girdi kenarı: yalnız boşluk konu 400", test_whitespace_topic_400)
check("girdi kenarı: 220+ karakter gövde kırpılır", test_long_body_trimmed)
check("recommend_style: determinizm + İ katlama + kurallar", test_recommend_style_rules)
check("15 stil: ayrı promptlar, 4000 altı, yazı yasağı", test_prompt_distinct_all_15_styles)
check("story_arc_roles: 1..8 geçerli", test_story_arc_roles_shape)
check("denetim ipuçları: zayıf dolu, iyi 2 ve altı", test_audit_tips)
check("denetim hızı: 1000 çağrı 1.0 sn altı", test_audit_speed_1000_calls)
check("api ipuçları ve roller (mock)", test_api_tips_and_roles_mock)
check("marka sahne uretim_ms (mock)", test_brand_scene_uretim_ms_mock)

print()
print(f"KISAS KARTI — mock 8 slayt karusel ve 1000 denetim çağrısı yukarıdaki sürelerle ölçüldü.")
if failures:
    print("HARDENING FAIL:", len(failures), "test")
    for name, exc in failures:
        print("-", name, "->", exc)
    sys.exit(1)
print("HARDENING OK: 15 test geçti")
