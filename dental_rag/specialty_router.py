from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SpecialtyScore:
    specialty: str
    label: str
    score: int
    reasons: list[str]


SPECIALTIES = {
    "pedodontics": "Pedodonti",
    "restorative": "Restoratif Diş Tedavisi",
    "endodontics": "Endodonti",
    "periodontology": "Periodontoloji",
    "prosthodontics": "Protetik Diş Tedavisi",
    "oral_surgery": "Ağız, Diş ve Çene Cerrahisi",
    "orthodontics": "Ortodonti",
    "oral_diagnosis_radiology": "Oral Diagnoz ve Oral Radyoloji",
    "oral_medicine": "Oral Medicine",
    "oral_pathology": "Oral Patoloji",
    "orofacial_pain": "Orofasiyal Ağrı",
    "dental_anesthesiology": "Dental Anesteziyoloji",
    "dental_public_health": "Dental Halk Sağlığı",
}


def _normalize(text: str) -> str:
    text = (text or "").lower()

    replacements = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def _age_group(age: Optional[int]) -> str:
    if age is None:
        return "unknown"

    if age < 3:
        return "infant"
    if age < 6:
        return "early_childhood"
    if age < 12:
        return "child"
    if age < 18:
        return "adolescent"
    if age < 65:
        return "adult"

    return "older_adult"


def _dentition_group(age: Optional[int], dentition: str = "") -> str:
    d = _normalize(dentition)

    if d:
        if "sut" in d:
            return "primary"
        if "karma" in d:
            return "mixed"
        if "daimi" in d or "permanent" in d:
            return "permanent"

    if age is None:
        return "unknown"

    if age < 6:
        return "primary"
    if age < 13:
        return "mixed"

    return "permanent"


def _add(
    scores: dict[str, SpecialtyScore],
    specialty: str,
    points: int,
    reason: str,
) -> None:
    scores[specialty].score += points

    if reason not in scores[specialty].reasons:
        scores[specialty].reasons.append(reason)


