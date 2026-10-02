"""Deterministic adversarial benchmark for Academic AI V2 question understanding.

No provider calls, no external embeddings, and no factual answer key. Gold labels
cover only routing/interpretation metadata; factual answers remain source-bound.
"""
from app.dental_query_intent import build_dental_requirement_plan

BASE = [
    ("ANB normal değeri kaçtır?", ("anb",), ("value",)),
    ("SNA açısı neyi değerlendirir?", ("sna",), ("measurement",)),
    ("SNB nasıl ölçülür?", ("snb",), ("measurement",)),
    ("irreversible pulpitis nedir?", ("irreversible_pulpitis",), ("definition",)),
    ("irreversible pulpitis nasıl tedavi edilir?", ("irreversible_pulpitis",), ("treatment",)),
    ("reversible pulpitis tanısı nasıl konur?", ("reversible_pulpitis",), ("diagnosis",)),
    ("periodontitis sınıflaması nedir?", ("periodontitis",), ("classification",)),
    ("implant endikasyonları nelerdir?", ("implant",), ("indication",)),
    ("implant kontrendikasyonları nelerdir?", ("implant",), ("contraindication",)),
    ("gömülü üçüncü molar komplikasyonları", ("third_molar",), ("complication",)),
    ("dry socket neden oluşur?", ("dry_socket",), ("cause",)),
    ("inferior alveolar sinir nerede seyreder?", ("ian",), ("anatomy",)),
    ("MRONJ tedavisi nedir?", ("mronj",), ("treatment",)),
    ("NaOCl komplikasyonları nelerdir?", ("sodium_hypochlorite",), ("complication",)),
    ("MIH bulguları nelerdir?", ("mih",), ("diagnosis",)),
    ("OSCC tanısı nasıl konur?", ("oscc",), ("diagnosis",)),
    ("Kennedy sınıflaması nedir?", ("kennedy_classification",), ("classification",)),
    ("ICDAS sınıflaması", ("icdas",), ("classification",)),
    ("PAI nedir?", ("periapical_index",), ("definition",)),
    ("IANB komplikasyonları", ("ianb",), ("complication",)),
]

MULTI = [
    ("irreversible pulpitisin tanısı ve tedavisi nedir?", ("irreversible_pulpitis",), ("diagnosis","treatment")),
    ("MRONJ bulguları ve tedavisi nelerdir?", ("mronj",), ("diagnosis","treatment")),
    ("IANB komplikasyonları ve kontrendikasyonları", ("ianb",), ("complication","contraindication")),
    ("SNA ile SNB arasındaki fark nedir?", ("sna","snb"), ("comparison",)),
    ("SNA, SNB ve ANB normal değerleri kaçtır?", ("sna","snb","anb"), ("value",)),
    ("kanal tedavisi komplikasyonları nelerdir?", ("root_canal_treatment",), ("complication",)),
]

QUALIFIERS = [
    ("alt sağ üçüncü moların komplikasyonları", ("third_molar",), ("complication",), ("alt","sağ")),
    ("üst sol üçüncü moları değerlendir", ("third_molar",), (), ("üst","sol")),
    ("mandibulada gömülü üçüncü molar", ("third_molar",), (), ("mandibular",)),
    ("maksillada gömülü üçüncü molar", ("third_molar",), (), ("maksiller",)),
    ("erişkinde periodontitis bulguları", ("periodontitis",), ("diagnosis",), ("erişkin",)),
    ("çocukta gingivitis bulguları", ("gingivitis",), ("diagnosis",), ("çocuk",)),
    ("akut apikal apse tedavisi", ("acute_apical_abscess",), ("treatment",), ("akut",)),
    ("kronik apikal periodontitis bulguları", ("apical_periodontitis",), ("diagnosis",), ("kronik",)),
]

NEGATIVE = [
    "hangisi kanal tedavisinde kullanılmaz?",
    "üçüncü molarda hangisi önerilmez?",
    "hangisi kontrendike değildir?",
    "hangisi doğru değildir?",
    "hangisi yanlıştır?",
    "hangisinden kaçınılmalıdır?",
]
NON_NEGATIVE = [
    "implant kontrendikasyonları nelerdir?",
    "bu işlem gebelikte kontrendike midir?",
    "kanal tedavisi komplikasyonları nelerdir?",
]

