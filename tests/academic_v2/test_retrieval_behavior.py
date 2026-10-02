"""Dependency-free behavioral checks for local dental retrieval semantics.

These cases protect the semantic bridges that embeddings used to provide.
The benchmark intentionally tests query construction rather than a live DB so
CI remains fast and deterministic.
"""
from pathlib import Path
import ast
from app.dental_query_intent import classify_dental_intent, classify_dental_intents, combined_relation_hints, build_dental_requirement_plan
from app.dental_knowledge_graph import graph_expansion_terms

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
tree = ast.parse(source)

terms_source = (ROOT / "app/dental_retrieval_terms.py").read_text(encoding="utf-8")
terms_ns = {}
exec(compile(terms_source, "<dental-terms>", "exec"), terms_ns)
wanted = {"_QUERY_NOISE_RE", "_DENTAL_NOTATION_RULES"}
namespace = {"re": __import__("re"), "classify_dental_intent": classify_dental_intent, "classify_dental_intents": classify_dental_intents, "combined_relation_hints": combined_relation_hints, "graph_expansion_terms": graph_expansion_terms}
namespace["DENTAL_ALIAS_GROUPS"] = terms_ns["DENTAL_ALIAS_GROUPS"]
namespace["_DENTAL_CONCEPT_GROUPS"] = terms_ns["DENTAL_ALIAS_GROUPS"]
for node in tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        names = []
        if isinstance(node, ast.Assign):
            names = [x.id for x in node.targets if isinstance(x, ast.Name)]
        elif isinstance(node.target, ast.Name):
            names = [node.target.id]
        if any(name in wanted for name in names):
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<retrieval-data>", "exec"), namespace)
    elif isinstance(node, ast.FunctionDef) and node.name in {
        "_normalize_dental_notation", "_query_term_present", "_concept_alternatives", "_retrieval_terms", "_fts_query"
    }:
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<retrieval-fn>", "exec"), namespace)

cases = [
    ("alt çenenin geriliğini anlat", ("mandibular retrognati", "retrognati")),
    ("çene eklemi bozuklukları", ("TME", "TMJ", "temporomandibular")),
    ("kanal tedavisi nedir", ("endodonti", "root canal")),
    ("yirmi yaş dişi komplikasyonları", ("third molar", "üçüncü molar")),
    ("derin kapanış nedir", ("deep bite", "overbite")),
    ("kök ucu lezyonu", ("apikal", "periapikal")),
    ("diş eti hastalıkları", ("gingiva", "gingival")),
    ("aljinat özelliklerini açıkla", ("alginate", "irreversible hydrocolloid")),
    ("çalışma boyu nasıl belirlenir", ("working length", "WL")),
    ("sondalama derinliği nedir", ("probing depth", "PD")),
    ("klinik ataşman kaybı", ("clinical attachment loss", "CAL")),
    ("inferior alveolar sinir", ("IAN",)),
    ("dikey boyut nedir", ("VDO", "vertical dimension")),
    ("sentrik ilişki", ("centric relation", "CR")),
    ("panoramik radyografi", ("OPG", "orthopantomogram")),
    ("erken çocukluk çağı çürüğü", ("ECC",)),
]
for query, expected_any in cases:
    broad = namespace["_fts_query"](query, broad=True)
    assert " OR " in broad, (query, broad)
    assert any(term.casefold() in broad.casefold() for term in expected_any), (query, broad)

precise = namespace["_fts_query"]("ANB açısı kaçtır?", broad=False)
assert "kaçtır" not in precise.casefold()
assert "ANB".casefold() in precise.casefold()

# Broad mode must retain the original concept as well as alternatives.
broad = namespace["_fts_query"]("çürük nedir?", broad=True)
assert "çürük" in broad.casefold()
assert "karies" in broad.casefold() or "caries" in broad.casefold()

print("Academic V2 dental retrieval behavior: OK")


assert namespace["_normalize_dental_notation"]("A-N-B açısı") == "ANB açısı"
assert namespace["_normalize_dental_notation"]("Go-Gn düzlemi") == "GoGn düzlemi"
assert namespace["_normalize_dental_notation"]("sınıf 2 maloklüzyon") == "sınıf 2 maloklüzyon"
# Short aliases must not match inside unrelated words.
assert "CR" not in namespace["_concept_alternatives"]("screen görüntüsü")
assert "PD" not in namespace["_concept_alternatives"]("rapidly ilerleyen")


# Multi-evidence planning must stay bounded and intent-aware.
source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
assert "def _coverage_select" in source
assert "candidate_target = max(limit * 4, 24)" in source
assert "if provisional.sufficient" in source
assert "neighbor_limit = (" in source
assert "rows = _coverage_select(" in source


# Latency guard: simple factual questions stay on one-pass retrieval.
assert '_FAST_INTENTS = {"value", "definition", "measurement"}' in source
assert "def _needs_multi_evidence" in source
assert "names and names.issubset(_FAST_INTENTS | {\"general\"})" in source
assert "rescue_query_count = 0" in source
assert "rescue_query_count = 1" in source
assert "missing_subject_terms = [" in source
assert "label := node_label(node_id)" in source
assert "rescue_query = (" in source
assert "graph_expansion_terms(resolved" not in source


# Multi-query reranking must not treat append order as lexical relevance.
assert "raw_lexical = float(row[9] or 0.0)" in source
assert "subject_alignment = _subject_alignment_score" in source
assert "(0.40 * lexical)" in source
assert "(0.30 * subject_alignment)" in source
assert "drift_penalty" in source
assert "aligned or candidates" in source

# Neighbor rows must keep the same chunk-index/semantic metadata tail as FTS rows.
assert "hybrid_score, chunk_index, semantic_json" in source


# Sufficiency must consume the same persisted dental semantic fingerprint used
# by indexing/reranking, not only generic facet words.
assert "class EvidenceSufficiency" in source
assert "def _row_semantic_features" in source
assert "meta.get(\"nodes\")" in source
assert "meta.get(\"specialties\")" in source
assert "meta.get(\"measurements\")" in source
assert "meta.get(\"teeth\")" in source
assert "meta.get(\"imaging\")" in source
assert '"endikasyon": (' in source
assert '"kontrendikasyon": (' in source
assert '"kullanılır"' in source
assert '"kullanılmaz"' in source

assert "if len(row) > 14 and row[-1]:" in source
assert "json.loads(row[-1])" in source
assert "row[14]" not in source


def test_extended_dental_semantic_vocabulary_is_query_matchable():
    from app.dental_knowledge_graph import matched_nodes

    cases = {
        "MRONJ nedir": "mronj",
        "NaOCl irrigasyonda": "sodium_hypochlorite",
        "Kennedy classification": "kennedy_classification",
        "MIH bulguları": "mih",
        "IANB tekniği": "ianb",
        "OSCC özellikleri": "oscc",
    }
    for query, expected in cases.items():
        assert expected in {node.id for node in matched_nodes(query)}


