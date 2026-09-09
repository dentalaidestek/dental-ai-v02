from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Iterable

from app.ai_provider import ask_ai
from dental_rag.specialty_router import SPECIALTIES, classify_specialties

try:
    from app.xray_trace import xray_trace_event
except Exception:  # temporary trace may be removed later
    def xray_trace_event(*args, **kwargs):
        return None


_ALLOWED_IMAGE_TYPES = {
    "RADIOGRAPH",
    "PERIAPICAL",
    "BITEWING",
    "PANORAMIC",
    "CBCT",
    "INTRAORAL",
    "EXTRAORAL",
    "CLINICAL_PHOTO",
    "OTHER",
}

_ALLOWED_SIGNALS = {
    "CARIES_OR_RESTORATIVE",
    "PAIN",
    "SPONTANEOUS_OR_NIGHT_PAIN",
    "LINGERING_THERMAL_RESPONSE",
    "PULP_TEST_ABNORMAL",
    "PULPAL_INVOLVEMENT",
    "APICAL_PATHOSIS",
    "PERIODONTAL_PATHOSIS",
    "ORAL_MUCOSAL_PATHOSIS",
    "SURGICAL_PATHOSIS",
    "ORTHODONTIC_ISSUE",
    "PROSTHODONTIC_RESTORABILITY",
    "PEDIATRIC_DENTITION",
    "OROFACIAL_PAIN",
    "TRAUMA",
    "RESORPTION",
    "CRACK_OR_FRACTURE",
    "IMMATURE_OR_OPEN_APEX",
    "SINUS_RELATION",
    "CBCT_COMPLEXITY",
    "ENDODONTIC_TREATMENT_TECHNIQUE",
    "PERIODONTAL_BONE_LOSS",
    "PERI_IMPLANT_DISEASE",
    "EDENTULISM",
    "IMPLANT_PROSTHODONTICS",
    "TOOTH_WEAR_OR_STRUCTURAL_LOSS",
    "IMPACTED_OR_ERUPTION_ISSUE",
    "THIRD_MOLAR",
    "SUSPICIOUS_ORAL_LESION",
    "BIOPSY_OR_PATHOLOGY_NEED",
    "TMJ_DISORDER",
    "NEUROPATHIC_PAIN_FEATURES",
    "SEDATION_OR_AIRWAY",
    "RADIOGRAPHIC_DECISION",
    "PEDIATRIC_BEHAVIOR",
    "DEVELOPING_OCCLUSION",
    "ORTHODONTIC_RETENTION",
    "CARIES_RISK_PREVENTION",
    "MRONJ_RISK",
    "CANCER_THERAPY_ORAL_COMPLICATION",
    "XEROSTOMIA_OR_HYPOSALIVATION",
    "PUBLIC_HEALTH_PREVENTION",
    "COMPLETE_EDENTULISM",
    "PARTIAL_EDENTULISM",
    "PROSTHESIS_RETENTION_STABILITY",
    "ALVEOLAR_RIDGE_RESORPTION",
    "PRIMARY_TOOTH",
    "NONCAVITATED_CARIES",
    "GINGIVAL_RECESSION",
    "IMPLANT_LOADING_DECISION",
    "OVERDENTURE_CANDIDACY",
}