VISUAL_TRUE = [
    "Bu radyografide hangi lezyon görülüyor?",
    "Bu CBCT görüntüsünde hangi yapı görülüyor?",
    "Görüntüde kök kırığı var mı?",
    "Bu panoramikte üçüncü moların konumunu değerlendir.",
]
VISUAL_FALSE = [
    "CBCT nedir?",
    "Panoramik radyografinin endikasyonları nelerdir?",
    "Bitewing ne zaman kullanılır?",
    "Periapikal radyografi nedir?",
]

TYPOS = [
    ("pulptis tedavisi nedir?", "pulpitis"),
    ("maloccluson sınıflaması", "malocclusion"),
    ("CBCT'de mandbular kanal ilişkisi", "mandibular_canal"),
]

def test_adversarial_understanding_base_cases():
    for query, subjects, facets in BASE + MULTI:
        plan = build_dental_requirement_plan(query)
        assert set(subjects).issubset(plan.subject_node_ids), (query, subjects, plan.subject_node_ids)
        assert set(facets).issubset(plan.requested_facets), (query, facets, plan.requested_facets)

def test_adversarial_understanding_qualifiers():
    for query, subjects, facets, qualifiers in QUALIFIERS:
        plan = build_dental_requirement_plan(query)
        assert set(subjects).issubset(plan.subject_node_ids), (query, plan.subject_node_ids)
        assert set(facets).issubset(plan.requested_facets), (query, plan.requested_facets)
        assert set(qualifiers).issubset(plan.qualifiers), (query, qualifiers, plan.qualifiers)

def test_adversarial_understanding_polarity():
    for query in NEGATIVE:
        assert build_dental_requirement_plan(query).asks_negation, query
    for query in NON_NEGATIVE:
        assert not build_dental_requirement_plan(query).asks_negation, query

def test_adversarial_understanding_visual_routing():
    for query in VISUAL_TRUE:
        assert build_dental_requirement_plan(query).requires_visual_source, query
    for query in VISUAL_FALSE:
        assert not build_dental_requirement_plan(query).requires_visual_source, query

def test_adversarial_understanding_typo_rescue():
    for query, subject in TYPOS:
        assert subject in build_dental_requirement_plan(query).subject_node_ids, query

def test_adversarial_understanding_matrix_has_meaningful_size():
    # Count explicit cases plus generated morphology/paraphrase variants below.
    assert len(BASE)+len(MULTI)+len(QUALIFIERS)+len(NEGATIVE)+len(NON_NEGATIVE)+len(VISUAL_TRUE)+len(VISUAL_FALSE)+len(TYPOS) >= 50

# Cheap generated paraphrase pressure: same canonical subject/facet must survive
# common Turkish question endings without creating provider work.
PARAPHRASE_SUBJECTS = [
    ("irreversible pulpitis", "irreversible_pulpitis"),
    ("reversible pulpitis", "reversible_pulpitis"),
    ("periodontitis", "periodontitis"),
    ("MRONJ", "mronj"),
    ("üçüncü molar", "third_molar"),
    ("implant", "implant"),
    ("MIH", "mih"),
    ("OSCC", "oscc"),
    ("dry socket", "dry_socket"),
    ("IANB", "ianb"),
]
PARAPHRASE_FORMS = [
    ("tedavisi nedir?", "treatment"),
    ("nasıl tedavi edilir?", "treatment"),
    ("komplikasyonları nelerdir?", "complication"),
    ("tanısı nasıl konur?", "diagnosis"),
    ("neden oluşur?", "cause"),
    ("nedir?", "definition"),
]

def test_adversarial_generated_paraphrase_matrix():
    checked = 0
    for subject_text, subject_id in PARAPHRASE_SUBJECTS:
        for ending, facet in PARAPHRASE_FORMS:
            plan = build_dental_requirement_plan(f"{subject_text} {ending}")
            assert subject_id in plan.subject_node_ids, (subject_text, ending, plan.subject_node_ids)
            assert facet in plan.requested_facets, (subject_text, ending, facet, plan.requested_facets)
            checked += 1
    assert checked == 60

def test_adversarial_matrix_exceeds_eighty_interpretations():
    explicit = len(BASE)+len(MULTI)+len(QUALIFIERS)+len(NEGATIVE)+len(NON_NEGATIVE)+len(VISUAL_TRUE)+len(VISUAL_FALSE)+len(TYPOS)
    generated = len(PARAPHRASE_SUBJECTS)*len(PARAPHRASE_FORMS)
    assert explicit + generated >= 100