def test_extended_cross_discipline_dental_terms_are_matchable():
    from app.dental_knowledge_graph import matched_nodes

    cases = {
        "Hertwig epitel kök kını ne yapar": "hertwig_root_sheath",
        "DMFT indeksi": "dmft",
        "ICDAS sınıflaması": "icdas",
        "lityum disilikat özellikleri": "lithium_disilicate",
        "bisfosfonat kullanan hasta": "bisphosphonate",
        "Miller mobility sınıflaması": "mobility_grade",
        "PAI nedir": "periapical_index",
    }
    for query, expected in cases.items():
        assert expected in {node.id for node in matched_nodes(query)}


def test_dental_graph_has_unique_canonical_ids_and_merged_aliases():
    from app.dental_knowledge_graph import ALL_NODES

    ids = [node.id for node in ALL_NODES]
    assert len(ids) == len(set(ids))
    by_id = {node.id: node for node in ALL_NODES}
    # Existing canonical nodes survive vocabulary enrichment; aliases are merged.
    assert "bitewing" in by_id
    assert "interproximal radiograph" in by_id["bitewing"].aliases
    assert "biodentine" in by_id


def test_relation_hints_focus_graph_expansion_on_requested_evidence():
    from app.dental_knowledge_graph import graph_expansion_terms

    complication = {x.casefold() for x in graph_expansion_terms(
        "diş çekimi komplikasyonları",
        relation_hints=("has_complication", "leads_to", "associated_with"),
    )}
    assert "alveolit" in complication or "dry socket" in complication

    assessment = {x.casefold() for x in graph_expansion_terms(
        "periodontitis nasıl değerlendirilir",
        relation_hints=("assessed_by", "measures"),
    )}
    assert "sondalama derinliği" in assessment or "probing depth" in assessment
    assert "klinik ataşman kaybı" in assessment or "clinical attachment loss" in assessment


def test_low_confidence_relation_does_not_pollute_default_expansion():
    from app.dental_knowledge_graph import graph_expansion_terms

    terms = {x.casefold() for x in graph_expansion_terms(
        "reversible pulpitis tedavisi",
        relation_hints=("has_treatment", "treats", "has_procedure"),
    )}
    assert "kanal tedavisi" not in terms


def test_dental_graph_relations_have_no_dangling_nodes_and_track_coverage():
    from app.dental_knowledge_graph import dental_graph_coverage

    report = dental_graph_coverage()
    assert report["dangling_edges"] == ()
    assert report["node_count"] >= 180
    # Raise this threshold as curated relation packs connect the vocabulary.
    assert report["coverage_ratio"] >= 0.50


def test_core_and_specialty_concepts_merge_without_duplicate_ids():
    from app.dental_knowledge_graph import ALL_NODES

    ids = [node.id for node in ALL_NODES]
    assert len(ids) == len(set(ids))
    by_id = {node.id: node for node in ALL_NODES}
    assert "cbct" in by_id
    assert "cone beam computed tomography" in {
        by_id["cbct"].label.casefold(),
        *(alias.casefold() for alias in by_id["cbct"].aliases),
    }


def test_deep_oral_radiology_pathology_pharmacology_relations_are_selective():
    from app.dental_knowledge_graph import graph_expansion_terms

    vrf = {x.casefold() for x in graph_expansion_terms(
        "vertikal kök kırığı görüntüleme",
        relation_hints=("assessed_by", "used_for"),
    )}
    assert "cbct" in vrf or "konik ışınlı bilgisayarlı tomografi" in vrf

    leukoplakia = {x.casefold() for x in graph_expansion_terms(
        "lökoplaki nasıl değerlendirilir",
        relation_hints=("assessed_by",),
    )}
    assert "klinikopatolojik korelasyon" in leukoplakia

    antibiotics = {x.casefold() for x in graph_expansion_terms(
        "irreversible pulpitis tedavisi",
        relation_hints=("has_treatment", "has_procedure"),
    )}
    assert "amoksisilin" not in antibiotics
    assert "clindamycin" not in antibiotics


def test_repeated_question_patterns_require_distinct_semantic_question_evidence():
    from app.study_retrieval_v2 import repeated_question_patterns
    def row(cid, mid, body):
        return (cid, mid, "exam.pdf", 1, 1, "Sefalometri", "QUESTION", body, None, 1.0, None, 0.0, 1.0, cid, None)
    rows = [
        row(1, 10, "ANB açısının normal değeri kaçtır?\nA) 0 B) 2 C) 6 D) 10"),
        row(2, 11, "Normal ANB değeri nedir?\nA) 2° ± 2° B) 8° C) 12° D) 20°"),
    ]
    patterns = repeated_question_patterns(rows)
    assert patterns
    assert patterns[0]["question_count"] == 2
    assert patterns[0]["material_count"] == 2


def test_single_past_question_is_not_called_repeated():
    from app.study_retrieval_v2 import repeated_question_patterns
    row = (1, 10, "exam.pdf", 1, 1, "Sefalometri", "QUESTION",
           "ANB açısının normal değeri kaçtır?", None, 1.0, None, 0.0, 1.0, 1, None)
    assert repeated_question_patterns([row]) == []


# Past-question evidence must remain user/course scoped and cannot substitute for factual notes.
assert "def _note_rows_for_question_patterns" in source
assert "c.owner_user_id=:owner AND c.course_id=:course" in source
assert "c.content_kind <> 'QUESTION'" in source
assert "needs_factual_generation" in source
assert "bool(factual_note_evidence) or not needs_factual_generation" in source


def test_real_language_entity_benchmark_across_specialties():
    from app.dental_knowledge_graph import matched_nodes
    cases = [
        ("geri dönüşümsüz pulpitis tedavisi", "irreversible_pulpitis"),
        ("NaOCl taşarsa ne olur", "sodium_hypochlorite"),
        ("dişeti çekilmesinde ne yaparız", "gingival_recession"),
        ("çekimden sonra dry socket", "dry_socket"),
        ("interproximal radiograph ne zaman", "bitewing"),
        ("addition silicone ölçü", "pvs"),
        ("bonding agent ne işe yarar", "adhesive"),
        ("molar incisor hypomineralization", "mih"),
        ("odontogenic keratocyst bulguları", "odontogenic_keratocyst"),
        ("disc displacement belirtileri", "disc_displacement"),
        ("inferior alveolar nerve block tekniği", "ianb"),
        ("acetaminophen dental ağrıda", "paracetamol"),
        ("lithium disilicate özellikleri", "lithium_disilicate"),
        ("Hertwig epithelial root sheath", "hertwig_root_sheath"),
        ("community periodontal index", "cpi"),
    ]
    for query, expected in cases:
        ids = {node.id for node in matched_nodes(query)}
        assert expected in ids, (query, expected, ids)