KEYWORDS = {
    "pedodontics": [
        "cocuk",
        "cocuk hasta",
        "sut dis",
        "sut disi",
        "karma dentisyon",
        "erken cocukluk",
        "fissur ortucu",
        "fluor",
        "davranis",
        "sedasyon",
        "cocuk travma",
        "avulsiyon",
        "luxasyon",
        "surdur",
        "gelisim",
    ],

    "restorative": [
        "curuk",
        "caries",
        "mine",
        "dentin",
        "kavit",
        "restorasyon",
        "kompozit",
        "cam iyonomer",
        "adeziv",
        "dolgu",
        "sekonder curuk",
        "kök yuzeyi",
        "erozyon",
        "abrazyon",
        "abfraksiyon",
        "hassasiyet",
        "derin curuk",
    ],

    "endodontics": [
        "pulpa",
        "pulpitis",
        "nekroz",
        "kanal",
        "endodonti",
        "apikal",
        "periapikal",
        "periapikal lezyon",
        "apikal periodontitis",
        "apse",
        "sinus trakt",
        "fistul",
        "rezorpsiyon",
        "internal rezorpsiyon",
        "eksternal rezorpsiyon",
        "perforasyon",
        "kanal tedavisi",
        "retreatment",
        "rejenaratif",
        "apeksifikasyon",
    ],

    "periodontology": [
        "gingivitis",
        "periodontitis",
        "periodontal",
        "cep",
        "ataşman",
        "kanama",
        "kemik kaybi",
        "furkasyon",
        "mobilite",
        "gingival cekilme",
        "cekilme",
        "mukogingival",
        "peri implant",
        "periimplant",
        "implantitis",
        "srp",
        "scaling",
        "kök yuzeyi",
    ],

    "prosthodontics": [
        "protez",
        "kron",
        "kopru",
        "tam protez",
        "hareketli",
        "bolumlu protez",
        "inley",
        "onley",
        "overdenture",
        "dis eksikligi",
        "dis eksik",
        "dis kaybi",
        "okluzyon",
        "dikey boyut",
        "rehabilitasyon",
        "implant ustu protez",
    ],

    "oral_surgery": [
        "cerrahi",
        "cerrahi cekim",
        "cekilecek",
        "cekimi",
        "dis cekimi",
        "gomulu",
        "yari gomulu",
        "20 lik",
        "yirmilik",
        "gömülü",
        "kist",
        "tümor",
        "tumor",
        "travma",
        "fraktur",
        "kirilma",
        "implant cerrahisi",
        "kemik grefti",
        "greft",
        "sinus lift",
        "augmentasyon",
        "alveol",
        "preprotetik",
        "orofasiyal enfeksiyon",
        "odontojenik enfeksiyon",
        "selulit",
        "tme cerrahisi",
        "tmj",
        "tükürük bezi",
        "tukuruk bezi",
        "sinir yaralanmasi",
    ],

    "orthodontics": [
        "ortodonti",
        "malokluzyon",
        "malokluz",
        "caprasiklik",
        "çaprasiklik",
        "aralik",
        "overjet",
        "overbite",
        "acik kapanis",
        "derin kapanis",
        "capraz kapanis",
        "iskeletsel",
        "sefalometri",
        "aparey",
        "retainer",
        "retansiyon",
        "surme bozuklugu",
        "gömülü dis",
        "gelisim",
    ],

    "oral_diagnosis_radiology": [
        "röntgen",
        "rontgen",
        "radyografi",
        "radyolojik",
        "periapikal film",
        "bitewing",
        "panoramik",
        "ortopantomografi",
        "cbct",
        "tomografi",
        "3d",
        "lezyon",
        "radyolusent",
        "radyopak",
        "artefakt",
        "anatomik",
        "mandibular kanal",
        "mental foramen",
        "sinus",
        "görüntü",
        "goruntu",
    ],

    "oral_medicine": [
        "oral medicine",
        "agiz hastaligi",
        "mukozal",
        "ülser",
        "ulser",
        "beyaz leke",
        "beyaz lezyon",
        "kirmizi lezyon",
        "pigmente",
        "ağız kuruluğu",
        "agiz kurulugu",
        "xerostomia",
        "otoimmun",
        "viral",
        "fungal",
        "mantar",
        "sistemik",
        "ilac yan etkisi",
    ],

    "oral_pathology": [
        "oral patoloji",
        "patoloji",
        "biyopsi",
        "premalign",
        "malign",
        "kanser",
        "scc",
        "skuamoz",
        "tümor",
        "tumor",
        "kist",
        "odontojenik tumor",
        "mukozal lezyon",
        "atipik lezyon",
        "persistan lezyon",
    ],

    "orofacial_pain": [
        "orofasiyal agri",
        "yuz agrisi",
        "çene agrisi",
        "cene agrisi",
        "tme",
        "tmj",
        "temporomandibular",
        "bruksizm",
        "migren",
        "nevralji",
        "trigeminal",
        "bas agrisi",
        "kas agrisi",
        "eklem agrisi",
    ],

    "dental_anesthesiology": [
        "anestezi",
        "lokal anestezi",
        "sedasyon",
        "genel anestezi",
        "anksiyete",
        "korku",
        "advers",
        "komplikasyon",
        "medikal acil",
        "acil",
        "senkop",
        "anafilaksi",
        "kanama",
        "antikoagulan",
    ],

    "dental_public_health": [
        "toplum",
        "koruyucu",
        "halk sagligi",
        "epidemiyoloji",
        "risk",
        "populasyon",
        "tarama",
        "koruma",
        "florid",
        "fluoridasyon",
        "okul",
        "toplum agiz",
    ],
}


IMAGE_RULES = {
    "radiograph": {
        "oral_diagnosis_radiology": 6,
        "endodontics": 2,
        "oral_surgery": 2,
        "periodontology": 2,
        "restorative": 2,
    },
    "periapical": {
        "oral_diagnosis_radiology": 6,
        "endodontics": 4,
        "restorative": 2,
    },
    "bitewing": {
        "oral_diagnosis_radiology": 5,
        "restorative": 5,
        "pedodontics": 2,
    },
    "panoramic": {
        "oral_diagnosis_radiology": 6,
        "oral_surgery": 4,
        "orthodontics": 3,
    },
    "cbct": {
        "oral_diagnosis_radiology": 7,
        "oral_surgery": 4,
        "endodontics": 3,
        "orthodontics": 2,
        "prosthodontics": 2,
    },
    "intraoral": {
        "oral_diagnosis_radiology": 2,
        "restorative": 3,
        "periodontology": 3,
        "oral_medicine": 3,
        "oral_pathology": 3,
    },
    "extraoral": {
        "oral_diagnosis_radiology": 3,
        "oral_surgery": 3,
        "orthodontics": 2,
        "oral_medicine": 2,
    },
    "clinical_photo": {
        "oral_diagnosis_radiology": 2,
        "restorative": 3,
        "periodontology": 3,
        "oral_medicine": 3,
        "oral_pathology": 3,
    },
}


