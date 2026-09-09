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
    "pedodontics": {
        "çocuk", "pediatrik", "pedodonti", "süt dişi", "karma dentisyon",
        "fissür örtücü", "davranış yönlendirme", "çocuk travma"
    },
    "restorative": {
        "restoratif", "kompozit", "direkt restorasyon", "selektif çürük",
        "rezin infiltrasyon", "sdf", "sealant", "cam iyonomer"
    },
    "prosthodontics": {
        "protez", "protetik", "kron", "köprü", "edentül", "edentulous",
        "overdenture", "implant üstü", "ferrule", "abutment", "oklüzyon"
    },
    "oral_surgery": {
        "cerrahi", "çekim", "gömülü", "üçüncü molar", "mronj",
        "biyopsi", "osteonekroz", "oral surgery", "tmj surgery"
    },
    "orthodontics": {
        "ortodonti", "maloklüzyon", "çapraşıklık", "crossbite",
        "retainer", "retansiyon", "gömülü kanin", "sürme", "cephalometric"
    },
    "oral_diagnosis_radiology": {
        "oral diagnoz", "oral radyoloji", "radyografi", "bitewing",
        "periapikal", "panoramik", "cbct", "görüntüleme"
    },
    "oral_medicine": {
        "oral medicine", "kserostomi", "xerostomia", "mukozit",
        "lichen planus", "burning mouth", "oral lezyon", "sistemik hastalık"
    },
    "oral_pathology": {
        "oral patoloji", "displazi", "dysplasia", "odontojenik kist",
        "odontogenic tumor", "tükürük bezi", "salivary", "opmd"
    },
    "orofacial_pain": {
        "orofasiyal ağrı", "tmd", "tme", "myalgia", "arthralgia",
        "nöropatik", "neuropathic", "allodynia", "burning mouth"
    },
    "dental_anesthesiology": {
        "dental anestezi", "sedasyon", "genel anestezi", "nitrous",
        "nitröz", "hava yolu", "airway", "monitoring", "lokal anestezi"
    },
    "dental_public_health": {
        "halk sağlığı", "public health", "epidemiyoloji", "surveillance",
        "florlama", "fluoridation", "uhc", "enfeksiyon kontrolü", "stewardship"
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
        necrosis_signal = _contains_any(normalized_query, [
            "nekroz", "nekrotik", "necrosis", "necrotic",
            "yanıt alınmıyor", "no response", "nonvital", "non-vital",
        ])
        eligible = (
            caries_signal
            and (pain_signal or pulp_exposure_signal)
            and not spontaneous_signal
            and not regenerative_signal
            and not necrosis_signal
        )
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


def _specialty_source_rules(source, query, specialties):
    """Return (eligible, bonus) for non-endodontic specialty evidence cards.

    Like the endodontic source gates above, highly focused documents are only
    promoted when the case carries the corresponding clinical signal. This
    keeps each department's RAG evidence specific instead of dumping generic
    or adjacent guidance into every case.
    """
    source_normalized = str(source).replace("\\", "/")
    source_upper = source_normalized.upper()
    normalized_query = normalize(query)
    specialties = {str(item) for item in (specialties or [])}
    category = source_normalized.split("/")[0].lower() if "/" in source_normalized else ""

    supported = {
        "pedodontics", "restorative", "periodontology", "prosthodontics",
        "oral_surgery", "orthodontics", "oral_diagnosis_radiology",
        "oral_medicine", "oral_pathology", "orofacial_pain",
        "dental_anesthesiology", "dental_public_health",
    }
    if category not in supported:
        return True, 0
    if category not in specialties:
        return False, 0

    def has(*phrases):
        return _contains_any(normalized_query, phrases)

    # PEDODONTICS
    if category == "pedodontics":
        child = has("çocuk", "pediatrik", "7 yaş", "8 yaş", "9 yaş", "süt dişi", "karma dentisyon", "primary tooth")
        if "AAPD_BEHAVIOR_GUIDANCE" in source_upper:
            signal = child and has("davranış", "kooperasyon", "anksiyete", "korku", "behavior", "cooperation")
            return signal, 55 if signal else 0
        if "AAPD_DENTAL_TRAUMA_IADT" in source_upper:
            signal = has("travma", "avulsiyon", "lüksasyon", "intrüzyon", "kırık", "trauma", "avulsion", "luxation")
            return signal, 54 if signal else 0
        if "AAPD_VPT_PRIMARY" in source_upper:
            signal = has("süt dişi", "süt molar", "primary tooth", "primary molar") and has("pulpa", "pulp", "derin çürük", "deep caries")
            return signal, 56 if signal else 0
        if "AAPD_NONVITAL_PRIMARY" in source_upper:
            signal = has("süt dişi", "süt molar", "primary tooth", "primary molar") and has("nekroz", "nekrotik", "nonvital", "fistül", "abscess")
            return signal, 54 if signal else 0
        if "AAPD_VPT_PERMANENT" in source_upper:
            signal = child and has("daimi", "permanent", "immatür", "immature", "open apex", "açık apeks") and has("pulpa", "pulp", "derin çürük", "deep caries")
            return signal, 52 if signal else 0
        if "AAPD_DEVELOPING_DENTITION" in source_upper:
            signal = has("karma dentisyon", "sürme", "eruption", "crossbite", "çapraşıklık", "developing dentition")
            return signal, 46 if signal else 0
        if "AAPD_PIT_FISSURE_SEALANTS" in source_upper:
            signal = has("fissür", "sealant", "örtücü", "nonkavite", "pit fissure")
            return signal, 44 if signal else 0
        if "AAPD_FLUORIDE" in source_upper:
            signal = has("flor", "fluoride", "koruyucu", "prevention")
            return signal, 42 if signal else 0
        if "AAPD_CARIES_RISK_MANAGEMENT" in source_upper:
            return True, 34 if has("çürük", "caries", "risk") else 18

    # RESTORATIVE
    if category == "restorative":
        if "ADA_RESTORATIVE_CARIES_CPG" in source_upper:
            signal = has("çürük", "caries", "kavite", "selektif", "selective", "restorasyon", "restoration")
            return signal, 55 if signal else 0
        if "ADA_NONRESTORATIVE_CARIES" in source_upper:
            signal = has("sdf", "silver diamine", "nonrestoratif", "nonrestorative", "arrest", "nonkavite")
            return signal, 52 if signal else 0
        if "ADA_DIRECT_RESTORATIVE_MATERIALS" in source_upper:
            signal = has("kompozit", "composite", "cam iyonomer", "glass ionomer", "amalgam", "direkt restorasyon")
            return signal, 48 if signal else 0
        if "ADA_SEALANTS" in source_upper:
            signal = has("fissür", "sealant", "pit", "örtücü")
            return signal, 46 if signal else 0
        if "FDI_MINIMAL_INTERVENTION" in source_upper:
            signal = has("minimal", "koru", "preserve", "tamir", "repair", "selektif")
            return signal, 44 if signal else 0
        if "ADA_FLUORIDE" in source_upper:
            signal = has("flor", "fluoride")
            return signal, 42 if signal else 0
        if "ADA_CARIES_RISK_MANAGEMENT" in source_upper:
            return True, 30 if has("risk", "çürük", "caries") else 16

    # PERIODONTOLOGY
    if category == "periodontology":
        if "EFP_PERI_IMPLANT_DISEASES" in source_upper:
            signal = has("peri-implant", "periimplant", "implant çevresi", "mukozit", "implantitis")
            return signal, 58 if signal else 0
        if "EFP_STAGE_IV" in source_upper:
            signal = has("stage iv", "evre iv", "şiddetli mobilite", "masticatory dysfunction", "diş kaybı", "tooth loss")
            return signal, 54 if signal else 0
        if "EFP_STAGE_I_III" in source_upper:
            signal = has("periodontitis", "periodontitis", "cep", "pocket", "kemik kaybı", "bone loss")
            return signal, 48 if signal else 0
        if "AAP_EFP_CLASSIFICATION" in source_upper:
            signal = has("stage", "evre", "grade", "derece", "periodontitis", "kemik kaybı")
            return signal, 46 if signal else 0
        if "EFP_DIABETES" in source_upper:
            signal = has("diyabet", "diabetes", "hba1c", "glisemik")
            return signal, 52 if signal else 0
        if "EFP_CARDIOVASCULAR" in source_upper:
            signal = has("kardiyovasküler", "cardiovascular", "kalp", "ateroskleroz")
            return signal, 50 if signal else 0
        if "EFP_MUCOGINGIVAL_RECESSION" in source_upper:
            signal = has("recesyon", "recession", "çekilme", "keratinize", "mukogingival")
            return signal, 50 if signal else 0
        if "EFP_SUPPORTIVE_PERIODONTAL_CARE" in source_upper:
            signal = has("idame", "bakım", "supportive", "maintenance", "recall")
            return signal, 44 if signal else 0

    # PROSTHODONTICS
    if category == "prosthodontics":
        if "ITI_OVERDENTURE_LOADING" in source_upper:
            signal = has("overdenture", "implant destekli hareketli", "locator")
            return signal, 58 if signal else 0
        if "ITI_FIXED_EDENTULOUS_LOADING" in source_upper:
            signal = has("tam ark sabit", "fixed full arch", "fixed edentulous", "all-on")
            return signal, 56 if signal else 0
        if "ITI_IMMEDIATE_ESTHETIC_ZONE" in source_upper:
            signal = has("estetik bölge", "esthetic zone", "anterior implant", "immediate implant", "hemen yükleme")
            return signal, 54 if signal else 0
        if "ITI_7TH_CONSENSUS_IMPLANT_PLACEMENT_LOADING" in source_upper:
            signal = has("implant", "yükleme", "loading", "placement")
            return signal, 48 if signal else 0
        if "ACP_PDI_COMPLETE_EDENTULISM" in source_upper:
            signal = has("tam dişsiz", "complete edentulous", "total protez", "complete denture")
            return signal, 52 if signal else 0
        if "ACP_PDI_PARTIAL_EDENTULISM" in source_upper:
            signal = has("parsiyel", "partial edentulous", "kısmi dişsizlik", "hareketli bölümlü")
            return signal, 50 if signal else 0
        if "ACP_PDI_DENTATE" in source_upper:
            signal = has("dentate", "kron", "köprü", "fixed prosthesis", "sabit protez")
            return signal, 42 if signal else 0
        if "ACP_CARIES_RISK_INTERVENTION" in source_upper:
            signal = has("abutment", "dayanak", "çürük riski", "caries risk")
            return signal, 40 if signal else 0
        if "ACP_PARAMETERS_OF_CARE" in source_upper:
            return True, 20

    # ORAL SURGERY
    if category == "oral_surgery":
        if "AAOMS_MRONJ" in source_upper:
            signal = has("mronj", "osteonekroz", "bisfosfonat", "bisphosphonate", "denosumab", "antiresorptif")
            return signal, 60 if signal else 0
        if "AAOMS_THIRD_MOLAR" in source_upper:
            signal = has("üçüncü molar", "20 yaş", "wisdom tooth", "gömülü", "impacted")
            return signal, 56 if signal else 0
        if "AAOMS_TMJ_INTRAARTICULAR" in source_upper:
            signal = has("tme", "tmj", "intraartiküler", "intraarticular", "disk", "ankiloz")
            return signal, 54 if signal else 0
        if "AAOMS_ORAL_LESION_BIOPSY" in source_upper:
            signal = has("biyopsi", "biopsy", "oral lezyon", "kitle", "ülser")
            return signal, 50 if signal else 0
        if "AAOMS_ORAL_MUCOSAL_DYSPLASIA" in source_upper:
            signal = has("displazi", "dysplasia", "lökoplaki", "leukoplakia", "eritroplaki", "erythroplakia")
            return signal, 52 if signal else 0
        if "AAOMS_OFFICE_ANESTHESIA" in source_upper:
            signal = has("sedasyon", "anestezi", "deep sedation", "general anesthesia")
            return signal, 44 if signal else 0
        if "AAOMS_OSA" in source_upper:
            signal = has("uyku apnesi", "sleep apnea", "osa", "horlama")
            return signal, 48 if signal else 0
        if "AAOMS_ACUTE_POSTOP_OPIOID" in source_upper:
            signal = has("postop ağrı", "postoperative pain", "opioid", "analjezi")
            return signal, 42 if signal else 0

    # ORTHODONTICS
    if category == "orthodontics":
        if "BOS_RETENTION" in source_upper:
            signal = has("retainer", "retansiyon", "relaps", "relapse")
            return signal, 58 if signal else 0
        if "BOS_ORTHODONTIC_RADIOGRAPHS" in source_upper:
            signal = has("sefalometri", "cephalometric", "panoramik", "radyografi", "radiograph")
            return signal, 48 if signal else 0
        if "BOS_TMD_ORTHODONTIC" in source_upper:
            signal = has("tmd", "tme", "tmj", "eklem ağrısı")
            return signal, 52 if signal else 0
        if "BOS_TRAUMATISED_TOOTH" in source_upper:
            signal = has("travma", "trauma", "avulsiyon", "lüksasyon", "kırık diş")
            return signal, 52 if signal else 0
        if "BOS_RISKS_ORTHODONTIC_TREATMENT" in source_upper:
            signal = has("rezorpsiyon", "resorption", "dekalsifikasyon", "white spot", "risk")
            return signal, 48 if signal else 0
        if "BOS_EXTRACTIONS_RISK" in source_upper:
            signal = has("çekimli ortodonti", "extraction", "premolar çekimi")
            return signal, 48 if signal else 0
        if "AAPD_DEVELOPING_OCCLUSION" in source_upper or "BOS_MANAGING_DEVELOPING_OCCLUSION" in source_upper:
            signal = has("karma dentisyon", "developing occlusion", "crossbite", "çapraşıklık", "sürme")
            return signal, 46 if signal else 0

    # ORAL DIAGNOSIS & RADIOLOGY
    if category == "oral_diagnosis_radiology":
        if "AAOMR_IMPLANT_IMAGING" in source_upper:
            signal = has("implant", "kemik genişliği", "sinir komşuluğu", "implant planning")
            return signal, 60 if signal else 0
        if "AAOMR_CBCT_ORTHODONTICS" in source_upper:
            signal = has("ortodonti", "orthodontic", "gömülü kanin", "impacted canine") and has("cbct", "3d", "konik")
            return signal, 56 if signal else 0
        if "AAOMR_INCIDENTAL_FINDINGS" in source_upper:
            signal = has("insidental", "incidental", "beklenmeyen bulgu")
            return signal, 52 if signal else 0
        if "ADA_CARIES_RADIOGRAPHIC_DETECTION" in source_upper:
            signal = has("çürük", "caries", "bitewing", "aproksimal")
            return signal, 54 if signal else 0
        if "SEDENTEXCT_CBCT" in source_upper:
            signal = has("cbct", "konik ışın", "cone beam", "3d görüntü")
            return signal, 48 if signal else 0
        if "ADA_RADIATION_SAFETY" in source_upper:
            signal = has("doz", "dose", "radyasyon", "radiation", "gebelik", "pregnancy", "alara")
            return signal, 46 if signal else 0
        if "ADA_AAOMR_PATIENT_SELECTION" in source_upper:
            return True, 28

    # ORAL MEDICINE
    if category == "oral_medicine":
        if "AAOM_BURNING_MOUTH" in source_upper:
            signal = has("burning mouth", "yanan ağız", "ağız yanması")
            return signal, 58 if signal else 0
        if "AAOM_LICHEN_PLANUS" in source_upper:
            signal = has("liken planus", "lichen planus", "lichenoid")
            return signal, 58 if signal else 0
        if "ADA_XEROSTOMIA" in source_upper:
            signal = has("kserostomi", "xerostomia", "ağız kuruluğu", "hiposalivasyon")
            return signal, 56 if signal else 0
        if "MASCC_ISOO_MUCOSITIS" in source_upper:
            signal = has("mukozit", "mucositis", "kemoterapi", "radyoterapi")
            return signal, 56 if signal else 0
        if "NCI_ORAL_COMPLICATIONS_CANCER_THERAPY" in source_upper:
            signal = has("kemoterapi", "radyoterapi", "kanser tedavisi", "cancer therapy")
            return signal, 52 if signal else 0
        if "AAOMS_ORAL_LESION_EVALUATION" in source_upper:
            signal = has("oral lezyon", "ülser", "ulcer", "kitle", "2 hafta", "3 hafta")
            return signal, 50 if signal else 0
        if "WHO_ORAL_CANCER_RISK" in source_upper:
            signal = has("tütün", "tobacco", "alkol", "alcohol", "kanser riski", "oral cancer risk")
            return signal, 46 if signal else 0
        if "AAOM_ORAL_MEDICINE_CLINICAL_PRACTICE" in source_upper:
            return True, 20

    # ORAL PATHOLOGY
    if category == "oral_pathology":
        opmd = has("opmd", "lökoplaki", "leukoplakia", "eritroplaki", "erythroplakia", "premalign", "potansiyel malign")
        if "WHO_OPMD_FRAMEWORK" in source_upper:
            return opmd, 66 if opmd else 0
        if "AAOMS_ORAL_MUCOSAL_DYSPLASIA" in source_upper:
            signal = opmd or has("displazi", "dysplasia")
            return signal, 60 if signal else 0
        if "NCI_ORAL_CANCER_PATHOLOGY" in source_upper:
            signal = has("oscc", "skuamöz", "squamous", "oral kanser", "malign", "boyun nodu")
            return signal, 58 if signal else 0
        if "AAOMP_ODONTOGENIC_LESIONS" in source_upper:
            signal = has("odontojenik", "odontogenic", "kist", "cyst", "çene lezyonu", "radiolucent")
            return signal, 56 if signal else 0
        if "AAOMP_SALIVARY_GLAND_LESIONS" in source_upper:
            signal = has("tükürük bezi", "salivary", "mukosel", "mucocele", "parotis")
            return signal, 56 if signal else 0
        if "AAOMS_LESION_BIOPSY_REFERRAL" in source_upper:
            signal = has("biyopsi", "biopsy", "persistan lezyon", "iyileşmeyen", "ülser")
            return signal, 52 if signal else 0
        if "WHO_HEAD_NECK_TUMOURS" in source_upper:
            signal = has("tümör", "tumour", "tumor", "neoplazi", "neoplasm", "sınıflandırma", "classification")
            return signal, 44 if signal else 0

    # OROFACIAL PAIN
    if category == "orofacial_pain":
        if "DC_TMD" in source_upper:
            signal = has("tmd", "tme", "tmj", "myalji", "myalgia", "artralji", "arthralgia")
            return signal, 60 if signal else 0
        if "IASP_NEUROPATHIC_PAIN" in source_upper:
            signal = has("nöropatik", "neuropathic", "allodini", "allodynia", "parestezi", "yanıcı ağrı")
            return signal, 58 if signal else 0
        if "AAPD_TMD_CHILDREN" in source_upper:
            signal = has("çocuk", "adölesan", "pediatric", "adolescent") and has("tmd", "tme", "tmj")
            return signal, 56 if signal else 0
        if "AAOMS_TMJ" in source_upper:
            signal = has("tmd", "tme", "tmj") and has("cerrahi", "surgical", "intraartiküler", "disk")
            return signal, 54 if signal else 0
        if "ADA_ACUTE_DENTAL_PAIN" in source_upper:
            signal = has("akut dental ağrı", "acute dental pain", "odontojenik ağrı")
            return signal, 48 if signal else 0
        if "ICOP" in source_upper:
            return True, 28
        if "AAOP_OROFACIAL_PAIN_GUIDELINES" in source_upper:
            return True, 26

    # DENTAL ANESTHESIOLOGY
    if category == "dental_anesthesiology":
        if "AAP_AAPD_PEDIATRIC_SEDATION" in source_upper:
            signal = has("çocuk", "pediatric") and has("sedasyon", "sedation")
            return signal, 60 if signal else 0
        if "ADA_NITROUS_OXIDE" in source_upper:
            signal = has("nitröz", "nitrous", "n2o")
            return signal, 58 if signal else 0
        if "ADA_LOCAL_ANESTHESIA" in source_upper:
            signal = has("lokal anestezi", "local anesthesia", "blok", "block", "infiltrasyon")
            return signal, 56 if signal else 0
        if "ASA_PREOPERATIVE_FASTING" in source_upper:
            signal = has("açlık", "fasting", "npo") and has("sedasyon", "anestezi", "anesthesia")
            return signal, 56 if signal else 0
        if "ADA_SEDATION_GENERAL_ANESTHESIA" in source_upper:
            signal = has("sedasyon", "sedation", "genel anestezi", "general anesthesia", "deep sedation")
            return signal, 54 if signal else 0
        if "AAOMS_OFFICE_ANESTHESIA" in source_upper:
            signal = has("ofis anestezi", "office anesthesia", "derin sedasyon", "deep sedation")
            return signal, 50 if signal else 0
        if "ADA_TEACHING_PAIN_CONTROL_SEDATION" in source_upper:
            return True, 18

    # DENTAL PUBLIC HEALTH
    if category == "dental_public_health":
        if "CDC_COMMUNITY_WATER_FLUORIDATION" in source_upper:
            signal = has("su florlaması", "water fluoridation", "florlama")
            return signal, 60 if signal else 0
        if "CDC_ANTIBIOTIC_STEWARDSHIP" in source_upper:
            signal = has("antibiyotik", "antibiotic", "stewardship", "direnç", "resistance")
            return signal, 58 if signal else 0
        if "CDC_DENTAL_INFECTION_PREVENTION" in source_upper:
            signal = has("enfeksiyon kontrol", "infection prevention", "sterilizasyon", "dezenfeksiyon")
            return signal, 58 if signal else 0
        if "WHO_ORAL_HEALTH_MONITORING" in source_upper:
            signal = has("izlem", "monitoring", "surveillance", "gösterge", "indicator", "epidemiyoloji")
            return signal, 56 if signal else 0
        if "WHO_SUGARS_GUIDELINE" in source_upper:
            signal = has("şeker", "sugar", "serbest şeker", "free sugars")
            return signal, 54 if signal else 0
        if "WHO_GLOBAL_ORAL_HEALTH_ACTION_PLAN" in source_upper:
            signal = has("program", "eylem planı", "action plan", "uhc", "politika", "policy")
            return signal, 50 if signal else 0
        if "ADA_CARIES_RISK_POPULATION" in source_upper:
            signal = has("toplum", "population", "çürük riski", "caries risk")
            return signal, 48 if signal else 0
        if "WHO_GLOBAL_ORAL_HEALTH_STATUS" in source_upper:
            return True, 22

    return True, 8


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
            "pedodontics", "caries", "pain", "general", "antibiotics"
        },
        "restorative": {
            "restorative", "caries", "pain", "general"
        },
        "endodontics": {
            "endodontics", "pain", "caries", "general", "antibiotics"
        },
        "periodontology": {
            "periodontology", "general", "antibiotics"
        },
        "prosthodontics": {
            "prosthodontics", "general", "periodontology", "pain"
        },
        "oral_surgery": {
            "oral_surgery", "general", "pain", "antibiotics"
        },
        "orthodontics": {
            "orthodontics", "general", "caries"
        },
        "oral_diagnosis_radiology": {
            "oral_diagnosis_radiology", "general"
        },
        "oral_medicine": {
            "oral_medicine", "oral_cancer", "general", "antibiotics", "pain"
        },
        "oral_pathology": {
            "oral_pathology", "oral_cancer", "general"
        },
        "orofacial_pain": {
            "orofacial_pain", "pain", "general"
        },
        "dental_anesthesiology": {
            "dental_anesthesiology", "general", "antibiotics", "pain"
        },
        "dental_public_health": {
            "dental_public_health", "general", "caries", "periodontology"
        },
    }

    # Category priority keeps the lexical search grounded in the specialties
    # selected by the router.  High-risk/special-purpose categories are not
    # pulled merely because a generic word happens to overlap.
    specialty_category_priority = {
        "pedodontics": {"pedodontics": 14, "caries": 8, "pain": 5, "general": 3, "antibiotics": 1},
        "restorative": {"restorative": 14, "caries": 10, "pain": 5, "general": 3},
        "endodontics": {"endodontics": 12, "pain": 9, "caries": 5, "general": 3, "antibiotics": 1},
        "periodontology": {"periodontology": 12, "general": 3, "antibiotics": 2},
        "prosthodontics": {"prosthodontics": 14, "general": 7, "periodontology": 4, "pain": 2},
        "oral_surgery": {"oral_surgery": 14, "general": 8, "pain": 6, "antibiotics": 3},
        "orthodontics": {"orthodontics": 14, "general": 8, "caries": 2},
        "oral_diagnosis_radiology": {"oral_diagnosis_radiology": 14, "general": 12},
        "oral_medicine": {"oral_medicine": 14, "oral_cancer": 10, "general": 6, "antibiotics": 3, "pain": 3},
        "oral_pathology": {"oral_pathology": 14, "oral_cancer": 12, "general": 5},
        "orofacial_pain": {"orofacial_pain": 14, "pain": 12, "general": 4},
        "dental_anesthesiology": {"dental_anesthesiology": 14, "general": 8, "antibiotics": 3, "pain": 3},
        "dental_public_health": {"dental_public_health": 14, "general": 8, "caries": 5, "periodontology": 5},
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
        elif category in {
            "pedodontics", "restorative", "periodontology", "prosthodontics",
            "oral_surgery", "orthodontics", "oral_diagnosis_radiology",
            "oral_medicine", "oral_pathology", "orofacial_pain",
            "dental_anesthesiology", "dental_public_health",
        }:
            source_allowed, source_bonus = _specialty_source_rules(
                source, query, specialties
            )
            if not source_allowed:
                continue

        # Hastalık-özel kaynaklar vaka metninde o klinik sinyal yoksa sırf
        # zayıf bir specialty puanı nedeniyle eklenmez. Endodonti bunun
        # istisnasıdır: çürük + ağrı paterni router tarafından özellikle
        # Endodonti'ye yönlendirilebilir ve pulpal kaynaklar o zaman gereklidir.
        if (
            category in {"caries", "pain", "periodontology"}
            and category not in category_scores
            and category not in specialties
        ):
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