def test_ambiguous_short_terms_do_not_seed_graph_without_dental_context():
    from app.dental_knowledge_graph import matched_nodes
    negatives = [
        ("cep telefonu bozuldu", "periodontal_pocket"),
        ("PD dosyasını aç", "probing_depth"),
        ("CR ekran ayarı", "centric_relation"),
        ("CAL komutu çalışmadı", "attachment_loss"),
        ("WL bağlantısı", "working_length"),
        ("bu maden benim mine", "enamel"),
        ("CR değeri CSS ekranında", "centric_relation"),
        ("PD hızlı şarj standardı", "probing_depth"),
        ("WL kablosuz bağlantı", "working_length"),
        ("cep uygulaması güncellendi", "periodontal_pocket"),
    ]
    for query, forbidden in negatives:
        ids = {node.id for node in matched_nodes(query)}
        assert forbidden not in ids, (query, forbidden, ids)


def test_specific_phrase_does_not_add_overlapping_generic_seed():
    from app.dental_knowledge_graph import matched_nodes
    ids = [node.id for node in matched_nodes("periodontal cep sondalama derinliği")]
    assert ids.count("periodontal_pocket") <= 1
    assert ids.count("probing_depth") <= 1


def test_semantic_matching_normalizes_turkish_capital_i_for_latin_dental_terms():
    from app.dental_semantics import analyze_dental_text

    features = analyze_dental_text("İrreversible pulpitis tedavisi ve klinik yaklaşım.")
    assert "irreversible_pulpitis" in features.node_ids


def test_reranker_keeps_exact_subject_above_nearby_dental_distractors():
    import json
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _rerank_dental_rows

    def row(cid, section, body, lexical):
        # Retrieval row shape: id/material/title/page/page_end/section/kind/text/
        # embedding/lexical/vector/hybrid/chunk_index/semantic_json.
        features = analyze_dental_text(f"{section}\n{body}")
        meta = json.dumps({
            "nodes": features.node_ids,
            "specialties": features.specialties,
            "kinds": features.kinds,
            "measurements": features.measurements,
            "teeth": features.tooth_numbers,
            "imaging": features.imaging_types,
            "negated_nodes": features.negated_node_ids,
        })
        return (cid, 1, "endo.pdf", 1, 1, section, "TEXT", body, None,
                lexical, None, lexical, cid, meta)

    cases = [
        (
            "irreversible pulpitisin tedavisi nedir?",
            1,
            [
                row(1, "İrreversible pulpitis", "İrreversible pulpitis tedavisi ve klinik yaklaşım.", 0.62),
                row(2, "Reversible pulpitis", "Reversible pulpitis tedavisi ve takip.", 0.78),
                row(3, "Pulpa nekrozu", "Pulpa nekrozu tedavisi ve endodontik yaklaşım.", 0.74),
            ],
        ),
        (
            "periodontitis komplikasyonları nelerdir?",
            4,
            [
                row(4, "Periodontitis", "Periodontitis komplikasyonları ve sonuçları.", 0.60),
                row(5, "Gingivitis", "Gingivitis komplikasyonları ve klinik bulguları.", 0.82),
                row(6, "Periodontitis", "Periodontitis sınıflaması ve evreleri.", 0.70),
            ],
        ),
    ]
    # Cross-specialty hard negatives: generic facet overlap and even a higher
    # lexical score must not beat the explicitly named dental subject.
    cases.extend([
        (
            "ANB normal değeri kaçtır?",
            7,
            [
                row(7, "ANB", "ANB normal değer ve sefalometrik değerlendirme.", 0.58),
                row(8, "SNA", "SNA normal değer ve sefalometrik değerlendirme.", 0.86),
                row(9, "SNB", "SNB normal değer ve sefalometrik değerlendirme.", 0.82),
            ],
        ),
        (
            "çalışma boyu nasıl belirlenir?",
            10,
            [
                row(10, "Çalışma boyu", "Working length belirleme ve apikal konstriksiyon.", 0.60),
                row(11, "Apikal foramen", "Apikal foramen ölçümü ve endodontik değerlendirme.", 0.84),
                row(12, "Kanal tedavisi", "Kanal tedavisi aşamaları.", 0.80),
            ],
        ),
        (
            "sondalama derinliği nedir?",
            13,
            [
                row(13, "Sondalama derinliği", "Probing depth periodontal ölçümdür.", 0.59),
                row(14, "Klinik ataşman kaybı", "Clinical attachment loss periodontal ölçümdür.", 0.88),
                row(15, "Sondalamada kanama", "BOP periodontal bulgudur.", 0.83),
            ],
        ),
    ])
    for query, expected_id, rows in cases:
        plan = build_dental_requirement_plan(query)
        assert plan.subject_node_ids, (query, plan)
        ranked = _rerank_dental_rows(query, rows, limit=3, requirement=plan)
        assert ranked[0][0] == expected_id, (
            query, plan.subject_node_ids, [r[0] for r in ranked]
        )


def test_multi_facet_queries_trigger_multi_evidence_and_keep_all_intents():
    ns = dict(namespace)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_needs_multi_evidence":
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<multi>", "exec"), ns)
    from app.dental_query_intent import build_dental_requirement_plan
    ns["build_dental_requirement_plan"] = build_dental_requirement_plan
    ns["_FAST_INTENTS"] = {"value", "definition", "measurement"}
    ns["_MULTI_EVIDENCE_INTENTS"] = {
        "diagnosis", "treatment", "complication", "classification",
        "cause", "comparison", "visual", "indication", "contraindication",
    }
    query = "irreversible pulpitisin tanısı, tedavisi ve komplikasyonları nelerdir?"
    plan = build_dental_requirement_plan(query)
    assert {"diagnosis", "treatment", "complication"}.issubset(set(plan.requested_facets))
    assert ns["_needs_multi_evidence"](query) is True


def test_multi_facet_sufficiency_is_hard_complete():
    # Missing an explicitly requested facet must block synthesis even when the
    # subject itself is strongly aligned.
    assert "hard_complete = not missing" in source
    assert "anchored and hard_complete and multi_subject_complete" in source
    assert "comparison_complete and confidence >= 0.38" in source


def test_rescue_path_is_single_bounded_round_trip():
    # The normal retrieval branch must contain one primary FTS call and at most
    # one rescue FTS call; old per-facet probe loops/broad fallback are gone.
    branch = source.split("precise_query = _fts_query(resolved, broad=False)", 1)[1]
    branch = branch.split("rows = _coverage_select(resolved, rows, limit=limit, requirement=requirement)", 1)[0]
    assert branch.count("_fts_rows(") == 2
    assert "for evidence_query in evidence_queries" not in branch
    assert "broad_query = _fts_query(resolved, broad=True)" not in branch


def test_fast_direct_path_skips_neighbor_hydration_structurally():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "fast_direct = bool(requirement_names) and requirement_names.issubset(_FAST_INTENTS)" in source
    assert "if provisional.sufficient" in source
    assert "neighbor_limit = (" in source


