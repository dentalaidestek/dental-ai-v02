from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent / "knowledge_base"

SUPPORTED_EXTENSIONS = {".txt", ".md"}

CATEGORY_KEYWORDS = {
    "antibiotics": {
        "antibiyotik", "antibiotics", "antibiotic",
        "sistemik", "ateş", "halsizlik", "şişlik",
        "pürülan", "akıntı", "enfeksiyon"
    },
    "pain": {
        "ağrı", "pain", "analjezik", "çekim",
        "postoperatif", "postoperative"
    },
    "caries": {
        "karies", "caries", "çürük", "restoratif",
        "restorasyon", "kavitasyon", "mine", "dentin"
    },
    "periodontology": {
        "periodontitis", "periodontal", "gingivitis",
        "gingiva", "dişeti", "srp", "scaling",
        "root planing", "kök yüzeyi"
    },
    "endodontics": {
        "endodonti", "endodontic", "pulpa", "pulpal",
        "pulpitis", "nekroz", "nekrotik", "vitalite", "vitality",
        "sensibility", "soğuk testi", "cold test", "ept",
        "elektrik pulpa testi", "spontan ağrı", "gece ağrısı",
        "lingering pain", "pulpa ekspozu", "pulp exposure",
        "vital pulp therapy", "vpt", "pulpotomi", "pulpotomy",
        "kuafaj", "pulp cap", "kanal", "kök kanal",
        "root canal", "rct", "apikal periodontitis",
        "apical periodontitis", "periapikal", "sinüs traktı",
        "sinus tract", "fistül", "rezorpsiyon", "resorption",
        "çatlak diş", "cracked tooth", "vertikal kök kırığı",
        "vertical root fracture", "açık apeks", "open apex",
        "revitalizasyon", "regenerative endodontics",
        "retreatment", "yeniden kanal", "perforasyon",
        "perforation", "kırık alet", "separated instrument"
    },
    "oral_cancer": {
        "oral kanser", "kanser", "oscc", "opmd",
        "malign", "premalign", "eritroplaki", "lökoplaki",
        "iyileşmeyen ülser", "persistan ülser",
        "persistan lezyon", "beyaz lezyon", "kırmızı lezyon"
    },
    "general": {
        "röntgen", "radyografi", "cbct",
        "x-ray", "görüntüleme", "sedasyon",
        "anestezi"
    }
}


def normalize(text):
    text = text.lower()

    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"[^a-z0-9\s]", " ", text)


def tokenize(text):
    stop_words = {
        "ve", "veya", "ile", "bir", "bu", "şu",
        "için", "olan", "olarak", "daha", "çok",
        "mı", "mi", "mu", "mü",
        "the", "and", "or", "of", "to",
        "a", "an", "in", "on"
    }

    return {
        word
        for word in normalize(text).split()
        if len(word) >= 2 and word not in stop_words
    }


def detect_categories(query):
    normalized_query = normalize(query)
    tokens = tokenize(query)

    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            nk = normalize(keyword)

            if " " in nk:
                if nk in normalized_query:
                    score += 3
            elif nk in tokens:
                score += 2

        if score:
            scores[category] = score

    return scores


def chunk_text(text, max_chars=2500):
    words = text.split()
    chunks = []
    current = []
    size = 0

    for word in words:
        if current and size + len(word) + 1 > max_chars:
            chunks.append(" ".join(current))
            current = []
            size = 0

        current.append(word)
        size += len(word) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


def load_documents():
    documents = []

    if not BASE_DIR.exists():
        return documents

    for path in BASE_DIR.rglob("*"):

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        if path.name.lower() == "readme.txt":
            continue

        if "SOURCE_INDEX" in path.name.upper():
            continue

        if "SOURCE_PRIORITY" in path.name.upper():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        if not text.strip():
            continue

        category = path.parent.name.lower()

        documents.append({
            "source": str(path.relative_to(BASE_DIR)),
            "text": text,
            "category": category
        })

    return documents


