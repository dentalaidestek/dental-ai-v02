#!/usr/bin/env python3
"""Foto Fikir yaratıcı yönetmen motoru denetim paketi (mock modu).

Tasarım sistemi, yönetmen prompt'u, kanca/karusel rubrikleri, reel çekim
planı, çıktı denetimi, mevzuat uyumlu öneri ve API entegrasyonunu sınar.
Duman testindeki TestClient + sahte kimlik deseni kullanılır.
"""
import json
import os
import re
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
import app.foto_fikir_creative as cr
from app.foto_fikir_api import FF_STYLES, FOTO_FIKIR_MEVZUAT_DISCLAIMER, FotoFikirJob, foto_fikir_router

app = FastAPI()
app.include_router(foto_fikir_router)
client = TestClient(app)

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(engine)
tmpdir = tempfile.mkdtemp(prefix="ff_creative_")
fake_main = SimpleNamespace(engine=engine, Session=Session, UPLOAD_DIR=Path(tmpdir))
fake_user = SimpleNamespace(id=801, role="DENTIST", display_name="Dr. Denetim Hekimi", username="denetim")
ff._ff_auth = lambda request: (fake_main, fake_user, None)

failures = []


def check(name, function):
    try:
        function()
        print("OK  ", name)
    except Exception as exc:  # noqa: BLE001 — denetim: her hatayı raporla
        failures.append((name, exc))
        print("FAIL", name, "->", repr(exc))


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
REELS_ORNEK = {
    "topic": "diş ipi kullanımı",
    "hooks": ["3 dakikada diş ipi nasıl doğru kullanılır?", "Diş ipini bu yanlışla kullanıyor musunuz?", "Çoğu kişi diş ipini aslında yanlış kullanıyor"],
    "senaryo": [
        {"aralik": "0-3 sn", "metin": "Yanlışı soruyla aç."},
        {"aralik": "3-15 sn", "metin": "İki uygulamayı makro planda göster."},
        {"aralik": "15-25 sn", "metin": "Resepsiyonda kapanış çağrısı yap."},
    ],
}
for row in REELS_ORNEK["senaryo"]:
    row["shot"] = cr.reel_shot_plan(REELS_ORNEK["topic"], row["aralik"], row["metin"])


def test_design_system_covers_all_styles():
    beklenen = {style["id"] for style in FF_STYLES}
    assert set(cr.FF_DESIGN_SYSTEM) == beklenen, (set(cr.FF_DESIGN_SYSTEM) ^ beklenen)
    hex_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for style_id, spec in cr.FF_DESIGN_SYSTEM.items():
        palet = spec["palet"]
        assert set(palet) == {"zemin", "vurgu", "metin"}, (style_id, set(palet))
        for rol, renk in palet.items():
            assert hex_re.fullmatch(renk), (style_id, rol, renk)
        for alan in ("tipografi", "kompozisyon", "isik", "doku", "kullanim"):
            assert isinstance(spec[alan], str) and spec[alan].strip(), (style_id, alan)


def test_creative_prompt_rules():
    spec = cr.FF_DESIGN_SYSTEM["derin-lacivert"]
    slide = {"headline": "İmplant sonrası ilk 24 saat", "body": "Dik durarak dinlenin; sıcak şeyler kaçının."}
    prompt_id = cr.creative_prompt_for_slide("İmplant sonrası bakım", "derin-lacivert", slide)
    prompt_ad = cr.creative_prompt_for_slide("İmplant sonrası bakım", "Derin Lacivert", slide)
    assert prompt_id == prompt_ad, "kimlik ve ad ile kurulan promptlar eşleşmeli"
    for renk in spec["palet"].values():
        assert renk in prompt_id, renk
    assert spec["isik"] in prompt_id and spec["kompozisyon"].split(",")[0] in prompt_id
    assert "yazı olmasın" in prompt_id
    for negatif in ("filigran", "logo", "bozuk el"):
        assert negatif in prompt_id, negatif
    assert "anatomi" in prompt_id and "deform" in prompt_id
    assert cr.creative_prompt_for_slide("k", "derin-lacivert", {"headline": "A", "body": ""}) != prompt_id
    markali = cr.creative_prompt_for_slide("İmplant", "derin-lacivert", slide, brand_name="Gülümse Klinik")
    assert markali != prompt_id and "Gülümse Klinik" in markali
    bilinmeyen = cr.creative_prompt_for_slide("konu", "boyle-bir-stil-yok", slide)
    assert cr.FF_DESIGN_SYSTEM["sade-klinik"]["palet"]["zemin"] in bilinmeyen