_SIGNAL_CANONICAL_TEXT = {
    "CARIES_OR_RESTORATIVE": "çürük caries kavite dentin restorasyon derin çürük",
    "PAIN": "ağrı pain",
    "SPONTANEOUS_OR_NIGHT_PAIN": "spontan ağrı gece ağrısı kendiliğinden ağrı",
    "LINGERING_THERMAL_RESPONSE": "soğuk testi uzamış ağrı lingering pain uyaran kaldırıldıktan sonra devam eden ağrı",
    "PULP_TEST_ABNORMAL": "vitalite soğuk testi EPT pulpa testi anormal",
    "PULPAL_INVOLVEMENT": "pulpa ile klinik veya radyografik ilişki pulpal involvement",
    "APICAL_PATHOSIS": "apikal periodontitis periapikal lezyon periapikal patoloji",
    "PERIODONTAL_PATHOSIS": "periodontitis periodontal cep kemik kaybı mobilite",
    "ORAL_MUCOSAL_PATHOSIS": "oral mukozada patolojik lezyon veya anormal doku bulgusu",
    "SURGICAL_PATHOSIS": "ağız diş çene cerrahisi değerlendirmesi gerektirebilecek pozitif bulgu",
    "ORTHODONTIC_ISSUE": "ortodontik problem veya ortodontik tedavi bağlamı",
    "PROSTHODONTIC_RESTORABILITY": "restorabilite ferrule kuron protez diş dokusu kaybı",
    "PEDIATRIC_DENTITION": "pediatrik dentisyon ve çocuk diş hekimliği bağlamı",
    "OROFACIAL_PAIN": "orofasiyal ağrı bağlamı",
    "TRAUMA": "travma avulsiyon lüksasyon dental injury",
    "RESORPTION": "diş kökü rezorpsiyonu root resorption internal external cervical resorption; edentül kret rezorpsiyonu değildir",
    "CRACK_OR_FRACTURE": "çatlak diş cracked tooth vertikal kök kırığı vertical root fracture",
    "IMMATURE_OR_OPEN_APEX": "immatür kök gelişimi ve açık apeks open apex immature root",
    "SINUS_RELATION": "maksiller sinüs odontojenik sinüzit maxillary sinus",
    "CBCT_COMPLEXITY": "CBCT ile üç boyutlu değerlendirme gerektirebilen kompleks anatomi veya komplikasyon",
    "ENDODONTIC_TREATMENT_TECHNIQUE": "kanal tedavisi RCT enstrümantasyon irrigasyon obturasyon",
    "PERIODONTAL_BONE_LOSS": "alveoler destek dokuda klinik olarak anlamlı kemik kaybı",
    "PERI_IMPLANT_DISEASE": "peri-implant mukozitis peri-implantitis implant çevresi kemik kaybı kanama",
    "EDENTULISM": "dişsizlik edentül alan",
    "IMPLANT_PROSTHODONTICS": "implant üstü protetik restorasyon veya mevcut implant-protez ilişkisi; yalnız implant varlığı değildir",
    "TOOTH_WEAR_OR_STRUCTURAL_LOSS": "aşınma tooth wear ileri diş dokusu kaybı restorabilite ferrule oklüzal rehabilitasyon",
    "IMPACTED_OR_ERUPTION_ISSUE": "gömülü diş impaksiyon ektopik sürme sürme bozukluğu gömülü kanin",
    "THIRD_MOLAR": "üçüncü molar yirmi yaş dişi gömülü molar perikoronitis",
    "SUSPICIOUS_ORAL_LESION": "persistan veya klinik olarak şüpheli oral lezyon malignite açısından değerlendirme gereksinimi",
    "BIOPSY_OR_PATHOLOGY_NEED": "biyopsi histopatoloji patoloji örnekleme oral lezyon",
    "TMJ_DISORDER": "TME TMD artralji myalji eklem sesi ağız açmada kısıtlılık",
    "NEUROPATHIC_PAIN_FEATURES": "nöropatik ağrı yanma elektriklenme allodini parestezi sinir hasarı",
    "SEDATION_OR_AIRWAY": "sedasyon veya genel anestezi bağlamında hava yolu ve monitorizasyon gereksinimi",
    "RADIOGRAPHIC_DECISION": "dental görüntüleme seçimi endikasyon gerekçelendirme ve radyografik değerlendirme",
    "PEDIATRIC_BEHAVIOR": "çocuk hastada davranış yönlendirme kooperasyon veya dental kaygı",
    "DEVELOPING_OCCLUSION": "karma dentisyon gelişen oklüzyon çapraz kapanış yer darlığı sürme bozukluğu interceptif",
    "ORTHODONTIC_RETENTION": "ortodontik retansiyon retainer relaps sabit retainer hareketli retainer",
    "CARIES_RISK_PREVENTION": "çürük riski koruyucu yaklaşım önleme ve remineralizasyon",
    "MRONJ_RISK": "MRONJ antirezorptif bisfosfonat denosumab çene osteonekrozu",
    "CANCER_THERAPY_ORAL_COMPLICATION": "kemoterapi radyoterapi oral mukozit kserostomi osteoradyonekroz enfeksiyon",
    "XEROSTOMIA_OR_HYPOSALIVATION": "kserostomi ağız kuruluğu hiposalivasyon tükürük azalması",
    "PUBLIC_HEALTH_PREVENTION": "toplum ağız sağlığı koruyucu program epidemiyoloji ve sağlık politikası bağlamı",
    "COMPLETE_EDENTULISM": "tam dişsizlik complete edentulism complete edentulous total protez",
    "PARTIAL_EDENTULISM": "kısmi dişsizlik parsiyel dişsizlik partial edentulism removable partial denture",
    "PROSTHESIS_RETENTION_STABILITY": "protez retansiyon stabilite tutuculuk yetersizliği hareketli protez fonksiyon sorunu",
    "ALVEOLAR_RIDGE_RESORPTION": "alveoler kret rezorpsiyonu edentül kret atrofisi alveolar ridge resorption",
    "PRIMARY_TOOTH": "süt dişi primary tooth primary molar deciduous tooth",
    "NONCAVITATED_CARIES": "nonkavite çürük noncavitated caries başlangıç lezyonu",
    "GINGIVAL_RECESSION": "diş eti çekilmesi gingival recession mukogingival resesyon",
    "IMPLANT_LOADING_DECISION": "implant yükleme zamanlaması loading timing primer stabilite immediate early conventional loading",
    "OVERDENTURE_CANDIDACY": "tam dişsiz çenede implant tutuculu hareketli overdenture adaylığı ve retansiyon sorunu",
}