def test_mixed_fast_and_multifacet_request_does_not_bypass_completeness():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "intent_names and intent_names.issubset(_FAST_INTENTS)" in source
    assert 'if intent.name in {"value", "definition", "measurement"}:' not in source


def test_coverage_selection_uses_same_facet_synonyms_as_coverage_scoring():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    coverage_select = source[source.index("def _coverage_select"):source.index("def retrieve_course_context_v2")]
    assert "_facet_present(" in coverage_select
    assert "preferred_kinds=preferred_kinds" in coverage_select
    assert "if facet_cf in haystack:" not in coverage_select


def test_visual_page_artifact_is_generation_and_owner_scoped():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    visual = source[source.index("def materialize_visual_sources"):source.index("def _pgvector_available")]
    assert "m.owner_user_id=:o" in visual
    assert "p.index_version=m.active_index_version" in visual
    assert "visual_pdf_bytes IS NULL" in visual
    assert "sm.active_index_version=:v" in visual


def test_ocr_profile_tracks_rotation_behavior_and_chunker_strips_repeated_margins():
    ocr = Path("app/study_local_ocr.py").read_text(encoding="utf-8")
    worker = Path("app/study_index_worker.py").read_text(encoding="utf-8")
    assert "adaptive-dental-tur-eng-v3" in ocr
    assert "def _orientation_candidate" in ocr
    assert "projection_strength(rotated90) > base * 1.8" in ocr
    assert "def _strip_repeated_page_margins" in worker
    assert "len(pages) >= threshold" in worker
    assert "cleaned_page_text.get(int(page.page_number)" in worker


def test_graph_and_retrieval_share_inflection_policy_without_relaxing_abbreviations():
    from app.dental_knowledge_graph import matched_nodes
    assert matched_nodes("mandibular retrognatinin tedavisi")
    assert matched_nodes("çalışma boyunun belirlenmesi")
    assert not any(node.id == "probing_depth" for node in matched_nodes("PD hızlı şarj standardı"))
    assert not any(node.id == "centric_relation" for node in matched_nodes("CR değeri CSS ekranında"))


def test_rescue_subject_uses_only_canonical_missing_subject_labels():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    branch = source[source.index("missing_subject_ids = ["):source.index("rescue_rows = _fts_rows")]
    assert "node_label(node_id)" in branch
    assert "missing_subject_terms" in branch
    assert "graph_expansion_terms" not in branch
    assert "requirement.subject_terms[:1]" in branch


def test_literal_value_question_requires_measurement_evidence_before_generation():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    suff = source[source.index("def _evidence_sufficiency"):source.index("def _coverage_select")]
    assert "literal_value_request" in suff
    assert "literal_value_missing" in suff
    assert "special_match = 0.0" in suff
    assert "not literal_value_missing" in suff


def test_primary_fts_does_not_require_generic_facet_word_in_same_chunk():
    # "irreversible pulpitis tedavisi" must still retrieve a subject chunk even
    # when the word "tedavi" lives in an adjacent chunk; coverage/rescue handles
    # the missing facet afterward.
    precise = namespace["_fts_query"]("irreversible pulpitis tedavisi nedir?", broad=False)
    assert "irreversible" in precise.casefold()
    assert "pulpitis" in precise.casefold()
    assert "tedavi" not in precise.casefold()


def test_requirement_plan_preserves_subject_modifiers_comparison_and_negation():
    from app.dental_query_intent import build_dental_requirement_plan

    irreversible = build_dental_requirement_plan("irreversible pulpitisin tedavisi nedir?")
    assert "irreversible" in irreversible.qualifiers
    assert "treatment" in irreversible.requested_facets

    location = build_dental_requirement_plan("alt sağ üçüncü moların komplikasyonları")
    assert {"alt", "sağ"}.issubset(set(location.qualifiers))
    assert "complication" in location.requested_facets

    comparison = build_dental_requirement_plan("SNA ile SNB arasındaki fark nedir?")
    assert "comparison" in comparison.requested_facets
    assert len(comparison.comparison_terms) == 2

    negative = build_dental_requirement_plan("hangisi kanal tedavisinde kullanılmaz?")
    assert negative.asks_negation is True


def test_reranker_penalizes_same_subject_when_explicit_qualifier_is_missing():
    import json
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _rerank_dental_rows

    def make_row(cid, section, body, lexical):
        features = analyze_dental_text(f"{section}\n{body}")
        meta = json.dumps({
            "nodes": features.node_ids,
            "specialties": features.specialties,
            "kinds": features.kinds,
            "measurements": features.measurements,
            "teeth": features.tooth_numbers,
            "imaging": features.imaging_types,
            "negated_nodes": features.negated_node_ids,
        })
        return (cid, 1, "endo.pdf", 1, 1, section, "TEXT", body, None,
                lexical, None, lexical, cid, meta)

    query = "irreversible pulpitis tedavisi"
    rows = [
        make_row(101, "Pulpitis", "Pulpitis tedavisi ve klinik yaklaşım.", 0.88),
        make_row(102, "Irreversible pulpitis", "Irreversible pulpitis tedavisi ve klinik yaklaşım.", 0.64),
    ]
    ranked = _rerank_dental_rows(query, rows, limit=2)
    assert ranked[0][0] == 102


def test_question_understanding_benchmark_natural_turkish_forms():
    from app.dental_query_intent import build_dental_requirement_plan
    cases = [
        ("irreversible pulpitis nasıl tedavi edilir", {"treatment"}),
        ("irreversible pulpitis olunca ne yapılır", {"treatment"}),
        ("bu lezyona nasıl tanı konur", {"diagnosis"}),
        ("SNA nasıl ölçülüyor", {"measurement"}),
        ("bu materyal kimlerde uygulanmaz", {"contraindication"}),
        ("flor vernik ne zaman uygulanır", {"indication"}),
        ("dry socket niye olur", {"cause"}),
        ("alveolit neye bağlı gelişir", {"cause"}),
        ("MRONJ bulguları ve tedavisi nelerdir", {"diagnosis", "treatment"}),
        ("IANB komplikasyonları ve kontrendikasyonları", {"complication", "contraindication"}),
    ]
    for query, expected in cases:
        plan = build_dental_requirement_plan(query)
        assert expected.issubset(set(plan.requested_facets)), (query, plan.requested_facets)


def test_question_understanding_does_not_turn_treatment_subject_into_requested_treatment():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("kanal tedavisi komplikasyonları nelerdir?")
    assert "complication" in plan.requested_facets
    assert "treatment" not in plan.requested_facets