def test_score_hook_rubric():
    guclu = cr.score_hook("3 dakikada diş ipi nasıl doğru kullanılır?")
    zayif = cr.score_hook("Diş sağlığı önemlidir.")
    assert guclu["score"] >= 70, guclu
    assert zayif["score"] <= 45, zayif
    for sonuc in (guclu, zayif):
        assert 0 <= sonuc["score"] <= 100 and sonuc["notes"], sonuc
    assert cr.score_hook("3 dakikada diş ipi nasıl doğru kullanılır?") == guclu, "puanlama belirlenimci olmalı"


def test_score_carousel_rubric():
    iyi = cr.score_carousel(IYI_KARUSEL)
    zayif = cr.score_carousel(ZAYIF_KARUSEL)
    assert iyi["score"] >= 70 and iyi["level"] == "iyi", iyi
    assert zayif["score"] <= 55 and zayif["level"] in ("orta", "geliştir"), zayif
    assert any("tekrar" in note for note in zayif["notes"]), zayif["notes"]
    bos = cr.score_carousel([])
    assert bos["score"] == 0 and bos["level"] == "geliştir"


def test_reel_shot_plan_rules():
    hook = cr.reel_shot_plan("diş ipi kullanımı", "0-3 sn", "Yanlışı soruyla aç.")
    deger = cr.reel_shot_plan("diş ipi kullanımı", "3-15 sn", "Makro plan göster.")
    cta = cr.reel_shot_plan("diş ipi kullanımı", "15-25 sn", "Randevu çağrısı yap.")
    anahtarlar = {"plan", "kamera", "hareket", "isik", "overlay", "ses_ritim"}
    for plan in (hook, deger, cta):
        assert set(plan) == anahtarlar and all(str(v).strip() for v in plan.values()), plan
        assert len(plan["overlay"]) <= 40, plan["overlay"]
    assert "yüz" in hook["plan"] and "bakış" in hook["plan"], hook["plan"]
    assert "makro" in deger["plan"] and "loupe" in deger["plan"], deger["plan"]
    assert "resepsiyon" in cta["plan"] and "gülüş" in cta["plan"], cta["plan"]
    varsayilan = cr.reel_shot_plan("konu", "belirsiz", "metin")
    assert set(varsayilan) == anahtarlar and varsayilan["plan"]


def test_audit_output_rubric():
    reels = cr.audit_creative_output("REELS", REELS_ORNEK)
    assert reels["kind"] == "REELS" and reels["max"] == 100 and reels["notes"]
    assert reels["score"] >= 65, reels
    assert set(reels) == {"kind", "score", "max", "notes", "level"}
    shotsuz = {"hooks": REELS_ORNEK["hooks"], "senaryo": [
        {"aralik": "0-3 sn", "metin": "x"}, {"aralik": "3-15 sn", "metin": "y"}, {"aralik": "15-25 sn", "metin": "z"}]}
    assert cr.audit_creative_output("REELS", shotsuz)["score"] < reels["score"]
    fikir = cr.audit_creative_output("IDEA", [{"title": "Diş sağlığı önemlidir."} for _ in range(5)])
    assert fikir["kind"] == "IDEA" and fikir["score"] < 60, fikir
    gorsel = cr.audit_creative_output("IMAGE", {"slides": IYI_KARUSEL, "style": "derin-lacivert"})
    assert gorsel["kind"] == "IMAGE" and 0 <= gorsel["score"] <= 100 and gorsel["notes"]
    assert any("Tasarım sistemi uyumu" in note for note in gorsel["notes"])


def test_safe_rewrite():
    oneri = cr.safe_rewrite_suggestion("Bölgenin en iyi kliniği")
    assert oneri is not None and "en iyi" not in oneri.lower(), oneri
    assert cr.safe_rewrite_suggestion("Dünyanın en güvenilir klinik") is not None
    assert cr.safe_rewrite_suggestion("Düzenli kontrol önemlidir.") is None
    assert cr.safe_rewrite_suggestion("") is None
    assert cr.safe_rewrite_suggestion("Bölgenin en iyi kliniği") == oneri, "öneri belirlenimci olmalı"