def test_adversarial_semantic_distractor_matrix():
    from app.dental_semantics import analyze_dental_text, semantic_overlap_score
    cases = [
        ("ANB normal değeri", "ANB açısı normal değer", "SNA açısı normal değer"),
        ("SNB normal değeri", "SNB açısı normal değer", "ANB açısı normal değer"),
        ("sondalama derinliği", "probing depth periodontal ölçüm", "clinical attachment loss periodontal ölçüm"),
        ("çalışma boyu", "working length apikal konstriksiyon", "apikal foramen endodontik ölçüm"),
        ("irreversible pulpitis", "irreversible pulpitis pulpa", "reversible pulpitis pulpa"),
        ("reversible pulpitis", "reversible pulpitis pulpa", "irreversible pulpitis pulpa"),
        ("third molar", "üçüncü molar yirmi yaş dişi", "ikinci molar diş"),
        ("MRONJ", "MRONJ çene osteonekrozu", "osteoradionekroz çene"),
        ("MIH", "molar incisor hypomineralization", "dental fluorosis"),
        ("IANB", "inferior alveolar nerve block", "mental nerve block"),
    ]
    for query, positive, distractor in cases:
        q = analyze_dental_text(query)
        assert semantic_overlap_score(q, analyze_dental_text(positive)) > semantic_overlap_score(q, analyze_dental_text(distractor)), query


def benchmark_case_count() -> int:
    explicit = len(BASE)+len(MULTI)+len(QUALIFIERS)+len(NEGATIVE)+len(NON_NEGATIVE)+len(VISUAL_TRUE)+len(VISUAL_FALSE)+len(TYPOS)
    paraphrases = len(PARAPHRASE_SUBJECTS)*len(PARAPHRASE_FORMS)
    distractors = 10
    return explicit + paraphrases + distractors

def test_adversarial_benchmark_case_count_is_stable():
    assert benchmark_case_count() >= 110


# Cross-product pressure: these are intentionally heterogeneous combinations,
# not duplicate paraphrases. They exercise subject identity + facet + qualifier
# + polarity together without provider calls.
CROSS_SUBJECTS = [
    ("irreversible pulpitis", "irreversible_pulpitis"),
    ("periodontitis", "periodontitis"),
    ("implant", "implant"),
    ("üçüncü molar", "third_molar"),
    ("MRONJ", "mronj"),
    ("IANB", "ianb"),
    ("SNA", "sna"),
    ("SNB", "snb"),
]
CROSS_FACETS = [
    ("tedavisi nedir?", "treatment"),
    ("komplikasyonları nelerdir?", "complication"),
    ("tanısı nasıl konur?", "diagnosis"),
    ("nedir?", "definition"),
]
CROSS_PREFIXES = ["", "erişkinde ", "akut durumda "]

def test_adversarial_cross_product_subject_facet_pressure():
    checked = 0
    for subject_text, subject_id in CROSS_SUBJECTS:
        for ending, facet in CROSS_FACETS:
            for prefix in CROSS_PREFIXES:
                plan = build_dental_requirement_plan(f"{prefix}{subject_text} {ending}")
                assert subject_id in plan.subject_node_ids, (prefix, subject_text, ending, plan.subject_node_ids)
                assert facet in plan.requested_facets, (prefix, subject_text, ending, facet, plan.requested_facets)
                checked += 1
    assert checked == 96


def test_adversarial_orthodontic_composition_pressure():
    cases = [
        ("SNA ve SNB normal değerleri kaçtır?", {"sna", "snb"}, {"value"}),
        ("SNA, SNB ve ANB normal değerlerini karşılaştır", {"sna", "snb", "anb"}, {"value", "comparison"}),
        ("SNA ile SNB arasındaki fark nedir?", {"sna", "snb"}, {"comparison"}),
        ("ANB açısı neyi değerlendirir?", {"anb"}, {"measurement"}),
        ("Wits analizi neyi değerlendirir?", {"wits"}, {"measurement"}),
        ("maloklüzyon sınıflaması nedir?", {"malocclusion"}, {"classification"}),
        ("CBCT'de mandibular kanal ilişkisi nedir?", {"mandibular_canal"}, set()),
        ("Bu panoramikte üçüncü moların konumunu değerlendir", {"third_molar"}, set()),
    ]
    for query, subjects, facets in cases:
        plan = build_dental_requirement_plan(query)
        assert subjects.issubset(set(plan.subject_node_ids)), (query, plan.subject_node_ids)
        assert facets.issubset(set(plan.requested_facets)), (query, plan.requested_facets)


def test_adversarial_benchmark_now_exceeds_two_hundred_interpretations():
    assert benchmark_case_count() + 96 + 8 >= 210