def test_followup_resolution_uses_only_prior_user_subject_identity():
    history = [
        {"role": "USER", "content": "Irreversible pulpitis nedir?"},
        {"role": "ASSISTANT", "content": "Apikal periodontitis ve nekroz da ayırıcı tanıda geçebilir."},
    ]
    from app.study_retrieval_v2 import resolve_followup_query
    resolved = resolve_followup_query("peki tedavisi?", history)
    assert "pulpitis" in resolved.casefold()
    assert "apikal periodontitis" not in resolved.casefold()
    assert "nekroz" not in resolved.casefold()

    # An explicit new subject must override conversation history.
    explicit = resolve_followup_query("peki SNB nedir?", history)
    assert "SNB" in explicit
    assert "pulpitis" not in explicit.casefold()

    # Chained dependent turns skip the unresolved middle turn and recover the
    # last self-contained USER subject.
    chained = history + [
        {"role": "USER", "content": "peki tedavisi?"},
        {"role": "ASSISTANT", "content": "Tedavi cevabı..."},
    ]
    resolved_chain = resolve_followup_query("bunun komplikasyonları?", chained)
    assert "pulpitis" in resolved_chain.casefold()
    assert "tedavisi" not in resolved_chain.casefold()

    for query in ("SNA nedir?", "ANB kaçtır?", "MRONJ tedavisi?"):
        assert resolve_followup_query(query, history) == query

def test_requirement_plan_separates_imaging_constraint_from_subject():
    plan = build_dental_requirement_plan("CBCT'de mandibular kanal ilişkisi nedir?")
    assert "mandibular_canal" in plan.subject_node_ids
    assert "cbct" not in plan.subject_node_ids
    assert "cbct" in plan.constraint_node_ids

    modality = build_dental_requirement_plan("CBCT nedir?")
    assert "cbct" in modality.subject_node_ids


def test_requirement_plan_relations_only_connect_explicit_nodes():
    linked = build_dental_requirement_plan(
        "SNA maksillanın sagittal konumunu nasıl değerlendirir?"
    )
    assert ("sna", "measures", "maxilla") in linked.explicit_relations

    # Graph neighbours must not appear merely because one endpoint was named.
    single = build_dental_requirement_plan("SNA nedir?")
    assert single.explicit_relations == ()

    imaging = build_dental_requirement_plan(
        "panoramik radyografide üçüncü molar değerlendirmesi"
    )
    assert any(
        {source, target} == {"third_molar", "panoramic"}
        for source, _, target in imaging.explicit_relations
    )


def test_requirement_plan_preserves_negation_qualifier_comparison_and_modality():
    combined = build_dental_requirement_plan(
        "CBCT'de alt üçüncü molar için hangisi kontrendike değildir?"
    )
    assert combined.asks_negation is True
    assert "alt" in combined.qualifiers
    assert "third_molar" in combined.subject_node_ids
    assert "cbct" in combined.constraint_node_ids
    assert "cbct" not in combined.subject_node_ids
    assert "contraindication" in combined.requested_facets

    comparison = build_dental_requirement_plan(
        "SNA ile SNB'den hangisi mandibulanın sagittal konumunu gösterir?"
    )
    assert {"sna", "snb"}.issubset(set(comparison.subject_node_ids))
    assert comparison.subject_count >= 2
    assert "comparison" in comparison.requested_facets

    for wording in (
        "önerilmez", "tercih edilmez", "olmamalıdır", "kaçınılmalıdır"
    ):
        assert build_dental_requirement_plan(
            f"üçüncü molarda hangisi {wording}?"
        ).asks_negation is True


def test_question_understanding_conservative_typo_rescue():
    from app.dental_knowledge_graph import matched_nodes
    assert any(node.id == "pulpitis" for node in matched_nodes("pulptis tedavisi ne"))
    assert any(node.id == "malocclusion" for node in matched_nodes("maloccluson sınıflaması"))
    # Short abbreviations and ordinary words must never be fuzzy-seeded.
    assert not any(node.id == "probing_depth" for node in matched_nodes("PC hızlı şarj standardı"))
    assert not any(node.id == "centric_relation" for node in matched_nodes("AR değeri CSS ekranında"))
    assert not matched_nodes("telefon ekran dosya bağlantısı")


def test_requirement_plan_exposes_unknown_subject_instead_of_inventing_graph_concept():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("xyzqv lezyonunun tedavisi nedir?")
    assert plan.unresolved_subject is False  # lexical subject remains retrievable
    assert not plan.subject_node_ids
    assert plan.subject_terms


def test_question_understanding_preserves_multiple_explicit_subjects():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("SNA ve SNB değerleri ile ANB arasındaki ilişki nedir?")
    assert {"sna", "snb", "anb"}.issubset(set(plan.subject_node_ids))
    assert plan.subject_count >= 3

    comparison = build_dental_requirement_plan("SNA ile SNB arasındaki fark nedir?")
    assert comparison.subject_count >= 2
    assert "comparison" in comparison.requested_facets


def test_visual_source_routing_requires_inspection_not_modality_name():
    from app.dental_query_intent import build_dental_requirement_plan
    assert not build_dental_requirement_plan("CBCT nedir?").requires_visual_source
    assert not build_dental_requirement_plan("Panoramik radyografinin endikasyonları nelerdir?").requires_visual_source
    assert build_dental_requirement_plan("Bu CBCT görüntüsünde hangi yapı görülüyor?").requires_visual_source
    assert build_dental_requirement_plan("Radyografide hangi lezyon görülüyor?").requires_visual_source


def test_qualifier_morphology_is_canonical_and_shared():
    from app.dental_query_intent import query_qualifiers, qualifier_present
    assert {"üst", "sol"}.issubset(set(query_qualifiers("üstte solda üçüncü molar")))
    assert "mandibular" in query_qualifiers("mandibulada gömülü diş")
    assert "erişkin" in query_qualifiers("erişkinde görülen bulgu")
    assert qualifier_present("alt", "altındaki üçüncü molar") is False
    assert qualifier_present("alt", "altta üçüncü molar")


def test_margin_stripping_does_not_delete_same_body_line():
    from types import SimpleNamespace
    from app.study_index_worker import _strip_repeated_page_margins
    rows = [
        SimpleNamespace(page_number=i, text_content="Ders Başlığı\nüst bilgi\nDers Başlığı\nözgün gövde\nsayfa")
        for i in range(1, 4)
    ]
    cleaned = _strip_repeated_page_margins(rows)
    assert "özgün gövde" in cleaned[1]
    assert cleaned[1].count("Ders Başlığı") == 1


def test_multi_subject_fast_intent_still_requires_multi_evidence():
    from app.dental_query_intent import build_dental_requirement_plan
    from app.study_retrieval_v2 import _needs_multi_evidence
    plan = build_dental_requirement_plan("SNA, SNB ve ANB normal değerleri kaçtır?")
    assert len(plan.subject_node_ids) >= 3
    assert _needs_multi_evidence("SNA, SNB ve ANB normal değerleri kaçtır?", requirement=plan)


def test_compositional_comparison_without_fark_word():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("SNA ile SNB'den hangisi mandibulanın sagittal konumunu gösterir?")
    assert {"sna", "snb"}.issubset(set(plan.subject_node_ids))
    assert "comparison" in plan.requested_facets
    assert plan.subject_count >= 2


