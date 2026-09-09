from __future__ import annotations

import json
import time
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
            "maxItems": 8,
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


def route_clinical_case(
    *,
    age=None,
    tooth_number: str = "",
    clinical_notes: str = "",
    chief_complaint: str = "",
    extra_text: str = "",
    image_paths: list[str] | None = None,
    stored_image_types: list[str] | None = None,
    top_k: int = 5,
) -> dict:
    """Multimodal AI-first RAG routing with deterministic fallback."""

    paths = [p for p in (image_paths or []) if p]
    stored_types = _unique(stored_image_types or [])
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
        ][:8]
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
    combined_text = "\n".join(
        value
        for value in [clinical_notes or "", extra_text or ""]
        if value
    )
    findings_for_fallback = "\n".join(
        value
        for value in [canonical_signal_text, "\n".join(routing_findings)]
        if value
    )

    lexical = classify_specialties(
        age=age,
        dentition="",
        tooth_number=tooth_number or "",
        clinical_notes=combined_text,
        image_types=resolved_types,
        findings=findings_for_fallback,
        chief_complaint=chief_complaint or "",
        top_k=max(5, top_k),
    )
    lexical_ranked = lexical.get("ranked_specialties", [])
    lexical_by_specialty = {
        item.get("specialty"): item
        for item in lexical_ranked
        if isinstance(item, dict) and item.get("specialty")
    }

    if ai_specialties:
        selected = list(ai_specialties)
        # AI is primary. Rules are only a safety net for a very strong signal;
        # weak word matches cannot pollute RAG.
        for item in lexical_ranked:
            specialty = item.get("specialty") if isinstance(item, dict) else None
            score = int(item.get("score") or 0) if isinstance(item, dict) else 0
            if specialty and specialty not in selected and score >= 8:
                selected.append(specialty)
            if len(selected) >= top_k:
                break
    else:
        selected = [
            item.get("specialty")
            for item in lexical_ranked
            if isinstance(item, dict) and item.get("specialty")
        ][:top_k]

    if not selected:
        selected = ["oral_diagnosis_radiology"]

    ranked_specialties = []
    for specialty in selected[:top_k]:
        lexical_item = lexical_by_specialty.get(specialty) or {}
        ranked_specialties.append(
            {
                "specialty": specialty,
                "label": SPECIALTIES.get(specialty, specialty),
                "score": lexical_item.get("score"),
                "reasons": (
                    ["Multimodal AI görüntü + klinik yönlendirmesi"]
                    if specialty in ai_specialties
                    else list(lexical_item.get("reasons") or [])
                ),
            }
        )

    return {
        "ranked_specialties": ranked_specialties,
        "image_types": resolved_types,
        "routing_findings": routing_findings,
        "signals": signals,
        "canonical_signal_text": canonical_signal_text,
        "mode": route_mode,
    }