def search(query, top_k=5):

    query_tokens = tokenize(query)
    category_scores = detect_categories(query)

    if not query_tokens:
        return []

    results = []

    for document in load_documents():

        for chunk in chunk_text(document["text"]):

            chunk_tokens = tokenize(chunk)

            overlap = query_tokens.intersection(chunk_tokens)

            if not overlap:
                continue

            score = len(overlap)

            category = document["category"]

            # Vakanın konusuyla eşleşen kategoriye güçlü öncelik.
            if category in category_scores:
                score += category_scores[category] * 3

            # Başlıkta geçen kelimeler ayrıca değerli.
            source_tokens = tokenize(document["source"])
            title_overlap = query_tokens.intersection(source_tokens)
            score += len(title_overlap) * 2

            results.append({
                "score": score,
                "source": document["source"],
                "text": chunk
            })

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    # Aynı kaynağın tekrar tekrar gelmesini önle.
    unique_results = []
    seen = set()

    for result in results:
        if result["source"] in seen:
            continue

        seen.add(result["source"])
        unique_results.append(result)

        if len(unique_results) >= top_k:
            break

    return unique_results


def get_relevant_context(
    query,
    top_k=5,
    max_chars=7000
):

    results = search(
        query,
        top_k=top_k
    )

    if not results:
        return ""

    parts = []
    total = 0

    for result in results:

        part = (
            f"[KAYNAK: {result['source']}]\n"
            f"{result['text']}"
        )

        if total + len(part) > max_chars:
            break

        parts.append(part)
        total += len(part)

    return "\n\n---\n\n".join(parts)




def _contains_any(normalized_query, phrases):
    return any(normalize(phrase) in normalized_query for phrase in phrases)


