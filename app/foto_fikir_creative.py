"""Foto Fikir yaratıcı yönetmen motoru (reklam + video tasarım beyni).

Bu modül bağımsızdır: yalnızca standart kütüphaneyi kullanır, foto_fikir_api
içe aktarmaz (döngü riski yok). Tüm çıktılar kural tabanlı ve belirlenimcidir;
rastgelelik yoktur. Üç görevi vardır:
1) 15 stil için tasarım sistemi ve yönetmen seviyesinde görsel prompt'u,
2) Reels çekim planı satırı ve kanca/karusel puanlama rubriği,
3) Üretilen çıktının denetimi ve mevzuat uyumlu yaratıcı öneri.

Metin kuralları: kullanıcıya dön tüm metinler Türkçedir; emoji kullanılmaz.
"""
from __future__ import annotations

import re
from typing import List, Optional

# ---------------------------------------------------------------------------
# Tasarım sistemi: 15 stil, foto_fikir_api.FF_STYLES kimlikleriyle birebir
# ---------------------------------------------------------------------------

FF_DESIGN_SYSTEM = {
    # Her satır: stil kimliği (foto_fikir_api.FF_STYLES ile birebir) -> spec.
    "sade-klinik": {"ad": "Sade Klinik", "palet": {"zemin": "#FFFFFF", "vurgu": "#0F5E9C", "metin": "#1F2933"}, "tipografi": "koyu gri sans-serif başlık, ince açık gövde, geniş beyaz alan", "kompozisyon": "üçler kuralı", "isik": "softbox", "doku": "pürüzsüz beyaz yüzey", "kullanim": "rutin bakım kartları, hızlı bilgilendirme, teknik adımlar"},
    "derin-lacivert": {"ad": "Derin Lacivert", "palet": {"zemin": "#0B2340", "vurgu": "#E9A84C", "metin": "#F4F7FB"}, "tipografi": "beyaz yüksek kontrastlı başlık, buz mavisi gövde", "kompozisyon": "merkez simetri", "isik": "stüdyo üç nokta", "doku": "mat lacivert degrade", "kullanim": "kurumsal güven, implant ve tedavi anlatımları, klinik tanıtımı"},
    "nane-esintisi": {"ad": "Nane Esintisi", "palet": {"zemin": "#F2FBF7", "vurgu": "#1E8E6E", "metin": "#1F3B32"}, "tipografi": "yeşil-gri orta ağırlıkta başlık, açık gövde", "kompozisyon": "üçler kuralı", "isik": "softbox", "doku": "temiz mat zemin", "kullanim": "ferah bakım önerileri, hijyen rutinleri, çocuk dostu içerik"},
    "yumusak-gul": {"ad": "Yumuşak Gül", "palet": {"zemin": "#FBEEF1", "vurgu": "#C05C7E", "metin": "#4A2B35"}, "tipografi": "sıcak bordo başlık, yumuşak gövde", "kompozisyon": "altın oran", "isik": "golden hour", "doku": "pastel granül", "kullanim": "gülüş tasarımı ve estetik, hasta karşılama, samimi seri"},
    "mum-isigi": {"ad": "Mum Işığı", "palet": {"zemin": "#FFF6E8", "vurgu": "#B4762A", "metin": "#43301C"}, "tipografi": "amber başlık, krem gövde", "kompozisyon": "çerçeve-içi çerçeve", "isik": "golden hour", "doku": "sıcak kâğıt dokusu", "kullanim": "hasta anlatıları, klinik kültürü, samimi tanıtımlar"},
    "mermer-doku": {"ad": "Mermer Doku", "palet": {"zemin": "#F4F2EE", "vurgu": "#A98A4E", "metin": "#2E2A24"}, "tipografi": "ince sans-serif başlık, altın ayraç çizgiler", "kompozisyon": "çerçeve-içi çerçeve", "isik": "softbox", "doku": "açık mermer", "kullanim": "premium hizmet kartları, portföy serisi, lansman kareleri"},
    "iki-renk": {"ad": "İki Renk", "palet": {"zemin": "#F5F7FA", "vurgu": "#0B2340", "metin": "#101828"}, "tipografi": "kalın blok başlık, tek ağırlıkta gövde", "kompozisyon": "merkez simetri", "isik": "yüksek kontrast stüdyo", "doku": "düz renk blokları", "kullanim": "güçlü açıklamalar, karşılaştırma kartları, uyarı serileri"},
    "yumusak-golge": {"ad": "Yumuşak Gölge", "palet": {"zemin": "#EFEFF3", "vurgu": "#3E6BD6", "metin": "#26303B"}, "tipografi": "orta kalın mavi başlık, nötr gövde", "kompozisyon": "katmanlı kart ızgarası", "isik": "softbox", "doku": "yumuşak gölgeli kartlar", "kullanim": "adım adım rehberler, hizmet kartları, eğitim serileri"},
    "su-cizgisi": {"ad": "Su Çizgisi", "palet": {"zemin": "#F0F7FC", "vurgu": "#2A7FB8", "metin": "#17324A"}, "tipografi": "koyu mavi başlık, akışkan gövde", "kompozisyon": "altın oran", "isik": "softbox", "doku": "ince dalgalı çizgiler", "kullanim": "ağız bakım akışları, fırçalama temaları, yaz içerikleri"},
    "kagit-kirma": {"ad": "Kağıt Katmanı", "palet": {"zemin": "#F7F3EC", "vurgu": "#B96A3C", "metin": "#3B2F24"}, "tipografi": "sıcak kahve başlık, el yazısı vurgu", "kompozisyon": "çerçeve-içi çerçeve", "isik": "golden hour", "doku": "kâğıt katmanları", "kullanim": "checklist kartları, hatırlatma serileri, el yapımı hissi"},
    "gece-neon": {"ad": "Gece Neon", "palet": {"zemin": "#0A0F1E", "vurgu": "#3BE8D8", "metin": "#EAF6F5"}, "tipografi": "nötr beyaz başlık, neon kontur vurgu", "kompozisyon": "merkez simetri", "isik": "neon kontur, kenarlarda vinyet", "doku": "gece koyusu zemin", "kullanim": "genç hedef kitle, gece bakım rutini, dikkat çeken duyuru kartları"},
    "isik-odagi": {"ad": "Işık Odağı", "palet": {"zemin": "#17181C", "vurgu": "#D9A441", "metin": "#ECE7DD"}, "tipografi": "krem başlık, geniş harf aralığı", "kompozisyon": "merkez simetri", "isik": "merkez spot, kenarlarda vinyet", "doku": "koyu düz zemin", "kullanim": "tek mesajlı açıklamalar, tanıtım kareleri, öne çıkan bilgi kartları"},
    "toprak-ton": {"ad": "Toprak Tonları", "palet": {"zemin": "#F3E9DC", "vurgu": "#9A5B33", "metin": "#3D2C1E"}, "tipografi": "kil tonlu başlık, doğal gövde", "kompozisyon": "üçler kuralı", "isik": "golden hour", "doku": "kum ve kil dokusu", "kullanim": "doğal bakım içerikleri, aile ve yaşam kartları, mevsim serileri"},
    "cam-saydam": {"ad": "Cam Saydam", "palet": {"zemin": "#EAF2F6", "vurgu": "#4FA3C7", "metin": "#1C3340"}, "tipografi": "koyu petrol başlık, saydam katmanlar", "kompozisyon": "çerçeve-içi çerçeve", "isik": "softbox", "doku": "buğulu cam", "kullanim": "dijital tarayıcı temaları, klinik tanıtımı, sakin bilgilendirme"},
    "defter-cizgi": {"ad": "Defter Çizgisi", "palet": {"zemin": "#FBF8F1", "vurgu": "#2C6E8F", "metin": "#2B2A26"}, "tipografi": "el yazısı başlık vurgusu, kalem gövde", "kompozisyon": "sütun çizgisi hizası, üçler kuralı", "isik": "softbox", "doku": "çizgili defter", "kullanim": "eğitim kartları, not alma temaları, soru-cevap serileri"},
}

