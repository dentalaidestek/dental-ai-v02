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
}

_SIGNAL_CANONICAL_TEXT = {
    "CARIES_OR_RESTORATIVE": "çürük caries kavite dentin restorasyon derin çürük",
    "PAIN": "ağrı pain",
    "SPONTANEOUS_OR_NIGHT_PAIN": "spontan ağrı gece ağrısı kendiliğinden ağrı",
    "LINGERING_THERMAL_RESPONSE": "soğuk testi uzamış ağrı lingering pain uyaran kaldırıldıktan sonra devam eden ağrı",
    "PULP_TEST_ABNORMAL": "vitalite soğuk testi EPT pulpa testi anormal",
    "PULPAL_INVOLVEMENT": "pulpa pulpal pulpitis pulpa yakın",
    "APICAL_PATHOSIS": "apikal periodontitis periapikal lezyon periapikal patoloji",
    "PERIODONTAL_PATHOSIS": "periodontitis periodontal cep kemik kaybı mobilite",
    "ORAL_MUCOSAL_PATHOSIS": "oral lezyon ülser lökoplaki eritroplaki mukozal patoloji",
    "SURGICAL_PATHOSIS": "cerrahi gömülü diş çekim kemik patolojisi",
    "ORTHODONTIC_ISSUE": "maloklüzyon ortodonti çapraşıklık diş sürmesi",
    "PROSTHODONTIC_RESTORABILITY": "restorabilite ferrule kuron protez diş dokusu kaybı",
    "PEDIATRIC_DENTITION": "çocuk süt dişi karma dentisyon pedodonti",
    "OROFACIAL_PAIN": "orofasiyal ağrı TME nöropatik ağrı",
    "TRAUMA": "travma avulsiyon lüksasyon dental injury",
    "RESORPTION": "rezorpsiyon resorption internal external cervical resorption",
    "CRACK_OR_FRACTURE": "çatlak diş cracked tooth vertikal kök kırığı vertical root fracture",
    "IMMATURE_OR_OPEN_APEX": "açık apeks open apex immatür revitalizasyon rejeneratif apeksifikasyon",
    "SINUS_RELATION": "maksiller sinüs odontojenik sinüzit maxillary sinus",
    "CBCT_COMPLEXITY": "CBCT perforasyon kırık alet iyileşmeyen apikal periodontitis kompleks anatomi",
    "ENDODONTIC_TREATMENT_TECHNIQUE": "kanal tedavisi RCT enstrümantasyon irrigasyon obturasyon",
    "PERIODONTAL_BONE_LOSS": "periodontal kemik kaybı furkasyon cep ataşman kaybı periodontitis",
    "PERI_IMPLANT_DISEASE": "peri-implant mukozitis peri-implantitis implant çevresi kemik kaybı kanama",
    "EDENTULISM": "dişsizlik edentül alan tam dişsizlik kısmi dişsizlik protez",
    "IMPLANT_PROSTHODONTICS": "implant üstü protez yükleme primer stabilite overdenture sabit implant restorasyonu",
    "TOOTH_WEAR_OR_STRUCTURAL_LOSS": "aşınma tooth wear ileri diş dokusu kaybı restorabilite ferrule oklüzal rehabilitasyon",
    "IMPACTED_OR_ERUPTION_ISSUE": "gömülü diş impaksiyon ektopik sürme sürme bozukluğu gömülü kanin",
    "THIRD_MOLAR": "üçüncü molar yirmi yaş dişi gömülü molar perikoronitis",
    "SUSPICIOUS_ORAL_LESION": "iyileşmeyen ülser lökoplaki eritroplaki indürasyon oral lezyon malignite şüphesi",
    "BIOPSY_OR_PATHOLOGY_NEED": "biyopsi histopatoloji patoloji örnekleme oral lezyon",
    "TMJ_DISORDER": "TME TMD artralji myalji eklem sesi ağız açmada kısıtlılık",
    "NEUROPATHIC_PAIN_FEATURES": "nöropatik ağrı yanma elektriklenme allodini parestezi sinir hasarı",
    "SEDATION_OR_AIRWAY": "sedasyon genel anestezi hava yolu airway monitorizasyon nitröz oksit",
    "RADIOGRAPHIC_DECISION": "radyografi görüntüleme bitewing periapikal panoramik CBCT endikasyon doz optimizasyonu",
    "PEDIATRIC_BEHAVIOR": "çocuk davranış yönlendirme kooperasyon dental kaygı sedasyon gereksinimi",
    "DEVELOPING_OCCLUSION": "karma dentisyon gelişen oklüzyon çapraz kapanış yer darlığı sürme bozukluğu interceptif",
    "ORTHODONTIC_RETENTION": "ortodontik retansiyon retainer relaps sabit retainer hareketli retainer",
    "CARIES_RISK_PREVENTION": "çürük riski florür sealant SDF önleme remineralizasyon",
    "MRONJ_RISK": "MRONJ antirezorptif bisfosfonat denosumab çene osteonekrozu",
    "CANCER_THERAPY_ORAL_COMPLICATION": "kemoterapi radyoterapi oral mukozit kserostomi osteoradyonekroz enfeksiyon",
    "XEROSTOMIA_OR_HYPOSALIVATION": "kserostomi ağız kuruluğu hiposalivasyon tükürük azalması",
    "PUBLIC_HEALTH_PREVENTION": "toplum ağız sağlığı epidemiyoloji florlu su enfeksiyon kontrolü antibiyotik stewardship",
}

_CLINICAL_RAG_ROUTER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "specialties": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": list(SPECIALTIES.keys())},
            "maxItems": 5,
        },
        "image_types": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": sorted(_ALLOWED_IMAGE_TYPES)},
            "maxItems": 5,
        },
        "signals": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": sorted(_ALLOWED_SIGNALS)},
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
- Görüntü tipini mümkün olduğunca spesifik sınıflandır: PERIAPICAL, BITEWING, PANORAMIC,
  CBCT, INTRAORAL, EXTRAORAL, CLINICAL_PHOTO, RADIOGRAPH veya OTHER.
- signals yalnız POZİTİF ve karar değiştiren standart sinyalleri içersin. Normal/negatif bulgular signals'a girmez.
- routing_findings alanına en fazla 6 kısa gözlem yaz; görüntü ve klinik metinden birlikte çıkar ve negasyonu koru.
  Örn: "pulpa yakın derin restorasyon", "soğuk testi sonrası uzamış ağrı", "periodontal sondlama normal".
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
Sistemde kayıtlı görüntü tipi: {", ".join(stored_image_types) or "OTHER"}
""".strip()


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
            item
            for item in _unique(data.get("specialties") or [])
            if item in SPECIALTIES
        ][:top_k]
        ai_image_types = [
            item
            for item in _unique(data.get("image_types") or [])
            if item in _ALLOWED_IMAGE_TYPES
        ]
        signals = [
            item
            for item in _unique(data.get("signals") or [])
            if item in _ALLOWED_SIGNALS
        ][:10]
        routing_findings = _unique(data.get("routing_findings") or [])[:6]

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

    resolved_types = _resolved_image_types(ai_image_types, stored_types)
    canonical_signal_text = "\n".join(
        _SIGNAL_CANONICAL_TEXT[item]
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
        # AI routing failed: only now use the legacy lexical router as fallback.
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