def test_api_mock_integration():
    gorsel = client.post("/api/foto-fikir/generate-image", json={
        "topic": "İmplant sonrası bakım", "style_id": "derin-lacivert",
        "slides": [{"headline": "İlk 24 saat", "body": "Dik durun."}, {"headline": "İlk hafta", "body": "Yumuşak beslenin."}],
    })
    assert gorsel.status_code == 200, gorsel.text
    data = gorsel.json()
    assert data["mock"] is True and len(data["images"]) == 2 and data["quota"]["used"] == 2
    denetim = data["creative_audit"]
    assert denetim["kind"] == "IMAGE" and 0 <= denetim["score"] <= 100 and denetim["level"] in ("iyi", "orta", "geliştir")
    with Session(engine) as session:
        job = session.get(FotoFikirJob, data["job_id"])
    is_kaydi = json.loads(job.payload)
    assert is_kaydi["creative_audit"]["kind"] == "IMAGE" and is_kaydi["image_paths"], job.payload[:200]
    reels = client.post("/api/foto-fikir/reels", json={"topic": "diş ipi kullanımı"}).json()
    assert reels["senaryo"] and all(isinstance(row["shot"], dict) and row["shot"]["overlay"] for row in reels["senaryo"])
    assert reels["creative_audit"]["kind"] == "REELS" and 0 <= reels["creative_audit"]["score"] <= 100
    fikirler = client.post("/api/foto-fikir/ideas", json={"topic_hint": "implant bakımı"}).json()
    assert len(fikirler["ideas"]) == 5 and fikirler["creative_audit"]["kind"] == "IDEA"
    mevzuat = client.post("/api/foto-fikir/mevzuat-check", json={"texts": [
        "Bölgenin en iyi kliniğidir.", "Tedavi ömür boyu garanti.", "Düzenli kontrol önemlidir.",
    ]}).json()
    satirlar = mevzuat["results"]
    assert [row["level"] for row in satirlar] == ["DIKKAT", "KALDIR", "OK"], satirlar
    assert satirlar[0]["creative_alternative"] and "en iyi" not in satirlar[0]["creative_alternative"]
    assert satirlar[1]["creative_alternative"] is None
    assert "creative_alternative" not in satirlar[2]
    assert mevzuat["disclaimer"] == FOTO_FIKIR_MEVZUAT_DISCLAIMER


check("tasarım sistemi 15 stili kapsıyor", test_design_system_covers_all_styles)
check("yönetmen prompt kuralları", test_creative_prompt_rules)
check("kanca puanlama rubriği", test_score_hook_rubric)
check("karusel puanlama rubriği", test_score_carousel_rubric)
check("reel çekim planı kuralları", test_reel_shot_plan_rules)
check("çıktı denetim rubriği", test_audit_output_rubric)
check("mevzuat uyumlu yeniden yazım", test_safe_rewrite)
check("api entegrasyonu (mock)", test_api_mock_integration)

iyi = cr.score_carousel(IYI_KARUSEL)
zayif = cr.score_carousel(ZAYIF_KARUSEL)
reels = cr.audit_creative_output("REELS", REELS_ORNEK)
print()
print("SKOR KARTI (rubrik: /100)")
print(f"SKOR KARTI — örnek iyi karusel: {iyi['score']}/100 ({iyi['level']}); kanca={cr.score_hook(IYI_KARUSEL[0]['headline'])['score']}, CTA={cr.score_hook(IYI_KARUSEL[-1]['headline'] + ' ' + IYI_KARUSEL[-1]['body'])['score']}")
print(f"SKOR KARTI — örnek zayıf karusel: {zayif['score']}/100 ({zayif['level']}; zayıf kanca={cr.score_hook(ZAYIF_KARUSEL[0]['headline'])['score']})")
print(f"SKOR KARTI — örnek reels: {reels['score']}/{reels['max']} ({reels['level']}); kanca ortalaması={sum(cr.score_hook(h)['score'] for h in REELS_ORNEK['hooks']) // len(REELS_ORNEK['hooks'])}, pacing=+25, plan=+15")
print()
if failures:
    print("CREATIVE FAIL:", len(failures), "denetim")
    for name, exc in failures:
        print("-", name, "->", exc)
    sys.exit(1)
print("CREATIVE OK: 8 denetim geçti")
