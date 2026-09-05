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
        "endodonti", "endodontic", "pulpa",
        "pulpitis", "nekroz", "nekrotik",
        "kanal", "kök kanal", "periapikal"
    },
    "oral_cancer": {
        "oral kanser", "kanser", "oscc",
        "opmd", "lezyon", "ülser", "ülserasyon",
        "malign", "premalign"
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
            "pain", "caries", "general", "antibiotics"
        },
        "periodontology": {
            "periodontology", "general", "antibiotics"
        },
        "prosthodontics": {
            "general", "periodontology", "pain"
        },
        "oral_surgery": {
            "general", "pain", "antibiotics", "oral_cancer"
        },
        "orthodontics": {
            "general", "caries"
        },
        "oral_diagnosis_radiology": {
            "general", "oral_cancer"
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
    results = search(query, top_k=max(top_k * 3, 10))

    if not results:
        return ""

    selected = []

    for result in results:
        source = str(result.get("source", "")).replace("\\", "/")
        parts = source.split("/")

        # Kaynağın knowledge_base altındaki kategori klasörünü bul.
        category = ""
        if len(parts) >= 2:
            category = parts[-2].lower()

        if category in allowed_categories:
            selected.append(result)

        if len(selected) >= top_k:
            break

    # Specialty filtresi çok dar kaldıysa mevcut RAG'dan
    # gerçekten ilgili birkaç sonucu kontrollü fallback olarak ekle.
    if not selected:
        selected = results[:top_k]

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