_CLINICAL_RAG_ROUTER_SCHEMA = {
    # Keep the wire schema intentionally small. Gemini may reject overly
    # constrained/large responseSchema payloads; business validation stays in
    # Python below and the prompt still lists the exact allowed values.
    "type": "OBJECT",
    "properties": {
        "specialties": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "maxItems": 5,
        },
        "image_types": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "maxItems": 5,
        },
        "signals": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "maxItems": 10,
        },
        "routing_findings": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "maxItems": 6,
        },
    },
    "required": ["specialties", "image_types", "signals", "routing_findings"],
}


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("AI router boş yanıt döndürdü.")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("AI router nesne döndürmedi.")
    return data


def _resolved_image_types(ai_types: list[str], stored_types: list[str]) -> list[str]:
    ai_clean = [t for t in _unique(ai_types) if t in _ALLOWED_IMAGE_TYPES]
    stored_clean = _unique(stored_types)

    ai_specific = [t for t in ai_clean if t != "OTHER"]
    if ai_specific:
        return ai_specific

    stored_specific = [t for t in stored_clean if t and t != "OTHER"]
    if stored_specific:
        return stored_specific

    return ai_clean or stored_clean or ["OTHER"]


def _build_router_prompt(
    *,
    age,
    tooth_number: str,
    clinical_notes: str,
    chief_complaint: str,
    extra_text: str,
    stored_image_types: list[str],
    image_count: int,
) -> str:
    allowed_specialties = ", ".join(SPECIALTIES.keys())
    allowed_signals = ", ".join(sorted(_ALLOWED_SIGNALS))
    return f"""
Sen Dental AI için yalnız RAG yönlendirmesi yapan kısa bir klinik triage katmanısın.
Tanı veya tedavi yazma. Yüklenen dental görüntüleri ve klinik bilgiyi birlikte anlayarak
esas analizde hangi uzmanlık kaynaklarının gerekli olduğunu seç.

KRİTİK KURALLAR:
- Kararı SADECE kelime eşleşmesine göre verme; görüntüyü gerçekten incele ve klinik metinle birlikte değerlendir.
- Hekim notu eksik olabilir. Görüntüdeki anlamlı bir bulgu tek başına ilgili branşı çağırabilir.
- "mobilite yok", "sondlama normal", "palpasyon hassas değil" gibi normal/negatif bulgular
  tek başına o branşı öne çıkarmasın.
- Sadece klinik karar desteğini anlamlı biçimde değiştirecek branşları seç; listeyi doldurmak için ekleme.
- image_types yalnız GERÇEKTEN yüklenen görüntü dosyalarını sınıflandırsın. Klinik notta "radyografide" yazması tek başına yüklenmiş görüntü sayılmaz.
  Yüklenen görüntü yoksa image_types boş dizi olsun. Görüntü varsa mümkün olduğunca spesifik sınıflandır: PERIAPICAL, BITEWING, PANORAMIC,
  CBCT, INTRAORAL, EXTRAORAL, CLINICAL_PHOTO, RADIOGRAPH veya OTHER.
- signals yalnız POZİTİF ve karar değiştiren standart sinyalleri içersin. Normal/negatif bulgular signals'a girmez.
- RESORPTION yalnız diş/kök rezorpsiyonudur. Edentül alveoler kret rezorpsiyonu için ALVEOLAR_RIDGE_RESORPTION kullan.
- IMPLANT_PROSTHODONTICS yalnız implant üstü restorasyon/protez, yükleme veya protetik sorun gerçekten varsa kullan; sadece ağızda implant bulunması yeterli değildir.
- Tam dişsizlikte COMPLETE_EDENTULISM, kısmi dişsizlikte PARTIAL_EDENTULISM kullan.
- Hareketli/total protezde tutuculuk veya stabilite sorunu varsa PROSTHESIS_RETENTION_STABILITY kullan.
- Tam dişsizlik + belirgin protez retansiyon/stabilite sorunu varsa OVERDENTURE_CANDIDACY düşünülebilir; bu bir tedavi kararı değil kaynak yönlendirme sinyalidir.
- İmplant yükleme zamanlaması/primer stabilite gerçekten tartışılıyorsa IMPLANT_LOADING_DECISION kullan; mevcut implant hastalığında sırf implant var diye kullanma.
- Süt dişi gerçekten söz konusuysa PRIMARY_TOOTH; nonkavite çürükte NONCAVITATED_CARIES; gingival çekilmede GINGIVAL_RECESSION kullan.
- routing_findings alanına en fazla 6 kısa gözlem yaz ve HER gözlemi kaynağıyla etiketle:
  [IMAGE] yalnız yüklenen görüntünün piksellerinden görülen bulgu, [TEXT] yalnız klinik nottan gelen bulgu, [BOTH] ikisinde de desteklenen bulgu.
  Yüklenen gerçek görüntü sayısı 0 ise [IMAGE] veya [BOTH] kullanma. Negasyonu koru.
  Örn: "[IMAGE] periapikal radyolüsensi", "[TEXT] soğuk testi sonrası uzamış ağrı", "[BOTH] implant çevresi krestal kemik kaybı".
- routing_findings tanı değildir; kaynak seçimini yönlendiren kısa gözlemdir.

İzin verilen uzmanlık anahtarları:
{allowed_specialties}

İzin verilen standart sinyaller:
{allowed_signals}

VAKA METADATASI:
Yaş: {age if age is not None else "bilinmiyor"}
Diş: {tooth_number or "belirtilmemiş"}
Şikayet: {chief_complaint or ""}
Klinik not: {clinical_notes or ""}
Ek hekim bilgisi: {extra_text or ""}
Yüklenen gerçek görüntü sayısı: {int(image_count or 0)}
Sistemde kayıtlı görüntü tipi: {", ".join(stored_image_types) or "OTHER"}
""".strip()