_FF_DEFAULT_SPEC = FF_DESIGN_SYSTEM["sade-klinik"]


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _fold(text: str) -> str:
    """Anahtar eşleşmesi için Türkçe duyarsız küçük harf biçimi."""
    folded = (text or "").replace("İ", "i").replace("I", "i").lower()
    return folded.replace("i\u0307", "i")


def _clip(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clip_word(value, limit: int, suffix: str = " …") -> str:
    """Kelime sınırında keser; uzunsa kelime boşluğunda kısaltıp son ek ekler."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + suffix


def _resolve_style(value) -> Optional[dict]:
    """Stil kimliği, stil adı veya stil sözlüğünden tasarım sistemi kaydını bulur."""
    if isinstance(value, dict):
        value = value.get("id") or value.get("name")
    folded = _fold(str(value or ""))
    if not folded:
        return None
    for style_id, spec in FF_DESIGN_SYSTEM.items():
        if folded in (_fold(style_id), _fold(spec.get("ad", style_id))):
            return spec
    return None


def _level(score: int) -> str:
    if score >= 70:
        return "iyi"
    if score >= 45:
        return "orta"
    return "geliştir"


# ---------------------------------------------------------------------------
# Yönetmen seviyesinde görsel prompt'u
# ---------------------------------------------------------------------------

def creative_prompt_for_slide(topic, style_id_or_name, slide, brand_name=None) -> str:
    """Slayt için yönetmen seviyesinde Türkçe görsel prompt'u kurar.

    Tasarım sisteminden palet (hex), kompozisyon, ışık ve doku taşınır;
    tıbbi doğruluk koruması, görselde yazı yasağı, negatif liste ve kalite
    anahtar sözcükleri eklenir. Belirlenimcidir.
    """
    spec = _resolve_style(style_id_or_name) or _FF_DEFAULT_SPEC
    palet = spec["palet"]
    slide = slide if isinstance(slide, dict) else {}
    topic_text = _clip(topic, 120) or "ağız ve diş sağlığı"
    headline = _clip(slide.get("headline") or topic, 120)
    body = _clip(slide.get("body"), 220)
    parts = [
        "Diş hekimliği reklam stüdyosu için profesyonel bir sosyal medya karusel görseli kompoze et.",
        (
            f"Stil: {spec['ad']}. Renk paleti: zemin {palet['zemin']}, "
            f"vurgu {palet['vurgu']}, metin alanı {palet['metin']}; paleti kaydırmadan kullan."
        ),
        (
            f"Kompozisyon: {spec['kompozisyon']}; karede tek odak, ana öge odakta, "
            "kenarlarda nefes payı, ön-orta-arka katmanlarla derinlik."
        ),
        (
            f"Işık kurulumu: {spec['isik']}. Doku: {spec['doku']}. "
            f"Tipografi alanı: {spec['tipografi']}; bu alanı boş bırak, yazı ayrı katmanda eklenecek."
        ),
        f"Konu: {topic_text}. Slayt başlığı: {headline}.",
    ]
    if body:
        parts.append(f"Slayt gövdesi: {body}.")
    if brand_name:
        parts.append(
            f"Marka kimliği: {_clip(brand_name, 60)}; sade ve kurumsal ton kullan, "
            "marka adını görsel üzerine yazma."
        )
    parts.append(
        "Tıbbi doğruluk: diş ve ağız anatomisi doğru ve gerçekçi olsun; deformasyon, "
        "aşırı abartı veya yanlış ağız yapısı olmasın."
    )
    parts.append(
        "KESİN KURAL: görselde yazı olmasın; hiçbir harf, kelime, sayı veya altyazı çizilmesin."
    )
    parts.append(
        "Negatif liste: metin, filigran, logo, imza, bozuk el, fazla parmak, "
        "düşük çözünürlük, bulanıklık, sert aşırı gölge."
    )
    parts.append(
        "Kalite: yüksek çözünürlük, dengeli renk, temiz arka plan, dergi kalitesinde "
        "profesyonel reklam estetiği."
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Reels yönetmen planı
# ---------------------------------------------------------------------------

_FF_REEL_TEMPLATES = {
    "hook": {
        "plan": "Yakın yüz planı: direkt bakış, ilk 3 saniyede '{konu}' kancasını sor; göz teması kesilmesin.",
        "kamera": "85 mm hissi, göz hizası, yüzü dolduran yakın plan",
        "hareket": "slow push-in",
        "isik": "yüzde softbox, arka planda hafif vinyet",
        "overlay": "{konu}: bu hatayı bırakın",
        "ses_ritim": "sessiz açılış, ilk saniyede tek vuruş müzik",
    },
    "value": {
        "plan": "Değer adımları: makro planda ağız içi uygulama; loupe ve el çatalı kadraja girsin; her adım tek cümle.",
        "kamera": "makro ve loupe yakın plan, 50 mm",
        "hareket": "adım geçişlerinde yavaş pan",
        "isik": "ağız içinde ring ışığı, dolguda softbox",
        "overlay": "{konu}: adım adım",
        "ses_ritim": "anlatım temposu; adım başına kısa nefes payı",
    },
    "cta": {
        "plan": "Kapanış: resepsiyonda doğal gülüş planıyla randevu çağrısı; yüz tam kadrajda, gülüş önde.",
        "kamera": "orta plan, göğüs üstü kadraj",
        "hareket": "sabit üçlü çekim",
        "isik": "resepsiyonda golden hour ton, yumuşak pencere ışığı",
        "overlay": "Kaydet ve randevunu planla",
        "ses_ritim": "kapanışta tek vuruş müzik, sonra sessizlik",
    },
}


def _reel_bucket(aralik) -> str:
    """Aralık metnini saniye başlangıcına göre üç yön planına ayırır.

    0-3 sn kanca, 3-15 sn değer adımları, 15-25 sn kapanış çağrısı.
    """
    match = re.search(r"(\d+)\s*-\s*(\d+)", str(aralik or ""))
    start = int(match.group(1)) if match else 8
    if start < 3:
        return "hook"
    if start < 15:
        return "value"
    return "cta"


def reel_shot_plan(topic, aralik, metin) -> dict:
    """Bir senaryo satırı için kural tabanlı yönetmen çekim planı döndürür.

    Anahtarlar: plan, kamera, hareket, isik, overlay, ses_ritim. Overlay önerisi
    40 karakteri aşmaz; tüm değerler belirlenimcidir.
    """
    bucket = _reel_bucket(aralik)
    template = _FF_REEL_TEMPLATES[bucket]
    konu = _clip_word(topic, 24) or "bu konu"
    return {
        "plan": template["plan"].format(konu=konu),
        "kamera": template["kamera"],
        "hareket": template["hareket"],
        "isik": template["isik"],
        "overlay": _clip_word(template["overlay"].format(konu=konu), 40, "…"),
        "ses_ritim": template["ses_ritim"],
    }


# ---------------------------------------------------------------------------
# Kanca puanlama
# ---------------------------------------------------------------------------

_FF_BENEFIT_WORDS = (
    "dakika", "kolay", "yanlış", "doğru", "hata", "pratik",
    "adım", "saniye", "ipucu", "rutin", "koruma",
)
_FF_CURIOSITY_WORDS = ("çoğu kişi", "aslında", "hâlâ", "en çok")
_FF_QUESTION_WORDS = ("nasıl", "neden", "ne zaman", "hangi", "nedenle")


def score_hook(text) -> dict:
    """Kanca cümlesini 0-100 arası puanlar; kriter notlarını döndürür."""
    text = str(text or "").strip()
    folded = _fold(text)
    notes: List[str] = []
    score = 0
    if re.search(r"\d", text):
        score += 20
        notes.append("Sayı içeriyor: somut vaat ilk bakışta okunur (+20).")
    else:
        notes.append("Sayı yok; bir rakam veya adım sayısı kanca gücünü artırır (+0).")
    if "?" in text or any(word in folded for word in _FF_QUESTION_WORDS):
        score += 20
        notes.append("Soru biçimi var: okuyucuyu cevap aramaya itiyor (+20).")
    else:
        notes.append("Soru biçimi yok; nasıl veya neden kalıbı denenebilir (+0).")
    benefits = [word for word in _FF_BENEFIT_WORDS if word in folded]
    if benefits:
        score += 20
        notes.append("Fayda sözcüğü var: " + ", ".join(benefits[:3]) + " (+20).")
    else:
        notes.append("Fayda sözcüğü yok; dakika, kolay, yanlış, doğru gibi kelimeler eklenebilir (+0).")
    curiosity = [word for word in _FF_CURIOSITY_WORDS if word in folded]
    if curiosity:
        score += 15
        notes.append("Merak boşluğu var: " + ", ".join(curiosity[:2]) + " (+15).")
    else:
        notes.append("Merak boşluğu yok; 'çoğu kişi' veya 'aslında' kalıbı eklenebilir (+0).")
    if len(text) <= 60:
        score += 15
        notes.append(f"Uzunluk {len(text)} karakter; tek bakışta okunuyor (+15).")
    else:
        notes.append(f"Uzunluk {len(text)} karakter; 60 karakterin altı ideal (+0).")
    words = len(text.split())
    if words <= 12:
        score += 10
        notes.append(f"Kelime sayısı {words}; akıcı (+10).")
    else:
        notes.append(f"Kelime sayısı {words}; 12 kelimenin altı ideal (+0).")
    return {"score": max(0, min(100, score)), "notes": notes}


# ---------------------------------------------------------------------------
# Karusel puanlama
# ---------------------------------------------------------------------------

_FF_CTA_WORDS = ("kaydet", "paylaş", "takip", "randevu", "soru")
_FF_MAX_SCORE = 100


def score_carousel(slides) -> dict:
    """Karusel slaytlarını 0-100 arası puanlar; kriter notlarını döndürür."""
    rows = [row for row in (slides or []) if isinstance(row, dict)]
    notes: List[str] = []
    if not rows:
        return {"score": 0, "notes": ["Slayt yok; karusel puanlanamadı."], "level": "geliştir"}
    score = 0
    hook = score_hook(str(rows[0].get("headline") or ""))
    hook_part = hook["score"] // 2
    score += hook_part
    notes.append(f"İlk slayt kanca puanı {hook['score']}, yarı ağırlıkla {hook_part} puan.")
    last_text = str(rows[-1].get("headline") or "") + " " + str(rows[-1].get("body") or "")
    last_folded = _fold(last_text)
    if any(word in last_folded for word in _FF_CTA_WORDS):
        score += 25
        notes.append("Son slaytta eylem çağrısı var (+25).")
    else:
        notes.append("Son slaytta kaydet, paylaş, takip, randevu veya soru çağrısı yok (+0).")
    headlines = [str(row.get("headline") or "").strip() for row in rows]
    if len(set(headlines)) < len(headlines):
        score -= 15
        notes.append("Başlık tekrarı var; çeşitlilik puanı düşürüldü (-15).")
    else:
        notes.append("Başlıklar çeşitli.")
    long_headlines = [headline for headline in headlines if len(headline) > 60]
    if long_headlines:
        penalty = min(15, 5 * len(long_headlines))
        score -= penalty
        notes.append(f"{len(long_headlines)} başlık 60 karakterden uzun (-{penalty}).")
    else:
        score += 10
        notes.append("Tüm başlıklar 60 karakterin altında, tek bakışta okunur (+10).")
    dense = [row for row in rows if len(str(row.get("body") or "")) > 200]
    if dense:
        penalty = min(15, 5 * len(dense))
        score -= penalty
        notes.append(f"{len(dense)} slaytın gövdesi 200 karakterden uzun; tek fikir kuralı zayıflıyor (-{penalty}).")
    else:
        notes.append("Her slaytta tek fikir: gövde metinleri yoğun değil.")
    step_folded = " ".join(_fold(str(row.get("headline") or "")) for row in rows)
    has_steps = any(re.search(r"\d", str(row.get("headline") or "")) for row in rows) or "adım" in step_folded
    if has_steps:
        score += 10
        notes.append("Numaralı veya adımlı yapı var (+10).")
    else:
        notes.append("Numaralı veya adımlı yapı yok (+0).")
    score = max(0, min(_FF_MAX_SCORE, score))
    return {"score": score, "notes": notes, "level": _level(score)}


# ---------------------------------------------------------------------------
# Çıktı denetimi (görsel, reels, fikir)
# ---------------------------------------------------------------------------

def _pacing_ok(senaryo) -> bool:
    """Aralıklar sıralı ve toplam süre 60 saniyeyi aşmıyor mu?"""
    spans = []
    for row in senaryo or []:
        raw = row.get("aralik") if isinstance(row, dict) else row
        match = re.search(r"(\d+)\s*-\s*(\d+)", str(raw or ""))
        if not match:
            return False
        spans.append((int(match.group(1)), int(match.group(2))))
    if not spans:
        return False
    ordered = all(spans[i][0] < spans[i + 1][0] for i in range(len(spans) - 1))
    return ordered and max(end for _, end in spans) <= 60


def _shots_ok(senaryo) -> bool:
    rows = [row for row in (senaryo or []) if isinstance(row, dict)]
    return bool(rows) and all(isinstance(row.get("shot"), dict) and row.get("shot") for row in rows)


def audit_creative_output(kind, data) -> dict:
    """Üretilen çıktıyı rubrikle denetler; kind IMAGE, REELS veya IDEA olabilir."""
    result = {"kind": str(kind), "score": 0, "max": _FF_MAX_SCORE, "notes": [], "level": "geliştir"}
    notes: List[str] = result["notes"]
    if kind == "IMAGE":
        slides = data.get("slides") or [] if isinstance(data, dict) else []
        carousel = score_carousel(slides)
        result["score"] = carousel["score"]
        notes.extend(carousel["notes"])
        style_ref = data.get("style") or data.get("style_id") if isinstance(data, dict) else None
        spec = _resolve_style(style_ref) if style_ref else None
        if spec is not None:
            palet = spec["palet"]
            notes.append(
                f"Tasarım sistemi uyumu: {spec['ad']} stili zemin {palet['zemin']} / vurgu {palet['vurgu']} / "
                f"metin {palet['metin']} paleti ve {spec['isik']} kurulumuyla prompt'a işlendi."
            )
        elif style_ref:
            notes.append("Stil tasarım sisteminde kayıtlı değil; palet varsayılan sade klinik ile eşlendi.")
        else:
            notes.append("Stil seçilmedi; yönetmen paleti varsayılan sade klinik ile kuruldu.")
        result["level"] = _level(result["score"])
        return result
    if kind == "REELS":
        if not isinstance(data, dict):
            notes.append("Reels verisi okunamadı.")
            return result
        hooks = [str(item) for item in (data.get("hooks") or []) if str(item or "").strip()]
        if hooks:
            scores = [score_hook(hook)["score"] for hook in hooks]
            hook_part = round(sum(scores) / len(scores) / 2)
            result["score"] += hook_part
            notes.append(f"{len(hooks)} kanca ortalaması {sum(scores) // len(scores)}, yarı ağırlıkla {hook_part} puan.")
        else:
            notes.append("Kanca satırı yok; ilk 3 saniye kancası puanlanamadı (+0).")
        senaryo = data.get("senaryo") or []
        if _pacing_ok(senaryo):
            result["score"] += 25
            notes.append("Pacing uygun: aralıklar sıralı ve toplam süre 60 saniyeyi aşmıyor (+25).")
        else:
            notes.append("Pacing zayıf: aralıklar sıralı değil veya toplam süre 60 saniyeyi aşıyor (+0).")
        if _shots_ok(senaryo):
            result["score"] += 15
            notes.append("Her senaryo satırında yönetmen çekim planı var (+15).")
        else:
            notes.append("Senaryo satırlarına yönetmen çekim planı (shot) eklenmeli; reel_shot_plan kullanın (+0).")
        result["score"] = max(0, min(_FF_MAX_SCORE, result["score"]))
        result["level"] = _level(result["score"])
        return result
    if kind == "IDEA":
        items = data if isinstance(data, list) else (data.get("ideas") or [] if isinstance(data, dict) else [])
        titles = []
        for item in items:
            if isinstance(item, dict):
                titles.append(str(item.get("title") or "").strip())
            else:
                titles.append(str(item or "").strip())
        titles = [title for title in titles if title]
        if not titles:
            notes.append("Fikir başlığı yok; kanca rubriği uygulanamadı.")
            return result
        scores = [score_hook(title)["score"] for title in titles]
        result["score"] = max(0, min(_FF_MAX_SCORE, round(sum(scores) / len(scores))))
        best_index = max(range(len(titles)), key=lambda i: scores[i])
        worst_index = min(range(len(titles)), key=lambda i: scores[i])
        notes.append(f"{len(titles)} başlığın kanca ortalaması {result['score']} puan.")
        notes.append(f"En güçlü kanca: '{_clip_word(titles[best_index], 60)}' ({scores[best_index]} puan).")
        notes.append(f"En zayıf kanca: '{_clip_word(titles[worst_index], 60)}' ({scores[worst_index]} puan).")
        result["level"] = _level(result["score"])
        return result
    notes.append("Bilinmeyen çıktı türü; rubrik uygulanmadı.")
    return result


# ---------------------------------------------------------------------------
# Mevzuat uyumlu yaratıcı öneri
# ---------------------------------------------------------------------------

_FF_SUPERLATIVE_ALTERNATIVES = (
    ("en iyi", "özenli"),
    ("en güvenilir", "bilgi veren"),
    ("en başarılı", "deneyimli"),
    ("en hızlı", "özenli"),
    ("dünyanın en", "deneyimli"),
    ("türkiyenin en", "deneyimli"),
    ("bölgenin en", "deneyimli"),
    ("bir numara", "özenli"),
    ("rakipsiz", "bilgi veren"),
)


def safe_rewrite_suggestion(text) -> Optional[str]:
    """Üstünlük iddiası içeren metne mevzuat uyumlu yaratıcı alternatif önerir.

    Kural tabanlı ve belirlenimcidir; iddia cümlesi öneriye taşınmaz.
    Eşleşen kural yoksa None döndürür.
    """
    folded = _fold(str(text or ""))
    if not folded:
        return None
    for phrase, alternative in _FF_SUPERLATIVE_ALTERNATIVES:
        if phrase in folded:
            return (
                f'Üstünlük iddiası yerine "{alternative}" gibi ölçülebilir bir niteleme kullanın; '
                "hizmet süresi, eğitim veya hasta bilgilendirme alışkanlığı gibi somut bir ayrıntıya bağlayın."
            )
    return None


# ---------------------------------------------------------------------------
# Yönetmen kimliği (metin üretim istemlerine eklenen sabit persona)
# ---------------------------------------------------------------------------

CREATIVE_DIRECTOR_BRIEF = """Sen diş hekimliği iletişiminde ödül kazanmış bir reklam yönetmeni, sanat yönetmeni ve video yönetmenisin.
Görevin: hastaya güven veren, tıbbi olarak doğru ve mevzuata uygun reklam görselleri ve kısa videolar üretmek.
Kompozisyon: her karede tek odak; üçler kuralı, merkez simetri, altın oran veya çerçeve-içi çerçeve kurallarından birini seç.
Renk disiplini: stil paletindeki zemin, vurgu ve metin renklerini kaydırmadan kullan; erişilebilir kontrastı bozma.
Işık: yüz ve ağız içi çekimlerde softbox veya stüdyo üç nokta kurulumu; sıcak ton yalnızca resepsiyon ve kapanış sahnelerinde.
Kanca: ilk 3 saniyede sayı, soru veya fayda sözüyle merak boşluğu aç; "Diş sağlığı önemlidir" gibi genel cümleler kanca değildir.
Gövde: her slaytta tek fikir; adımlar numaralı, başlıklar 12 kelimenin altında, cümleler kısa ve gözlem diliyle yazılır.
Kapanış: son karede tek eylem çağrısı; kaydet, paylaş, takip veya randevu. Birden fazla çağrı kareyi dağıtır.
Video ritmi: 0-3 sn yakın yüz kancası, 3-15 sn makro değer adımları, 15-25 sn resepsiyon çağrısı; toplam süre 60 saniyeyi aşmasın.
Ekranda yazı: görsellerde yazı olmasın; yazıyı ayrı katmanda, stil tipografisiyle ve 40 karakteri aşmayan önerilerle koy.
Mevzuat: garanti, üstünlük iddiası, kampanya dili ve öncesi-sonrası karşılaştırması kullanma; özenli, bilgi veren, deneyimli gibi ölçülebilir nitelemeler seç.
Tıbbi doğruluk: anatomi doğru, deform yok; korku dili yerine gözlem dili kullan.
Denetim sırası: önce kanca, sonra kompozisyon, sonra mevzuat; rubrik puanı 45'in altındaysa çıktıyı yeniden kur."""


# ---------------------------------------------------------------------------
# Anlatı yayı: slayt başına görev (rol)
# ---------------------------------------------------------------------------

_FF_ARC_MIDDLE = ("Değer", "Kanıt", "Sahne")


def story_arc_roles(count) -> List[str]:
    """Slayt sayısına göre belirlenimci anlatı yayı döndürür (1..8).

    Kanca -> Değer -> Kanıt -> Sahne -> Kapanış/CTA örüntüsü slayt sayısına
    uyarlanır; 6-8 slaytta orta roller tekrar eder ve sıra numarası alır
    ("Değer 2" gibi). Son görev her zaman kapanış çağrısıdır.
    """
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(8, n))
    if n == 1:
        return ["Kanca + Kapanış/CTA"]
    roles = ["Kanca"]
    repeat: dict = {}
    for index in range(n - 2):
        role = _FF_ARC_MIDDLE[index % len(_FF_ARC_MIDDLE)]
        repeat[role] = repeat.get(role, 0) + 1
        roles.append(role if repeat[role] == 1 else f"{role} {repeat[role]}")
    roles.append("Kapanış/CTA")
    return roles


