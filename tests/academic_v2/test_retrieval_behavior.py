"""Dependency-free behavioral checks for local dental retrieval semantics.

These cases protect the semantic bridges that embeddings used to provide.
The benchmark intentionally tests query construction rather than a live DB so
CI remains fast and deterministic.
"""
from pathlib import Path
import ast
from app.dental_query_intent import classify_dental_intent, classify_dental_intents, combined_relation_hints
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
assert "if len(rows) < max(limit, 6):" in source
assert "rows = _coverage_select(resolved, rows, limit=limit)" in source


# Latency guard: simple factual questions stay on one-pass retrieval.
assert '_FAST_INTENTS = {"value", "definition", "measurement"}' in source
assert "def _needs_multi_evidence" in source
assert "coverage < 0.34" in source
assert "rescue_query_count = 0" in source
assert "rescue_query_count = 1" in source
assert "alias_terms = _concept_alternatives(resolved)" in source
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
assert '"indication": ("endikasyon", "kullanım", "durum")' in source
assert '"contraindication": ("kontrendikasyon", "sakınca", "kullanılmaz")' in source

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


def test_reranker_keeps_exact_subject_above_nearby_dental_distractors():
    # Extract the production reranker and its local helpers without a DB.
    import json
    from app.dental_semantics import analyze_dental_text, semantic_overlap_score
    ns = dict(namespace)
    ns.update({
        "analyze_dental_text": analyze_dental_text,
        "semantic_overlap_score": semantic_overlap_score,
    })
    wanted_fns = {"_subject_alignment_score", "_rerank_dental_rows"}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted_fns:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<reranker>", "exec"), ns)

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
    for query, expected_id, rows in cases:
        ranked = ns["_rerank_dental_rows"](query, rows, limit=3)
        assert ranked[0][0] == expected_id, (query, [r[0] for r in ranked])


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
    assert "sufficient = anchored and hard_complete and confidence >= 0.38" in source


def test_rescue_path_is_single_bounded_round_trip():
    # The normal retrieval branch must contain one primary FTS call and at most
    # one rescue FTS call; old per-facet probe loops/broad fallback are gone.
    branch = source.split("precise_query = _fts_query(resolved, broad=False)", 1)[1]
    branch = branch.split("rows = _coverage_select(resolved, rows, limit=limit)", 1)[0]
    assert branch.count("_fts_rows(") == 2
    assert "for evidence_query in evidence_queries" not in branch
    assert "broad_query = _fts_query(resolved, broad=True)" not in branch


def test_fast_direct_path_skips_neighbor_hydration_structurally():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "fast_direct = bool(requirement_names) and requirement_names.issubset(_FAST_INTENTS)" in source
    assert "neighbor_limit = 0 if fast_direct and rows" in source


def test_mixed_fast_and_multifacet_request_does_not_bypass_completeness():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    assert "intent_names and intent_names.issubset(_FAST_INTENTS)" in source
    assert 'if intent.name in {"value", "definition", "measurement"}:' not in source


def test_coverage_selection_uses_same_facet_synonyms_as_coverage_scoring():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    coverage_select = source[source.index("def _coverage_select"):source.index("def retrieve_course_context_v2")]
    assert "_facet_present(facet, haystack, row_kinds)" in coverage_select
    assert "if facet_cf in haystack:" not in coverage_select


def test_visual_page_artifact_is_generation_and_owner_scoped():
    source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
    visual = source[source.index("def _single_page_pdf"):source.index("def _pgvector_available")]
    assert "owner_user_id=:o AND material_id=:m" in visual
    assert "index_version=:v AND page_number=:p" in visual
    assert "visual_pdf_bytes IS NULL" in visual