def _normalize_router_token(value: str, *, upper: bool = False) -> str:
    token = str(value or "").strip()
    token = token.replace("-", "_").replace(" ", "_")
    return token.upper() if upper else token.lower()


def _fallback_text(value: str) -> str:
    text = str(value or "").lower()
    replacements = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split())


def _refine_router_signals(
    signals: list[str],
    *,
    clinical_notes: str = "",
    chief_complaint: str = "",
    routing_findings: list[str] | None = None,
) -> list[str]:
    """
    Fast deterministic signal cleanup/enrichment after multimodal AI routing.

    This does not diagnose. It only prevents broad signals from polluting source
    selection and adds high-confidence context signals that can be recovered
    from the clinical text/routing findings without another model call.
    """
    refined = [
        item for item in _unique(signals or [])
        if item in _ALLOWED_SIGNALS
    ]
    evidence = _fallback_text(
        " ".join([
            clinical_notes or "",
            chief_complaint or "",
            " ".join(routing_findings or []),
        ])
    )

    def has(*phrases: str) -> bool:
        return any(_fallback_text(p) in evidence for p in phrases)

    def add(signal: str) -> None:
        if signal in _ALLOWED_SIGNALS and signal not in refined:
            refined.append(signal)

    def remove(signal: str) -> None:
        while signal in refined:
            refined.remove(signal)

    complete = has(
        "tam dissizlik", "tam dişsizlik", "complete edentulism",
        "complete edentulous", "total protez", "complete denture",
    )
    partial = has(
        "kismi dissizlik", "kısmi dişsizlik", "parsiyel dissizlik",
        "parsiyel dişsizlik", "partial edentulism", "partial edentulous",
        "hareketli bolumlu", "hareketli bölümlü",
    )
    prosthesis_problem = has("protez", "denture", "prosthesis") and has(
        "retansiyon", "tutuculuk", "stabilite", "retention", "stability",
        "cigneme guclugu", "çiğneme güçlüğü",
    )
    ridge_resorption = (has("kret", "ridge", "alveoler", "alveolar") and has("rezorpsiyon", "resorption", "atrofi", "atrophy")) or has(
        "kret rezorpsiyonu", "alveoler kret rezorpsiyonu",
        "alveolar ridge resorption", "ridge resorption",
        "ridge atrophy", "kret atrofisi",
    )
    root_resorption = has(
        "kok rezorpsiyonu", "kök rezorpsiyonu", "root resorption",
        "internal resorption", "external resorption", "servikal rezorpsiyon",
    )
    implant_loading = has(
        "implant yukleme", "implant yükleme", "loading timing", "loading protocol",
        "primer stabilite", "primary stability", "immediate loading",
        "early loading", "conventional loading", "hemen yukleme", "hemen yükleme",
    )
    explicit_overdenture = has("overdenture", "locator", "implant tutuculu hareketli")
    implant_prosthetic_evidence = has(
        "implant ustu protez", "implant üstü protez", "implant prosthesis",
        "implant-supported prosthesis", "abutment", "dayanak", "overdenture",
        "locator", "implant crown", "implant kuron", "implant kopru",
        "implant köprü", "protetik", "prosthodontic",
    ) or prosthesis_problem or implant_loading or complete or partial

    if complete:
        add("EDENTULISM")
        add("COMPLETE_EDENTULISM")
        remove("PARTIAL_EDENTULISM")
    elif partial:
        add("EDENTULISM")
        add("PARTIAL_EDENTULISM")
        remove("COMPLETE_EDENTULISM")

    if prosthesis_problem:
        add("PROSTHESIS_RETENTION_STABILITY")
    if ridge_resorption:
        add("ALVEOLAR_RIDGE_RESORPTION")
        if not root_resorption:
            remove("RESORPTION")
    if root_resorption:
        add("RESORPTION")

    if has("sut disi", "süt dişi", "primary tooth", "primary molar", "deciduous tooth"):
        add("PRIMARY_TOOTH")
    if has("nonkavite", "noncavitated", "non cavitated", "baslangic curuk", "başlangıç çürük"):
        add("NONCAVITATED_CARIES")
    if has("gingival recession", "dis eti cekilmesi", "diş eti çekilmesi", "mukogingival", "gingival recesyon"):
        add("GINGIVAL_RECESSION")
    if implant_loading:
        add("IMPLANT_LOADING_DECISION")
    if explicit_overdenture or (complete and prosthesis_problem):
        add("OVERDENTURE_CANDIDACY")
        add("IMPLANT_PROSTHODONTICS")

    # Existing implant disease is not a prosthodontic/loading signal by itself.
    if "IMPLANT_PROSTHODONTICS" in refined and not implant_prosthetic_evidence:
        remove("IMPLANT_PROSTHODONTICS")
    if "IMPLANT_LOADING_DECISION" in refined and not implant_loading:
        remove("IMPLANT_LOADING_DECISION")

    # High-confidence peri-implant disease pattern can be reconstructed from
    # text/findings if the multimodal model omitted the standardized code.
    implant_context = has("implant", "peri implant", "peri-implant")
    inflammatory = has("kanama", "bleeding", "suppurasyon", "suppuration", "purulence")
    pocket_or_loss = has("cep", "pocket", "sondlama", "probing", "kemik kaybi", "kemik kaybı", "bone loss")
    if implant_context and inflammatory and pocket_or_loss:
        add("PERI_IMPLANT_DISEASE")
        if has("kemik kaybi", "kemik kaybı", "bone loss", "krestal"):
            add("PERIODONTAL_BONE_LOSS")

    return refined[:16]