# ---------------------------------------------------------------------------
# Konu -> stil önerisi (deterministik)
# ---------------------------------------------------------------------------

_FF_STYLE_RULES = (
    (("implant", "protez", "köprü", "kurumsal", "klinik tanıtım"), "derin-lacivert"),
    (("beyazlatma", "whitening", "estetik", "gülüş", "gülümseme", "lamine"), "yumusak-gul"),
    (("çocuk", "süt dişi", "bebek", "okul", "aile"), "nane-esintisi"),
    (("fırçalama", "diş ipi", "ağız bakımı", "hijyen", "rutin"), "su-cizgisi"),
    (("kanal", "ağrı", "hassasiyet", "acil", "uyarı", "karşılaştırma"), "iki-renk"),
    (("portföy", "lansman", "premium", "zirkonyum", "hizmet kartları"), "mermer-doku"),
    (("gece", "etkinlik", "duyuru", "genç"), "gece-neon"),
    (("checklist", "hatırlatma", "not", "soru-cevap"), "defter-cizgi"),
    (("doğal", "yaşam", "mevsim", "beslenme"), "toprak-ton"),
    (("eğitim", "bilgilendirme", "adım adım"), "sade-klinik"),
)


def recommend_style(topic) -> dict:
    """Konuya göre belirlenimci stil önerisi; {style_id, reason} döndürür.

    Eşleşme Türkçe duyarsız katlama ile tasarım sisteminin 'kullanim' alanları
    üzerinden kurulur; eşleşme yoksa sade klinik stili önerilir. Aynı konu
    her zaman aynı sonucu verir.
    """
    folded = _fold(str(topic or ""))
    for keywords, style_id in _FF_STYLE_RULES:
        for keyword in keywords:
            if _fold(keyword) and _fold(keyword) in folded:
                spec = FF_DESIGN_SYSTEM[style_id]
                return {
                    "style_id": style_id,
                    "reason": f"'{keyword}' sinyali bu stili öneriyor; kullanım alanı: {spec['kullanim']}.",
                }
    spec = FF_DESIGN_SYSTEM["sade-klinik"]
    return {
        "style_id": "sade-klinik",
        "reason": f"Konuya özgü eşleşme bulunamadı; kullanım alanı: {spec['kullanim']}.",
    }


# ---------------------------------------------------------------------------
# Denetim notlarından uygulanabilir öneriler
# ---------------------------------------------------------------------------

def actionable_tips(audit, limit: int = 2) -> List[str]:
    """Denetim notlarından en fazla `limit` uygulanabilir Türkçe öneri seçer.

    Sadece "(+0)" veya "(-" puan etiketi taşıyan notlar uygulanabilir sayılır;
    bilgi amaçlı notlar öneri listesine girmez. Puan iyiyse ve uygulanabilir
    not yoksa boş liste döner.
    """
    if not isinstance(audit, dict) or not isinstance(audit.get("notes"), list):
        return []
    tips = [
        str(note).strip()
        for note in audit["notes"]
        if str(note or "").strip() and ("(+0)" in str(note) or "(-" in str(note))
    ]
    return tips[:max(0, limit)]