def classify_specialties(
    age: Optional[int] = None,
    dentition: str = "",
    tooth_number: str = "",
    clinical_notes: str = "",
    image_types: Optional[list[str]] = None,
    findings: str = "",
    chief_complaint: str = "",
    top_k: int = 5,
) -> dict:
    """
    Deterministic clinical-domain router.

    IMPORTANT:
    - This is NOT a diagnostic model.
    - Scores are routing relevance scores, not probabilities.
    - Dentist-selected tooth remains the source of truth.
    - AI localization must never silently replace the dentist-selected tooth.
    """

    scores = {
        key: SpecialtyScore(
            specialty=key,
            label=label,
            score=0,
            reasons=[],
        )
        for key, label in SPECIALTIES.items()
    }

    age_group = _age_group(age)
    dentition_group = _dentition_group(age, dentition)

    # ---------------------------------------------------------
    # AGE / DENTITION
    # ---------------------------------------------------------

    if age_group in {"infant", "early_childhood", "child"}:
        _add(scores, "pedodontics", 8, "Hasta çocuk yaş grubunda")
        _add(scores, "restorative", 3, "Çocuk hastada restoratif değerlendirme")
        _add(scores, "oral_diagnosis_radiology", 2, "Çocuk hastada görüntüleme değerlendirmesi")

    elif age_group == "adolescent":
        _add(scores, "orthodontics", 5, "Adölesan yaş grubu")
        _add(scores, "pedodontics", 3, "Gelişen dentisyon")
        _add(scores, "restorative", 3, "Adölesan restoratif değerlendirme")
        _add(scores, "periodontology", 2, "Adölesan periodontal değerlendirme")
        _add(scores, "endodontics", 2, "Adölesan endodontik değerlendirme")

    elif age_group == "adult":
        _add(scores, "restorative", 3, "Yetişkin restoratif değerlendirme")
        _add(scores, "endodontics", 3, "Yetişkin endodontik değerlendirme")
        _add(scores, "periodontology", 3, "Yetişkin periodontal değerlendirme")
        _add(scores, "prosthodontics", 2, "Yetişkin protetik değerlendirme")
        _add(scores, "oral_diagnosis_radiology", 2, "Görüntüleme değerlendirmesi")

    elif age_group == "older_adult":
        _add(scores, "prosthodontics", 5, "İleri yaşta protetik değerlendirme")
        _add(scores, "periodontology", 4, "İleri yaşta periodontal değerlendirme")
        _add(scores, "restorative", 3, "İleri yaşta restoratif değerlendirme")
        _add(scores, "oral_diagnosis_radiology", 3, "İleri yaşta görüntüleme değerlendirmesi")
        _add(scores, "oral_surgery", 2, "Cerrahi risk ve tedavi değerlendirmesi")
        _add(scores, "endodontics", 2, "Endodontik değerlendirme")

    if dentition_group == "primary":
        _add(scores, "pedodontics", 7, "Süt dentisyonu")
        _add(scores, "restorative", 2, "Süt dişlerinde restoratif yaklaşım")

    elif dentition_group == "mixed":
        _add(scores, "pedodontics", 5, "Karma dentisyon")
        _add(scores, "orthodontics", 4, "Karma dentisyonda gelişimsel/ortodontik değerlendirme")
        _add(scores, "oral_diagnosis_radiology", 2, "Karma dentisyonda sürme değerlendirmesi")

    elif dentition_group == "permanent":
        _add(scores, "restorative", 1, "Daimi dentisyon")
        _add(scores, "endodontics", 1, "Daimi dentisyon")

    # ---------------------------------------------------------
    # TEXT / CLINICAL INFORMATION
    # ---------------------------------------------------------

    combined_text = _normalize(
        " ".join(
            [
                tooth_number or "",
                clinical_notes or "",
                findings or "",
                chief_complaint or "",
            ]
        )
    )

    for specialty, keywords in KEYWORDS.items():
        for keyword in keywords:
            if _normalize(keyword) in combined_text:
                # Daha özgül klinik ifadeler daha fazla ağırlık alır.
                normalized_keyword = _normalize(keyword)

                points = 3

                if len(normalized_keyword.split()) >= 2:
                    points = 4

                _add(
                    scores,
                    specialty,
                    points,
                    f"Klinik bilgi eşleşmesi: {keyword}",
                )

    # ---------------------------------------------------------
    # HIGH-VALUE CLINICAL PATTERN ROUTING
    # ---------------------------------------------------------
    # Bunlar tanı koymaz.
    # Sadece RAG için klinik olarak daha ilgili uzmanlıkları öne çıkarır.

    # Derin çürük + spontan/gece ağrısı + pulpal/periapikal şüphe
    if (
        "derin curuk" in combined_text
        and (
            "spontan" in combined_text
            or "gece agrisi" in combined_text
            or "gece agri" in combined_text
            or "kendiliginden agri" in combined_text
        )
    ):
        _add(
            scores,
            "endodontics",
            8,
            "Derin çürük ve spontan/gece ağrısı birlikte"
        )

        _add(
            scores,
            "pedodontics",
            4,
            "Çocuk/adölesan hastada pulpal değerlendirme"
        )

        _add(
            scores,
            "restorative",
            4,
            "Derin çürük için restoratif değerlendirme"
        )

    if (
        "periapikal" in combined_text
        or "apikal" in combined_text
        or "pulpa" in combined_text
        or "pulpitis" in combined_text
        or "nekroz" in combined_text
    ):
        _add(
            scores,
            "endodontics",
            6,
            "Pulpa/periapikal klinik bulgu"
        )

    # Persistan oral mukozal lezyonlar:
    # Oral Medicine + Oral Pathology ana yönlendirme.
    persistent_lesion = any(
        x in combined_text
        for x in [
            "iyilesmeyen",
            "iyilesmeyen lezyon",
            "uzun suredir",
            "persistan",
            "gecmeyen",
            "kapanmayan",
        ]
    )

    mucosal_lesion = any(
        x in combined_text
        for x in [
            "oral lezyon",
            "mukozal",
            "beyaz lezyon",
            "beyaz kirmizi",
            "kirmizi lezyon",
            "ulser",
            "ulkus",
            "pigmente",
            "oral kanser",
            "kanser",
        ]
    )

    if persistent_lesion and mucosal_lesion:
        _add(
            scores,
            "oral_pathology",
            12,
            "Persistan oral/mukozal lezyon"
        )

        _add(
            scores,
            "oral_medicine",
            10,
            "Persistan mukozal hastalık değerlendirmesi"
        )

        _add(
            scores,
            "oral_diagnosis_radiology",
            4,
            "Oral lezyonun görüntüleme ile değerlendirilmesi"
        )

    elif mucosal_lesion:
        _add(
            scores,
            "oral_medicine",
            8,
            "Oral/mukozal lezyon"
        )

        _add(
            scores,
            "oral_pathology",
            8,
            "Oral lezyonun patolojik değerlendirmesi"
        )

    # Beyaz/kırmızı lezyonlar özellikle Oral Medicine + Oral Pathology
    if (
        "beyaz lezyon" in combined_text
        or "beyaz kirmizi" in combined_text
        or "kirmizi lezyon" in combined_text
    ):
        _add(
            scores,
            "oral_medicine",
            5,
            "Beyaz/kırmızı mukozal lezyon"
        )

        _add(
            scores,
            "oral_pathology",
            7,
            "Beyaz/kırmızı lezyonun patolojik değerlendirmesi"
        )

    # Gömülü diş / cerrahi çekim
    if any(
        x in combined_text
        for x in [
            "gomulu",
            "yari gomulu",
            "20 lik",
            "yirmilik",
            "cerrahi cekim",
            "gömülü",
        ]
    ):
        _add(
            scores,
            "oral_surgery",
            8,
            "Gömülü diş/cerrahi çekim"
        )

        _add(
            scores,
            "oral_diagnosis_radiology",
            3,
            "Cerrahi öncesi anatomik görüntüleme"
        )

    # Periodontal kemik kaybı
    if any(
        x in combined_text
        for x in [
            "kemik kaybi",
            "cep",
            "ataşman",
            "periodontitis",
            "furkasyon",
        ]
    ):
        _add(
            scores,
            "periodontology",
            6,
            "Periodontal hastalık/kemik kaybı bulgusu"
        )

    # İmplant planlaması: cerrahi + protez + radyoloji birlikte
    if "implant" in combined_text:
        _add(
            scores,
            "oral_surgery",
            5,
            "İmplant cerrahisi değerlendirmesi"
        )

        _add(
            scores,
            "prosthodontics",
            5,
            "İmplant üstü protetik planlama"
        )

        _add(
            scores,
            "oral_diagnosis_radiology",
            5,
            "İmplant planlamasında görüntüleme"
        )

    # TME / orofasiyal ağrı
    if any(
        x in combined_text
        for x in [
            "tme",
            "tmj",
            "temporomandibular",
            "trigeminal",
            "nevralji",
            "bruksizm",
            "yuz agrisi",
            "cene agrisi",
        ]
    ):
        _add(
            scores,
            "orofacial_pain",
            8,
            "Orofasiyal ağrı/TME bulgusu"
        )

    # ---------------------------------------------------------
    # IMAGE TYPES
    # ---------------------------------------------------------

    normalized_image_types = [
        _normalize(x)
        for x in (image_types or [])
    ]

    for image_type in normalized_image_types:
        for rule_key, specialty_points in IMAGE_RULES.items():
            if rule_key in image_type:
                for specialty, points in specialty_points.items():
                    _add(
                        scores,
                        specialty,
                        points,
                        f"Görüntü türü: {image_type}",
                    )

    # ---------------------------------------------------------
    # GENERAL CLINICAL SAFETY ROUTING
    # ---------------------------------------------------------

    if any(
        x in combined_text
        for x in [
            "kanama",
            "antikoagulan",
            "kalp",
            "alerji",
            "anafilaksi",
            "gebelik",
            "hamile",
            "diyabet",
            "hipertansiyon",
            "medikal",
            "sistemik",
        ]
    ):
        _add(
            scores,
            "dental_anesthesiology",
            5,
            "Medikal güvenlik/anestezi değerlendirmesi gerekli",
        )

    if any(
        x in combined_text
        for x in [
            "toplum",
            "tarama",
            "koruyucu",
            "populasyon",
            "epidemiyoloji",
        ]
    ):
        _add(
            scores,
            "dental_public_health",
            6,
            "Toplum/koruyucu diş hekimliği konusu",
        )

    # ---------------------------------------------------------
    # ALWAYS-USEFUL DIAGNOSTIC SUPPORT
    # ---------------------------------------------------------

    if findings or image_types:
        _add(
            scores,
            "oral_diagnosis_radiology",
            2,
            "Görüntü/bulgu temelli vaka",
        )

    # ---------------------------------------------------------
    # SORT
    # ---------------------------------------------------------

    ranked = sorted(
        scores.values(),
        key=lambda item: item.score,
        reverse=True,
    )

    # Keep only meaningful specialties.
    meaningful = [
        item
        for item in ranked
        if item.score > 0
    ]

    selected = meaningful[: max(1, top_k)]

    return {
        "age_group": age_group,
        "dentition_group": dentition_group,
        "dentist_selected_tooth": tooth_number or None,
        "tooth_source_of_truth": "DENTIST_SELECTED_TOOTH",
        "ranked_specialties": [
            {
                "specialty": item.specialty,
                "label": item.label,
                "score": item.score,
                "reasons": item.reasons[:8],
            }
            for item in selected
        ],
        "all_specialty_scores": {
            item.specialty: {
                "label": item.label,
                "score": item.score,
                "reasons": item.reasons[:8],
            }
            for item in ranked
        },
    }