def _fallback_specialty_hints(
    *,
    age=None,
    tooth_number: str = "",
    clinical_notes: str = "",
    chief_complaint: str = "",
    extra_text: str = "",
    image_types: list[str] | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    High-precision deterministic safety fallback.

    It is used only when multimodal AI routing fails. These rules intentionally
    prefer strong clinical phrases over broad single-word matches, so a normal
    TME finding or alveolar ridge resorption cannot accidentally route a
    prosthodontic case to orofacial pain/endodontics.
    """
    text = _fallback_text(
        " ".join(
            [
                tooth_number or "",
                clinical_notes or "",
                chief_complaint or "",
                extra_text or "",
            ]
        )
    )
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}

    def has(*phrases: str) -> bool:
        return any(_fallback_text(p) in text for p in phrases)

    def add(specialty: str, score: int, reason: str) -> None:
        if specialty not in SPECIALTIES:
            return
        scores[specialty] = max(scores.get(specialty, 0), int(score))
        reasons.setdefault(specialty, [])
        if reason not in reasons[specialty]:
            reasons[specialty].append(reason)

    # Pedodontics
    if age is not None:
        try:
            if int(age) < 18:
                add("pedodontics", 12, "Çocuk/adölesan hasta")
        except (TypeError, ValueError):
            pass
    if has("sut disi", "karma dentisyon", "cocuk hasta", "pedodonti", "süt dişi"):
        add("pedodontics", 24, "Pediatrik dentisyon/klinik bağlam")

    # Restorative
    if has("curuk", "caries", "kavite", "kompozit", "direkt restorasyon", "sdf", "sealant"):
        add("restorative", 18, "Çürük/restoratif tedavi sinyali")
    if has("selektif curuk", "minimal invaziv", "remineralizasyon"):
        add("restorative", 24, "Minimal invaziv/restoratif karar sinyali")

    # Endodontics — require tooth/root/pulp-specific evidence. Generic alveolar
    # or ridge resorption is deliberately NOT an endodontic signal.
    if has(
        "pulpa testi", "ept", "soguk testi", "kanal tedavisi",
        "apikal periodontitis", "periapikal lezyon", "acik apeks",
        "nekrotik pulpa", "pulpitis", "kok kanal", "kök kanal",
        "kok rezorpsiyonu", "root resorption", "internal resorption",
        "external resorption", "servikal rezorpsiyon",
    ):
        add("endodontics", 26, "Pulpa/periapikal/kök-spesifik endodontik sinyal")

    # Periodontology / peri-implant
    if has(
        "periodontitis", "periodontal cep", "atasman kaybi", "furkasyon",
        "dis eti cekilmesi", "gingival recession", "peri-implantitis",
        "peri implantitis", "implant cevresinde kanama", "suppurasyon",
    ):
        add("periodontology", 26, "Periodontal/peri-implant hastalık sinyali")

    # Prosthodontics
    if has(
        "tam dissizlik", "tam dişsizlik", "edentul", "edentulous",
        "total protez", "tam protez", "overdenture",
        "implant ustu protez", "implant üstü protez",
        "bolumlu protez", "bölümlü protez", "hareketli protez",
    ):
        add("prosthodontics", 34, "Dişsizlik/protez rehabilitasyonu")
    if has("protez") and has("retansiyon", "tutuculuk", "stabilite", "cigneme guclugu", "çiğneme güçlüğü"):
        add("prosthodontics", 36, "Protez retansiyon/stabilite problemi")
    if has("alveoler kret rezorpsiyonu", "alveolar ridge resorption", "kret rezorpsiyonu"):
        add("prosthodontics", 28, "Dişsiz kret/protetik destek değerlendirmesi")

    # Oral surgery
    if has(
        "gomulu dis", "gömülü diş", "impacted", "ucuncu molar", "üçüncü molar",
        "yirmilik", "cerrahi cekim", "mronj", "bisfosfonat", "denosumab",
        "kemik grefti", "sinus lift", "augmentasyon",
    ):
        add("oral_surgery", 28, "Cerrahi/gömülü diş/MRONJ sinyali")

    # Orthodontics
    if has(
        "malokluzyon", "maloklüzyon", "caprasiklik", "çapraşıklık",
        "retainer", "relaps", "ortodontik", "sabit aparey", "seffaf plak",
        "şeffaf plak", "yer darligi", "yer darlığı",
    ):
        add("orthodontics", 28, "Ortodontik/retansiyon sinyali")

    # Oral diagnosis / radiology
    if has("cbct", "panoramik", "bitewing", "periapikal", "radyografi", "rontgen", "röntgen"):
        add("oral_diagnosis_radiology", 16, "Görüntüleme kararı/değerlendirmesi")
    specific_images = {
        _normalize_router_token(t, upper=True)
        for t in (image_types or [])
    } - {"", "OTHER"}
    if specific_images:
        add("oral_diagnosis_radiology", 10, "Dental görüntü mevcut")

    # Oral medicine
    if has(
        "lichen planus", "liken planus", "kserostomi", "agiz kurulugu",
        "ağız kuruluğu", "mukozit", "burning mouth", "yanan agiz",
        "yanan ağız", "oral medicine",
    ):
        add("oral_medicine", 27, "Oral medicine/mukozal sistemik komplikasyon sinyali")

    # Oral pathology
    if has(
        "lokoplaki", "lökoplaki", "eritroplaki", "displazi", "biyopsi",
        "histopatoloji", "opmd", "oral kanser", "malignite",
        "odontojenik kist", "odontojenik tumor", "odontojenik tümör",
    ):
        add("oral_pathology", 30, "Patoloji/biyopsi/OPMD sinyali")

    # Orofacial pain: TME/TMD only counts when symptomatic. "TME muayenesi
    # normal" alone is intentionally ignored.
    if has(
        "tme agrisi", "tme ağrısı", "tmd agrisi", "tmd ağrısı",
        "artralji", "myalji", "eklem sesi", "agiz acmada kisitlilik",
        "ağız açmada kısıtlılık", "nöropatik ağrı", "noropatik agri",
        "allodini", "parestezi", "elektriklenme",
    ):
        add("orofacial_pain", 28, "Semptomatik TMD/nöropatik ağrı sinyali")

    # Dental anesthesiology
    if has(
        "sedasyon", "nitroz oksit", "nitröz oksit", "genel anestezi",
        "hava yolu", "airway", "preoperatif aclik", "preoperatif açlık",
        "monitorizasyon", "monitörizasyon",
    ):
        add("dental_anesthesiology", 30, "Sedasyon/anestezi/hava yolu sinyali")

    # Dental public health
    if has(
        "toplum agiz sagligi", "toplum ağız sağlığı", "epidemiyoloji",
        "su florlamasi", "su florlaması", "community water fluoridation",
        "enfeksiyon kontrolu", "enfeksiyon kontrolü",
        "antibiyotik stewardship", "oral health program",
    ):
        add("dental_public_health", 30, "Toplum ağız sağlığı/koruyucu program sinyali")

    ranked = sorted(
        scores,
        key=lambda specialty: (-scores[specialty], list(SPECIALTIES).index(specialty)),
    )
    return [
        {
            "specialty": specialty,
            "label": SPECIALTIES.get(specialty, specialty),
            "score": scores[specialty],
            "reasons": reasons.get(specialty) or ["Güçlü fallback klinik sinyali"],
        }
        for specialty in ranked[: max(1, int(top_k or 5))]
    ]


_ROUTE_CACHE_TTL_SECONDS = 30 * 60
_ROUTE_CACHE_MAX_ITEMS = 512
_ROUTE_CACHE: dict[str, tuple[float, str, dict]] = {}
_ROUTE_CACHE_LOCK = threading.Lock()


def _route_fingerprint(
    *,
    age,
    tooth_number: str,
    clinical_notes: str,
    chief_complaint: str,
    image_paths: list[str],
    stored_image_types: list[str],
    top_k: int,
) -> str:
    """
    Stable case fingerprint for reusing the preliminary multimodal route.

    extra_text is intentionally excluded: final dentist answers still enter the
    downstream RAG query and final clinical prompt, but they do not force the
    same radiograph to be re-routed by a second multimodal AI call.
    """
    parts = [
        str(age if age is not None else ""),
        str(tooth_number or ""),
        str(clinical_notes or ""),
        str(chief_complaint or ""),
        ",".join(stored_image_types),
        str(int(top_k or 5)),
    ]
    for raw_path in image_paths:
        p = Path(raw_path)
        try:
            stat = p.stat()
            parts.append(
                f"{p}:{stat.st_size}:{getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1_000_000_000))}"
            )
        except OSError:
            parts.append(str(p))
    payload = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def _route_cache_get(cache_key: str, fingerprint: str) -> dict | None:
    key = str(cache_key or "").strip()
    if not key:
        return None
    now = time.monotonic()
    with _ROUTE_CACHE_LOCK:
        entry = _ROUTE_CACHE.get(key)
        if not entry:
            return None
        created_at, saved_fingerprint, saved_route = entry
        if saved_fingerprint != fingerprint or now - created_at > _ROUTE_CACHE_TTL_SECONDS:
            _ROUTE_CACHE.pop(key, None)
            return None
        result = copy.deepcopy(saved_route)
    result["mode"] = "ai_cache"
    xray_trace_event(
        "rag.ai_router.cache_hit",
        cache_key_tag=hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
        specialties=[
            item.get("specialty")
            for item in result.get("ranked_specialties", [])
            if isinstance(item, dict) and item.get("specialty")
        ],
        image_types=result.get("image_types") or [],
        signals=result.get("signals") or [],
        cache_age_ms=round((now - created_at) * 1000, 1),
    )
    return result


def _route_cache_put(cache_key: str, fingerprint: str, route: dict) -> None:
    key = str(cache_key or "").strip()
    if not key:
        return
    now = time.monotonic()
    with _ROUTE_CACHE_LOCK:
        expired = [
            saved_key
            for saved_key, (created_at, _, _) in _ROUTE_CACHE.items()
            if now - created_at > _ROUTE_CACHE_TTL_SECONDS
        ]
        for saved_key in expired:
            _ROUTE_CACHE.pop(saved_key, None)
        if len(_ROUTE_CACHE) >= _ROUTE_CACHE_MAX_ITEMS:
            oldest_key = min(_ROUTE_CACHE, key=lambda k: _ROUTE_CACHE[k][0])
            _ROUTE_CACHE.pop(oldest_key, None)
        _ROUTE_CACHE[key] = (now, fingerprint, copy.deepcopy(route))


def route_clinical_case(
    *,
    age=None,
    tooth_number: str = "",
    clinical_notes: str = "",
    chief_complaint: str = "",
    extra_text: str = "",
    image_paths: list[str] | None = None,
    stored_image_types: list[str] | None = None,
    cache_key: str = "",
    top_k: int = 5,
) -> dict:
    """Multimodal AI-first RAG routing; lexical router is failure fallback only."""

    paths = [p for p in (image_paths or []) if p]
    stored_types = _unique(stored_image_types or [])
    fingerprint = _route_fingerprint(
        age=age,
        tooth_number=tooth_number,
        clinical_notes=clinical_notes,
        chief_complaint=chief_complaint,
        image_paths=paths,
        stored_image_types=stored_types,
        top_k=top_k,
    )
    cached = _route_cache_get(cache_key, fingerprint)
    if cached is not None:
        return cached

    prompt = _build_router_prompt(
        age=age,
        tooth_number=tooth_number,
        clinical_notes=clinical_notes,
        chief_complaint=chief_complaint,
        extra_text=extra_text,
        stored_image_types=stored_types,
        image_count=len(paths),
    )

    ai_specialties: list[str] = []
    ai_image_types: list[str] = []
    signals: list[str] = []
    routing_findings: list[str] = []
    route_mode = "ai"
    started = time.perf_counter()

    xray_trace_event(
        "rag.ai_router.begin",
        image_count=len(paths),
        stored_image_types=stored_types,
        prompt_chars=len(prompt),
    )

    try:
        text = ask_ai(
            prompt,
            image_paths=paths,
            response_schema=_CLINICAL_RAG_ROUTER_SCHEMA,
        )
        data = _json_object(text)

        ai_specialties = [
            token
            for token in (
                _normalize_router_token(item)
                for item in _unique(data.get("specialties") or [])
            )
            if token in SPECIALTIES
        ][:top_k]
        ai_image_types = [
            token
            for token in (
                _normalize_router_token(item, upper=True)
                for item in _unique(data.get("image_types") or [])
            )
            if token in _ALLOWED_IMAGE_TYPES
        ]
        signals = [
            token
            for token in (
                _normalize_router_token(item, upper=True)
                for item in _unique(data.get("signals") or [])
            )
            if token in _ALLOWED_SIGNALS
        ][:10]
        routing_findings = _unique(data.get("routing_findings") or [])[:6]
        if not paths:
            ai_image_types = []

        signals = _refine_router_signals(
            signals,
            clinical_notes=clinical_notes,
            chief_complaint=chief_complaint,
            routing_findings=routing_findings,
        )

        if not ai_specialties:
            raise ValueError("AI router geçerli uzmanlık seçmedi.")

        xray_trace_event(
            "rag.ai_router.success",
            specialties=ai_specialties,
            image_types=ai_image_types,
            signals=signals,
            finding_count=len(routing_findings),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    except Exception as exc:
        route_mode = "fallback"
        xray_trace_event(
            "rag.ai_router.fallback",
            error_type=type(exc).__name__,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    if route_mode == "fallback":
        signals = _refine_router_signals(
            signals,
            clinical_notes=clinical_notes,
            chief_complaint=chief_complaint,
            routing_findings=routing_findings,
        )

    resolved_types = _resolved_image_types(ai_image_types, stored_types)
    canonical_signal_text = "\n".join(
        f"{item}: {_SIGNAL_CANONICAL_TEXT[item]}"
        for item in signals
        if item in _SIGNAL_CANONICAL_TEXT
    )

    if ai_specialties:
        # AI succeeded: do not let the old word/score router inject extra branches.
        selected = list(ai_specialties[:top_k])
        ranked_specialties = [
            {
                "specialty": specialty,
                "label": SPECIALTIES.get(specialty, specialty),
                "score": max(1, top_k - index),
                "reasons": [
                    f"Multimodal AI görüntü + klinik yönlendirmesi (öncelik {index + 1})"
                ],
            }
            for index, specialty in enumerate(selected)
        ]
    else:
        # AI routing failed. Prefer high-precision clinical safety hints first;
        # only fall back to the broader legacy lexical router if no strong hint
        # exists. This prevents broad words such as "rezorpsiyon" or a normal
        # TME exam from hijacking a clearly prosthodontic case.
        strong_fallback = _fallback_specialty_hints(
            age=age,
            tooth_number=tooth_number or "",
            clinical_notes=clinical_notes or "",
            chief_complaint=chief_complaint or "",
            extra_text=extra_text or "",
            image_types=resolved_types,
            top_k=top_k,
        )
        if strong_fallback:
            ranked_specialties = strong_fallback
        else:
            combined_text = "\n".join(
                value
                for value in [clinical_notes or "", extra_text or ""]
                if value
            )
            lexical = classify_specialties(
                age=age,
                dentition="",
                tooth_number=tooth_number or "",
                clinical_notes=combined_text,
                image_types=resolved_types,
                findings="",
                chief_complaint=chief_complaint or "",
                top_k=max(5, top_k),
            )
            lexical_ranked = lexical.get("ranked_specialties", [])
            ranked_specialties = [
                {
                    "specialty": item.get("specialty"),
                    "label": item.get("label") or SPECIALTIES.get(
                        item.get("specialty"), item.get("specialty")
                    ),
                    "score": item.get("score"),
                    "reasons": list(item.get("reasons") or []),
                }
                for item in lexical_ranked[:top_k]
                if isinstance(item, dict) and item.get("specialty")
            ]

    if not ranked_specialties:
        ranked_specialties = [
            {
                "specialty": "oral_diagnosis_radiology",
                "label": SPECIALTIES.get(
                    "oral_diagnosis_radiology", "Oral Diagnoz ve Oral Radyoloji"
                ),
                "score": 1,
                "reasons": ["Güvenli varsayılan klinik yönlendirme"],
            }
        ]

    result = {
        "ranked_specialties": ranked_specialties,
        "image_types": resolved_types,
        "routing_findings": routing_findings,
        "signals": signals,
        "canonical_signal_text": canonical_signal_text,
        "mode": route_mode,
    }

    # Cache only successful AI routes. If AI failed, final can retry instead of
    # freezing a weaker lexical fallback result.
    if route_mode == "ai":
        _route_cache_put(cache_key, fingerprint, result)

    return result