def _endodontic_source_rules(source, query, specialties):
    """Return (eligible, source_bonus) for endodontic knowledge files.

    Broad/core sources can support most endodontic cases; highly specialized
    documents are gated by case signals so trauma/resorption/CBCT/etc. do not
    flood an ordinary deep-caries prompt.
    """
    source_normalized = str(source).replace("\\", "/")
    source_upper = source_normalized.upper()
    normalized_query = normalize(query)
    specialties = {str(item) for item in (specialties or [])}

    if not source_normalized.lower().startswith("endodontics/"):
        return True, 0

    endo_routed = "endodontics" in specialties
    if not endo_routed and not detect_categories(query).get("endodontics"):
        return False, 0

    caries_signal = _contains_any(normalized_query, [
        "çürük", "caries", "kavit", "dentin", "derin çürük", "deep caries",
    ])
    pain_signal = _contains_any(normalized_query, [
        "ağrı", "pain", "sızlama", "zonklama", "soğuk", "sıcak",
    ])

    # Spontan/gece ağrısı gerçek klinik dilde çoğu zaman tam olarak
    # "spontan ağrı" diye yazılmaz: "kendiliğinden başladı", "geceleri
    # uyandırıyor" veya termal uyaran kalktıktan sonra 20-30 saniye sürdü
    # gibi ifadeler kullanılır. Negatif ifadeler ("spontan ağrı yok")
    # pozitif sinyal sayılmaz.
    spontaneous_negated = bool(re.search(
        r"(?:spontan|kendiliginden|gece|geceleri).{0,55}"
        r"(?:yok|yoktur|tariflemiyor|olmuyor|bulunmuyor|inkar ediyor|denies)",
        normalized_query,
    ))
    spontaneous_wording_signal = (
        pain_signal
        and not spontaneous_negated
        and _contains_any(normalized_query, [
            "spontan", "kendiliğinden", "geceleri", "gece", "uyandıran",
            "uyandırıyor", "uykudan uyandır", "spontaneous", "night pain",
            "wakes", "waking",
        ])
    )
    thermal_signal = _contains_any(normalized_query, [
        "soğuk", "sıcak", "cold", "hot", "termal", "thermal",
    ])
    post_stimulus_signal = _contains_any(normalized_query, [
        "uyaran kaldırıldıktan sonra", "uyaran kesildikten sonra",
        "uyaran uzaklaştırıldıktan sonra", "stimulus removed",
        "after stimulus", "sonra devam", "devam ediyor",
        "sürüyor", "sürmektedir", "lingering", "uzamış", "uzun süre",
    ])
    duration_10s_or_more = bool(re.search(
        r"\b(?:1[0-9]|[2-9][0-9]|[1-9][0-9]{2,})\s*(?:saniye|sn|sec|second)",
        normalized_query,
    ))
    lingering_thermal_signal = thermal_signal and post_stimulus_signal and (
        duration_10s_or_more
        or _contains_any(normalized_query, ["lingering", "uzamış", "uzun süre"])
    )
    direct_spontaneous_signal = (
        not spontaneous_negated
        and _contains_any(normalized_query, [
            "spontan ağrı", "spontaneous pain", "gece ağrısı", "night pain",
            "lingering pain", "uzamış ağrı", "uzun süre devam",
        ])
    )
    spontaneous_signal = (
        direct_spontaneous_signal
        or spontaneous_wording_signal
        or lingering_thermal_signal
    )
    pulp_test_signal = _contains_any(normalized_query, [
        "vitalite", "vitality", "sensibility", "soğuk testi", "cold test",
        "ept", "elektrik pulpa", "pulpa testi", "pulp test",
    ])
    pulp_exposure_signal = _contains_any(normalized_query, [
        "pulpa ekspozu", "pulp exposure", "pulpa açılması", "pulp exposed",
    ])
    apical_signal = _contains_any(normalized_query, [
        "apikal periodontitis", "apical periodontitis", "periapikal",
        "periradiküler", "periradicular", "sinüs traktı", "sinus tract",
        "fistül", "fistula",
    ])
    rct_signal = _contains_any(normalized_query, [
        "kanal tedavisi", "root canal", "rct", "pulpektomi", "pulpectomy",
        "retreatment", "yeniden kanal",
    ])
    instrumentation_signal = rct_signal or _contains_any(normalized_query, [
        "enstrümantasyon", "instrumentation", "şekillendirme", "shaping",
        "niti", "nickel titanium", "çalışma boyu", "working length",
        "glide path", "transportasyon", "transportation",
    ])
    irrigation_signal = rct_signal or _contains_any(normalized_query, [
        "irrigasyon", "irrigation", "naocl", "sodyum hipoklorit",
        "sodium hypochlorite", "edta", "kalsiyum hidroksit",
        "calcium hydroxide", "kanal içi medikament", "intracanal dressing",
    ])
    obturation_signal = rct_signal or _contains_any(normalized_query, [
        "obturasyon", "obturation", "kök kanal dolgusu", "root filling",
        "güta perka", "gutta percha", "sealer", "single cone",
        "lateral condensation", "vertical compaction",
    ])
    adjunct_signal = _contains_any(normalized_query, [
        "yardımcı tedavi", "adjunct therapy", "ultrasonik aktivasyon",
        "ultrasonic activation", "irrigant activation", "lazer", "laser",
        "fotodinamik", "photodynamic", "ozon", "ozone",
    ])
    cbct_signal = _contains_any(normalized_query, [
        "cbct", "konik ışın", "cone beam", "3d görüntü", "üç boyutlu",
        "kalsifiye kanal", "calcified canal", "perforasyon", "perforation",
        "kırık alet", "separated instrument", "retreatment", "yeniden kanal",
        "nonhealing", "iyileşmeyen",
    ])
    resorption_signal = _contains_any(normalized_query, [
        "rezorpsiyon", "resorption", "internal resorption",
        "external resorption", "servikal rezorpsiyon", "cervical resorption",
    ])
    crack_signal = _contains_any(normalized_query, [
        "çatlak", "crack", "cracked tooth", "vertikal kök kırığı",
        "vertical root fracture", "split tooth", "ısırma ağrısı", "biting pain",
    ])
    trauma_signal = _contains_any(normalized_query, [
        "travma", "trauma", "avulsiyon", "avulsion", "lüksasyon", "luxation",
        "intrüzyon", "intrusion", "ekstrüzyon", "extrusion",
        "dental injury",
    ])
    regenerative_signal = _contains_any(normalized_query, [
        "açık apeks", "open apex", "immatür", "immature", "gelişimini tamamlamamış",
        "revitalizasyon", "regenerative", "rejeneratif", "apeksifikasyon",
        "apexification",
    ])
    sinus_signal = _contains_any(normalized_query, [
        "sinüzit", "sinusitis", "maksiller sinüs", "maxillary sinus",
        "odontojenik sinüzit", "odontogenic sinusitis",
    ])
    difficulty_signal = _contains_any(normalized_query, [
        "zor vaka", "kompleks vaka", "difficulty", "sevk", "referral",
        "kalsifiye", "calcified", "şiddetli kurvatür", "severe curvature",
        "s eğrisi", "c shaped", "c-shaped", "perforasyon", "retreatment",
        "kırık alet", "separated instrument",
    ])

    if "ESE_S3_PULPAL_APICAL_DISEASE_2023" in source_upper:
        # Endodontik çekirdek kılavuz her endodontik vakada ana omurgadır.
        return True, 60
    if "ESE_PULPITIS_DIAGNOSIS_SYSTEMATIC_REVIEW_2023" in source_upper:
        eligible = (caries_signal and pain_signal) or pulp_test_signal
        if not eligible:
            return False, 0
        return True, 55 if spontaneous_signal else 48
    if "ESE_VPT_NONSPONTANEOUS_PAIN_SYSTEMATIC_REVIEW_2023" in source_upper:
        eligible = caries_signal and (pain_signal or pulp_exposure_signal) and not spontaneous_signal
        return eligible, 52 if eligible else 0
    if "ESE_PULPOTOMY_VS_RCT_SPONTANEOUS_PAIN_2023" in source_upper:
        return spontaneous_signal, 52 if spontaneous_signal else 0
    if "AAE_VITAL_PULP_THERAPY_2021" in source_upper:
        eligible = caries_signal or pulp_exposure_signal or pulp_test_signal
        if not eligible:
            return False, 0
        return True, 38 if (pulp_exposure_signal or pulp_test_signal) else 30
    if "AAE_TREATMENT_STANDARDS_2018" in source_upper:
        eligible = rct_signal or apical_signal or difficulty_signal
        return eligible, 22 if eligible else 0

    if "ESE_APICAL_PERIODONTITIS_IMAGING_2023" in source_upper:
        eligible = apical_signal or cbct_signal
        return eligible, 38 if eligible else 0
    if "ESE_ROOT_CANAL_INSTRUMENTATION_2023" in source_upper:
        return instrumentation_signal, 30 if instrumentation_signal else 0
    if "ESE_IRRIGATION_DRESSING_2023" in source_upper:
        return irrigation_signal, 30 if irrigation_signal else 0
    if "ESE_ROOT_FILLING_2023" in source_upper:
        return obturation_signal, 28 if obturation_signal else 0
    if "ESE_ADJUNCT_THERAPY_APICAL_PERIODONTITIS_2023" in source_upper:
        return adjunct_signal, 42 if adjunct_signal else 0

    if "AAE_AAOMR_CBCT_ENDODONTICS_2025" in source_upper:
        eligible = cbct_signal or resorption_signal or crack_signal or trauma_signal
        return eligible, 42 if eligible else 0
    if "ESE_ROOT_RESORPTION_2023" in source_upper:
        return resorption_signal, 48 if resorption_signal else 0
    if "ESE_CRACKS_FRACTURES_2025" in source_upper:
        return crack_signal, 48 if crack_signal else 0
    if "AAE_REGENERATIVE_ENDODONTICS_2022_2025" in source_upper:
        return regenerative_signal, 48 if regenerative_signal else 0
    if "AAE_TRAUMATIC_DENTAL_INJURIES_2026" in source_upper:
        return trauma_signal, 48 if trauma_signal else 0
    if "AAE_MAXILLARY_SINUSITIS_ENDODONTIC_ORIGIN_2018" in source_upper:
        return sinus_signal, 48 if sinus_signal else 0
    if "AAE_CASE_DIFFICULTY_2021" in source_upper:
        return difficulty_signal, 36 if difficulty_signal else 0

    explicit_endo = bool(detect_categories(query).get("endodontics"))
    return explicit_endo, 8 if explicit_endo else 0