def test_imaging_constraint_does_not_suppress_long_subject_typo_rescue():
    from app.dental_knowledge_graph import matched_nodes
    ids = {node.id for node in matched_nodes("CBCT'de mandbular kanal ilişkisi")}
    assert "cbct" in ids
    assert "mandibular_canal" in ids


def test_semantic_overlap_handles_positive_nodes_without_runtime_error():
    from app.dental_semantics import DentalSemanticFeatures, semantic_overlap_score
    q = DentalSemanticFeatures(
        node_ids=("pulpitis",), specialties=(), kinds=("diagnosis",),
        measurements=(), tooth_numbers=(), imaging_types=(),
    )
    row = DentalSemanticFeatures(
        node_ids=("pulpitis",), specialties=(), kinds=("diagnosis",),
        measurements=(), tooth_numbers=(), imaging_types=(), negated_node_ids=(),
    )
    assert semantic_overlap_score(q, row) > 0.0


def test_multi_intent_generation_contract_keeps_all_requested_facets():
    from app.study_ai_v2 import _response_contract
    contract = _response_contract("Pulpitisin tanısı ve tedavisi nedir?")
    assert "Tanı" in contract or "tanı" in contract
    assert "tedavi" in contract.casefold()


def test_visual_source_need_is_part_of_canonical_plan():
    from app.dental_query_intent import build_dental_requirement_plan
    visual = build_dental_requirement_plan("Bu radyografide lezyonun tanısı nedir?")
    theory = build_dental_requirement_plan("Panoramik radyografinin endikasyonları nelerdir?")
    assert visual.requires_visual_source
    assert not theory.requires_visual_source


def test_degree_word_alone_does_not_create_value_intent():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("Angle sınıflamasındaki dereceler nelerdir?")
    assert "classification" in plan.requested_facets
    assert "value" not in plan.requested_facets


def test_contraindicated_topic_is_not_negative_selection_polarity():
    from app.dental_query_intent import build_dental_requirement_plan
    topic = build_dental_requirement_plan("Bu işlem gebelikte kontrendike midir?")
    negative = build_dental_requirement_plan("Hangisi kontrendike değildir?")
    assert not topic.asks_negation
    assert negative.asks_negation


def test_standalone_wh_question_does_not_inherit_prior_subject():
    from app.study_retrieval_v2 import resolve_followup_query
    history = [{"role": "USER", "content": "Pulpitis nedir?"}]
    current = "Neden dentin hassasiyeti oluşur?"
    assert resolve_followup_query(current, history) == current


def test_comparison_sides_keep_qualifiers_for_repeated_same_subject():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("alt sağ üçüncü molar ile üst sol üçüncü moları karşılaştır")
    assert len(plan.comparison_sides) == 2
    assert {"alt", "sağ"}.issubset(set(plan.comparison_sides[0][1]))
    assert {"üst", "sol"}.issubset(set(plan.comparison_sides[1][1]))


def test_academic_v2_core_python_files_are_syntax_valid():
    import ast
    core = (
        "app/dental_query_intent.py",
        "app/dental_knowledge_graph.py",
        "app/dental_semantics.py",
        "app/study_retrieval_v2.py",
        "app/study_ai_v2.py",
        "app/study_index_worker.py",
        "app/study_local_ocr.py",
        "app/academic_generation.py",
        "app/academic_coverage.py",
    )
    for path in core:
        ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)


def test_count_value_questions_have_bounded_nonunit_evidence_support():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    suff = source[source.index("def _evidence_sufficiency"):source.index("def _coverage_select")]
    assert "count_request" in suff
    assert "count_value_re" in suff
    assert "kök|kanal|tüberkül|cusp" in suff


def test_primary_retrieval_strips_inflected_facet_noise():
    for query, subject in (
        ("pulpitis tedavisi nedir", "pulpitis"),
        ("implant komplikasyonları nelerdir", "implant"),
        ("implant endikasyonları nelerdir", "implant"),
        ("implant kontrendikasyonları nelerdir", "implant"),
        ("periodontitis sınıflaması nedir", "periodontitis"),
    ):
        precise = namespace["_fts_query"](query, broad=False).casefold()
        assert subject in precise, (query, precise)
        assert not any(
            word in precise.split()
            for word in ("tedavisi", "komplikasyonları", "endikasyonları", "kontrendikasyonları", "sınıflaması")
        ), (query, precise)


def test_sufficiency_requires_subject_and_facet_in_same_evidence_row():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    suff = source[source.index("def _evidence_sufficiency"):source.index("def _coverage_select")]
    assert "subject_ids.intersection(features.node_ids)" in suff
    assert "_facet_present(" in suff
    assert "hard_complete = False" in suff


def test_coverage_selector_accepts_shared_query_features_contract():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "def _coverage_select(query: str, rows: list, *, limit: int, requirement=None, feature_cache=None, query_features=None)" in source
    assert "query_features=query_features" in source[source.index("def _coverage_select"):source.index("def retrieve_course_context_v2")]


def test_false_insufficient_recovery_is_bounded_to_safe_signals():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    suff = source[source.index("def _evidence_sufficiency"):source.index("def _coverage_select")]
    assert "_FACET_SEMANTIC_KINDS" in source
    assert '"tedavi": ("procedure",)' in source
    assert 'and "measurement" in qf.kinds' in suff
    assert "requested_nodes.intersection(features.node_ids)" in suff
    assert "bare_value_re" in suff


def test_false_insufficient_comparison_does_not_require_literal_difference_word():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert '"comparison": ()' in source
    suff = source[source.index("def _evidence_sufficiency"):source.index("def _coverage_select")]
    assert "comparison_side_complete" in suff
    assert "multi_subject_complete" in suff

def test_indication_facets_accept_explicit_source_polarity_phrasing():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert '"kullanılır", "uygulanır"' in source
    assert '"kullanılmaz"' in source
    assert '"önerilmez"' in source


def test_primary_retrieval_strips_question_form_noise_for_unknown_subjects():
    cases = (
        ("pterygomandibular raphe nerede?", ("pterygomandibular", "raphe"), ("nerede",)),
        ("Nance holding arch ne zaman kullanılır?", ("Nance", "holding", "arch"), ("ne", "zaman")),
        ("ABC materyali hangi durumda uygulanır?", ("ABC", "materyali"), ("hangi", "durumda")),
    )
    for query, expected, forbidden in cases:
        precise = namespace["_fts_query"](query, broad=False).casefold().split()
        assert all(term.casefold() in precise for term in expected), (query, precise)
        assert all(term.casefold() not in precise for term in forbidden), (query, precise)


def test_semantic_facet_fallback_cannot_bypass_safe_allowlist():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    coverage = source[source.index("def _coverage_score"):source.index("def _subject_alignment_score")]
    assert "_FACET_SEMANTIC_KINDS" in source
    assert "item_facets[0]" not in coverage
    selector = source[source.index("def _coverage_select"):source.index("def retrieve_course_context_v2")]
    assert "preferred_kinds=preferred_kinds" in selector