if __name__ == "__main__":
    tests = [
        {
            "name": "Çocuk + derin çürük + periapikal",
            "kwargs": {
                "age": 9,
                "dentition": "karma dentisyon",
                "tooth_number": "36",
                "chief_complaint": "Gece ağrısı",
                "clinical_notes": "Derin çürük, spontan ağrı",
                "image_types": ["periapical", "intraoral"],
            },
        },
        {
            "name": "Gömülü 20 yaş dişi + CBCT",
            "kwargs": {
                "age": 24,
                "dentition": "daimi",
                "tooth_number": "48",
                "clinical_notes": "Gömülü 20 yaş dişi, cerrahi çekim planlanıyor",
                "image_types": ["panoramic", "cbct"],
            },
        },
        {
            "name": "İleri yaş + diş eksikliği + periodontal",
            "kwargs": {
                "age": 72,
                "dentition": "daimi",
                "clinical_notes": "Çoklu diş eksikliği, kemik kaybı, protez planlaması",
                "image_types": ["panoramic", "intraoral"],
            },
        },
        {
            "name": "Oral mukozal lezyon",
            "kwargs": {
                "age": 51,
                "clinical_notes": "Uzun süredir iyileşmeyen beyaz-kırmızı oral lezyon",
                "image_types": ["clinical_photo"],
            },
        },
    ]

    for test in tests:
        result = classify_specialties(**test["kwargs"])

        print("\n" + "=" * 70)
        print(test["name"])
        print("=" * 70)
        print("Yaş grubu:", result["age_group"])
        print("Dentisyon:", result["dentition_group"])
        print("Hekimin seçtiği diş:", result["dentist_selected_tooth"])

        for item in result["ranked_specialties"]:
            print(
                f"{item['label']}: "
                f"{item['score']} | "
                f"{', '.join(item['reasons'][:3])}"
            )