def get_specialty_relevant_context(
    query,
    specialties=None,
    top_k=5,
    max_chars=7000,
):
    """
    Specialty router sonucuna göre mevcut RAG kaynaklarını daraltır.

    Router tanı koymaz; yalnızca hangi dental disiplinlerin
    bilgi açısından daha ilgili olduğunu belirler.

    Mevcut knowledge_base'de bulunmayan branşlar için kaynak
    uydurulmaz. Uygun mevcut kaynak kategorileri kullanılır.
    """
    specialties = specialties or []

    specialty_to_categories = {
        "pedodontics": {
            "caries", "pain", "general", "antibiotics"
        },
        "restorative": {
            "caries", "pain", "general"
        },
        "endodontics": {
            "endodontics", "pain", "caries", "general", "antibiotics"
        },
        "periodontology": {
            "periodontology", "general", "antibiotics"
        },
        "prosthodontics": {
            "general", "periodontology", "pain"
        },
        "oral_surgery": {
            "general", "pain", "antibiotics"
        },
        "orthodontics": {
            "general", "caries"
        },
        "oral_diagnosis_radiology": {
            "general"
        },
        "oral_medicine": {
            "oral_cancer", "general", "antibiotics", "pain"
        },
        "oral_pathology": {
            "oral_cancer", "general"
        },
        "orofacial_pain": {
            "pain", "general"
        },
        "dental_anesthesiology": {
            "general", "antibiotics", "pain"
        },
        "dental_public_health": {
            "general", "caries", "periodontology"
        },
    }

    # Category priority keeps the lexical search grounded in the specialties
    # selected by the router.  High-risk/special-purpose categories are not
    # pulled merely because a generic word happens to overlap.
    specialty_category_priority = {
        "pedodontics": {"caries": 8, "pain": 5, "general": 3, "antibiotics": 1},
        "restorative": {"caries": 10, "pain": 5, "general": 3},
        "endodontics": {"endodontics": 12, "pain": 9, "caries": 5, "general": 3, "antibiotics": 1},
        "periodontology": {"periodontology": 12, "general": 3, "antibiotics": 2},
        "prosthodontics": {"general": 7, "periodontology": 4, "pain": 2},
        "oral_surgery": {"general": 8, "pain": 6, "antibiotics": 3},
        "orthodontics": {"general": 8, "caries": 2},
        "oral_diagnosis_radiology": {"general": 12},
        "oral_medicine": {"oral_cancer": 10, "general": 6, "antibiotics": 3, "pain": 3},
        "oral_pathology": {"oral_cancer": 12, "general": 5},
        "orofacial_pain": {"pain": 12, "general": 4},
        "dental_anesthesiology": {"general": 8, "antibiotics": 3, "pain": 3},
        "dental_public_health": {"general": 8, "caries": 5, "periodontology": 5},
    }

    allowed_categories = set()

    for specialty in specialties:
        allowed_categories.update(
            specialty_to_categories.get(str(specialty), set())
        )

    # Router sonucu çözülemezse mevcut RAG davranışını koru.
    if not allowed_categories:
        return get_relevant_context(
            query,
            top_k=top_k,
            max_chars=max_chars,
        )

    # Önce normal RAG araması yapılır.
    # Böylece mevcut relevance scoring korunur.
    results = search(query, top_k=max(top_k * 8, 40))

    if not results:
        return ""

    category_scores = detect_categories(query)
    category_priority = {}

    for specialty in specialties:
        for category, bonus in specialty_category_priority.get(str(specialty), {}).items():
            category_priority[category] = max(category_priority.get(category, 0), bonus)

    ranked_results = []

    for result in results:
        source = str(result.get("source", "")).replace("\\", "/")
        parts = source.split("/")

        # Kaynağın knowledge_base altındaki kategori klasörünü bul.
        category = ""
        if len(parts) >= 2:
            category = parts[-2].lower()

        if category not in allowed_categories:
            continue

        source_bonus = 0
        if category == "endodontics":
            source_allowed, source_bonus = _endodontic_source_rules(
                source, query, specialties
            )
            if not source_allowed:
                continue

        # Hastalık-özel kaynaklar vaka metninde o klinik sinyal yoksa sırf
        # zayıf bir specialty puanı nedeniyle eklenmez. Endodonti bunun
        # istisnasıdır: çürük + ağrı paterni router tarafından özellikle
        # Endodonti'ye yönlendirilebilir ve pulpal kaynaklar o zaman gereklidir.
        if category in {"caries", "pain", "periodontology"} and category not in category_scores:
            continue
        if (
            category == "endodontics"
            and category not in category_scores
            and "endodontics" not in specialties
        ):
            continue

        # Antibiyotik ve oral-kanser gibi özel kaynaklar yalnızca vaka metni
        # gerçekten o kategoriyi işaret ediyorsa kullanılır. Böylece basit bir
        # "lezyon" sözcüğü oral-kanser rehberini çürük vakasına taşımaz.
        if category in {"antibiotics", "oral_cancer"} and category not in category_scores:
            continue

        source_upper = source.upper()
        normalized_query = normalize(query)

        # General klasöründeki özel amaçlı rehberler yalnızca ilgili klinik
        # sinyal varsa seçilir. Örneğin görüntülü bir çürük vakasına sırf
        # ``general`` kategorisinde diye sedasyon rehberi eklenmez.
        if "SEDATION" in source_upper and not any(
            token in normalized_query
            for token in ["sedasyon", "anestezi", "anksiyete", "korku"]
        ):
            continue

        adjusted_score = (
            int(result.get("score", 0))
            + int(category_priority.get(category, 0))
            + int(category_scores.get(category, 0)) * 2
            + int(source_bonus)
        )

        ranked_results.append((adjusted_score, result))

    ranked_results.sort(
        key=lambda item: (item[0], int(item[1].get("score", 0))),
        reverse=True,
    )

    selected = [result for _, result in ranked_results[:top_k]]

    # Specialty filtresi çok dar kaldıysa mevcut RAG'dan sonuç eklemek yerine
    # boş dön. Yanlış branşa ait kaynakla modeli yönlendirmek, kaynak vermemekten
    # daha risklidir.
    if not selected:
        return ""

    parts = []
    total = 0

    for result in selected:
        part = (
            f"[KAYNAK: {result['source']}]\n"
            f"{result['text']}"
        )

        if total + len(part) > max_chars:
            break

        parts.append(part)
        total += len(part)

    return "\n\n---\n\n".join(parts)

if __name__ == "__main__":

    print("DENTAL-AI SMART RAG TEST")
    print("=========================")

    query = input(
        "Dental konu/soru: "
    ).strip()

    categories = detect_categories(query)

    print()
    print("Tespit edilen kategoriler:")
    print(categories)

    results = search(query)

    if not results:
        print()
        print("İlgili klinik kaynak bulunamadı.")
    else:
        print()

        for i, result in enumerate(
            results,
            start=1
        ):
            print(
                f"{i}. {result['source']} "
                f"(skor: {result['score']})"
            )
            print(
                result["text"][:500]
            )
            print()