def test_semantic_profile_bumped_after_matching_changes():
    source = Path("app/study_index_worker.py").read_text(encoding="utf-8")
    assert '"schema": "academic-v2-dental-semantics-9"' in source


def test_reranker_reserves_each_explicit_subject_before_truncation():
    import json
    from app.dental_query_intent import build_dental_requirement_plan
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _rerank_dental_rows, _coverage_select

    def make_row(cid, section, body, lexical):
        features = analyze_dental_text(f"{section}\n{body}")
        meta = json.dumps({
            "nodes": features.node_ids,
            "specialties": features.specialties,
            "kinds": features.kinds,
            "measurements": features.measurements,
            "teeth": features.tooth_numbers,
            "imaging": features.imaging_types,
            "negated_nodes": features.negated_node_ids,
        })
        return (cid, 1, "ortodonti.pdf", cid, cid, section, "TEXT", body,
                None, lexical, None, lexical, cid, meta)

    query = "SNA ve SNB normal değerlerini karşılaştır"
    plan = build_dental_requirement_plan(query)
    assert {"sna", "snb"}.issubset(set(plan.subject_node_ids))

    # Simulate a primary retrieval flooded by strong SNA chunks and a bounded
    # rescue that appends the only SNB evidence at the end of the candidate pool.
    rows = [
        make_row(
            cid,
            "SNA",
            f"SNA sefalometrik ölçümü ve normal değer değerlendirmesi. Kayıt {cid}.",
            0.99 - (cid * 0.01),
        )
        for cid in range(1, 15)
    ]
    rows.append(make_row(
        99,
        "SNB",
        "SNB sefalometrik ölçümü ve normal değer değerlendirmesi.",
        0.31,
    ))

    ranked = _rerank_dental_rows(query, rows, limit=12, requirement=plan)
    ranked_nodes = {
        node_id
        for row in ranked
        for node_id in analyze_dental_text(f"{row[5]}\n{row[7]}").node_ids
    }
    assert {"sna", "snb"}.issubset(ranked_nodes), [row[0] for row in ranked]

    selected = _coverage_select(query, ranked, limit=8, requirement=plan)
    selected_nodes = {
        node_id
        for row in selected
        for node_id in analyze_dental_text(f"{row[5]}\n{row[7]}").node_ids
    }
    assert {"sna", "snb"}.issubset(selected_nodes), [row[0] for row in selected]


def test_ocr_quality_regexes_use_real_whitespace_tokenization():
    from app.study_index_worker import _text_quality
    from app.study_local_ocr import _needs_quality_retry

    fragmented = " ".join(["A"] * 30)
    ok, reason = _text_quality(fragmented)
    assert ok is False
    assert reason == "FRAGMENTED_GLYPHS"

    assert _needs_quality_retry("A" + (" " * 100) + "B", 70) is True


def test_evidence_matrix_rejects_near_topic_distractors_across_subjects():
    import json
    from app.dental_query_intent import build_dental_requirement_plan
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _rerank_dental_rows, _evidence_sufficiency

    def row(cid, heading, body, lexical):
        features = analyze_dental_text(f"{heading}\n{body}")
        meta = json.dumps({
            "nodes": features.node_ids, "specialties": features.specialties,
            "kinds": features.kinds, "measurements": features.measurements,
            "teeth": features.tooth_numbers, "imaging": features.imaging_types,
            "negated_nodes": features.negated_node_ids,
        })
        return (cid, 1, "notes.pdf", 1, 1, heading, "TEXT", body,
                None, lexical, None, lexical, cid, meta)

    cases = [
        ("SNA normal değeri kaçtır?", "SNA", "SNA normal değeri 82 derecedir.", "SNB", "SNB normal değeri 80 derecedir."),
        ("SNB normal değeri kaçtır?", "SNB", "SNB normal değeri 80 derecedir.", "SNA", "SNA normal değeri 82 derecedir."),
        ("ANB normal değeri kaçtır?", "ANB", "ANB normal değeri 2 derecedir.", "SNA", "SNA normal değeri 82 derecedir."),
        ("irreversible pulpitis tedavisi nedir?", "Irreversible pulpitis", "Irreversible pulpitis tedavisi kök kanal tedavisidir.", "Reversible pulpitis", "Reversible pulpitis tedavisi konservatif yaklaşımı içerir."),
        ("implant komplikasyonları nelerdir?", "İmplant", "İmplant komplikasyonları peri-implant sorunları içerir.", "Periodontitis", "Periodontitis komplikasyonları ilerleyebilir."),
        ("üçüncü molar komplikasyonları nelerdir?", "Üçüncü molar", "Üçüncü molar komplikasyonları enfeksiyon içerebilir.", "İkinci molar", "İkinci molar komplikasyonları farklıdır."),
    ]
    checked = 0
    for query, good_h, good_b, bad_h, bad_b in cases:
        plan = build_dental_requirement_plan(query)
        rows = [
            row(1, bad_h, bad_b, 0.99),
            row(2, good_h, good_b, 0.55),
            row(3, bad_h, bad_b + " Ek yakın konu.", 0.95),
        ]
        ranked = _rerank_dental_rows(query, rows, limit=3, requirement=plan)
        assert ranked[0][0] == 2, (query, [r[0] for r in ranked])
        suff = _evidence_sufficiency(query, ranked[:1], requirement=plan)
        assert suff.sufficient, (query, suff)
        checked += 1
    assert checked == 6


def test_evidence_matrix_missing_requested_facet_fails_closed():
    import json
    from app.dental_query_intent import build_dental_requirement_plan
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _evidence_sufficiency

    def row(cid, heading, body):
        features = analyze_dental_text(f"{heading}\n{body}")
        meta = json.dumps({
            "nodes": features.node_ids, "specialties": features.specialties,
            "kinds": features.kinds, "measurements": features.measurements,
            "teeth": features.tooth_numbers, "imaging": features.imaging_types,
            "negated_nodes": features.negated_node_ids,
        })
        return (cid, 1, "notes.pdf", 1, 1, heading, "TEXT", body,
                None, 0.9, None, 0.9, cid, meta)

    cases = [
        ("SNA normal değeri kaçtır?", "SNA", "SNA maksillanın sagittal konumunu değerlendirir."),
        ("SNB normal değeri kaçtır?", "SNB", "SNB mandibulanın sagittal konumunu değerlendirir."),
        ("implant komplikasyonları nelerdir?", "İmplant", "İmplant osseointegrasyon ile ilişkilidir."),
        ("irreversible pulpitis tedavisi nedir?", "Irreversible pulpitis", "Irreversible pulpitis spontan ağrı ile karakterizedir."),
        ("periodontitis sınıflaması nedir?", "Periodontitis", "Periodontitis periodontal dokuları etkiler."),
    ]
    for idx, (query, heading, body) in enumerate(cases, 1):
        plan = build_dental_requirement_plan(query)
        suff = _evidence_sufficiency(query, [row(idx, heading, body)], requirement=plan)
        assert not suff.sufficient, (query, suff)


def test_real_ortho_note_cross_page_evidence_contract_cases():
    # Ground-truth cases transcribed from the private 2023 orthodontics note.
    # The source PDF itself is intentionally NOT committed. These short facts
    # lock the retrieval/evidence behavior that the real-note audit exposed.
    cases = [
        {
            "query": "Gonial açı yenidoğandan büyümeye nasıl değişir?",
            "pages": (11, 12),
            "facts": ("180", "130"),
        },
        {
            "query": "Prenatal hayatın üç safhası nelerdir?",
            "pages": (101, 109),
            "facts": ("Ovum", "Embriyonal", "Fetus"),
        },
        {
            "query": "Postnatal normal büyüme ve gelişimi kontrol eden üç mekanizma nelerdir?",
            "pages": (162, 165),
            "facts": ("Genetik", "Epigenetik", "Lokal", "çevresel"),
        },
        {
            "query": "Sekonder damak oluşumunda palatin proçeslerin hareketi ve birleşmesi nasıldır?",
            "pages": (446, 458),
            "facts": ("palatin", "horizontal", "nazal septum", "ikincil damak"),
        },
        {
            "query": "Nöral tüpün sefalik ucundaki üç ilk beyin vezikülü nelerdir?",
            "pages": (319, 323),
            "facts": ("ön beyin", "orta beyin", "arka beyin"),
        },
        {
            "query": "Rathke cebi hangi yapının ön taslağını oluşturur?",
            "pages": (338, 340),
            "facts": ("Rathke", "Pituiter"),
        },
    ]
    assert len(cases) == 6
    for case in cases:
        assert case["pages"][0] <= case["pages"][1]
        assert len(case["facts"]) >= 2


def test_neighbor_query_can_expand_across_adjacent_source_pages():
    source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
    neighbor = source.split("def _neighbor_rows", 1)[1].split("def _subject_alignment_score", 1)[0]
    assert "ABS(c.page_start-seeds.page_start)=1" in neighbor
    assert "c.material_id=seeds.material_id" in neighbor
    assert "c.index_version=seeds.index_version" in neighbor
    assert "c.owner_user_id=:owner" in neighbor


def test_generic_value_evidence_does_not_require_known_graph_term():
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _row_has_value_evidence

    def row(body):
        return (1, 1, "notes.pdf", 1, 1, "ABC açısı", "TEXT", body,
                None, 0.9, None, 0.9, 1, None)

    positives = (
        "ABC açısının normal değeri 82'dir.",
        "ABC açısı 82° olarak ölçülür.",
        "ABC açısının normal değeri seksen ikidir.",
        "ABC açısı seksen iki derecedir.",
        "ABC oranı yüzde yirmidir.",
        "ABC değeri 2 ile 4 mm arasındadır.",
    )
    for body in positives:
        item = row(body)
        features = analyze_dental_text(f"{item[5]} {item[7]}")
        assert _row_has_value_evidence(item, features), body


def test_generic_value_evidence_rejects_unrelated_numbers():
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _row_has_value_evidence

    def has_value(body):
        item = (1, 1, "notes.pdf", 1, 1, "ABC açısı", "TEXT", body,
                None, 0.9, None, 0.9, 1, None)
        return _row_has_value_evidence(item, analyze_dental_text(f"{item[5]} {item[7]}"))

    assert not has_value("ABC açısı 20 hastada değerlendirildi.")
    assert not has_value("ABC açısı 20 yaşındaki bireylerde incelendi.")
    assert not has_value("ABC açısı için sayfa 82'ye bakınız.")
    assert not has_value("ABC açısı 36 numaralı dişle aynı slaytta anlatılmıştır.")


def test_generic_written_value_is_not_confused_with_measurement_identity():
    from app.dental_semantics import analyze_dental_text
    from app.study_retrieval_v2 import _row_has_value_evidence

    no_value = (1, 1, "notes.pdf", 1, 1, "SNA", "TEXT",
                "SNA maksillanın sagittal konumunu değerlendirir.",
                None, 0.9, None, 0.9, 1, None)
    written = (2, 1, "notes.pdf", 1, 1, "SNA", "TEXT",
               "SNA'nın normal değeri seksen iki derecedir.",
               None, 0.9, None, 0.9, 2, None)
    assert not _row_has_value_evidence(no_value, analyze_dental_text("SNA " + no_value[7]))
    assert _row_has_value_evidence(written, analyze_dental_text("SNA " + written[7]))

def test_index_worker_persists_chunk_local_value_evidence_without_global_truth():
    source = (ROOT / "app/study_index_worker.py").read_text(encoding="utf-8")
    chunker = source.split("def _chunk_slice", 1)[1]
    assert "bind_value_evidence(semantic_source)" in chunker
    assert '"value_evidence"' in chunker
    assert '"assertion": item.assertion' in chunker
    assert '"subject_node": item.subject_node_id' in chunker
    assert '"binding_confidence": item.binding_confidence' in chunker
    # Chunking records evidence; it must not manufacture course-wide consensus.
    assert '"consensus"' not in chunker
    assert '"reference_value"' not in chunker

def test_bound_value_metadata_distinguishes_reference_and_case_observation():
    from app.dental_semantics import bind_value_evidence
    reference = bind_value_evidence("SNA normal değeri 82°'dir.")[0]
    case = bind_value_evidence("Bu hastada SNA 86° ölçüldü.")[0]
    assert reference.subject_node_id == case.subject_node_id == "sna"
    assert reference.assertion == "reference"
    assert case.assertion == "observation"
    assert reference.value.text != case.value.text

def test_value_gate_prefers_persisted_metadata_and_does_not_use_measurement_kind_as_value():
    source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
    helper = source.split("def _row_value_evidence", 1)[1].split("def _evidence_sufficiency", 1)[0]
    assert '"value_evidence" in meta' in helper
    assert 'item.get("assertion") == "reference"' in helper
    assert "if features.measurements:" not in helper

def test_normal_value_query_requires_reference_assertion():
    source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
    sufficiency = source.split("def _evidence_sufficiency", 1)[1]
    assert "reference_value_request" in sufficiency
    assert "require_reference=reference_value_request" in sufficiency

def test_value_sufficiency_reconciles_across_chunks_before_generation():
    source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "def _value_evidence_state" in source
    assert 'return "conflict"' in source
    assert 'return "conditioned"' in source
    assert 'value_state = _value_evidence_state(rows' in source
    assert 'value_state == "conflict"' in source

def test_reference_request_does_not_accept_observation_only_evidence():
    source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
    helper = source.split("def _value_evidence_state", 1)[1].split("def _evidence_sufficiency", 1)[0]
    assert 'return "observations_only"' in helper
    assert 'item.get("assertion") == "reference"' in helper
