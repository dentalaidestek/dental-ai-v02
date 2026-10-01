"""Dependency-free behavioral checks for local dental retrieval semantics.

These cases protect the semantic bridges that embeddings used to provide.
The benchmark intentionally tests query construction rather than a live DB so
CI remains fast and deterministic.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
tree = ast.parse(source)

wanted = {"_DENTAL_CONCEPT_GROUPS", "_QUERY_NOISE_RE"}
namespace = {"re": __import__("re")}
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
        "_concept_alternatives", "_retrieval_terms", "_fts_query"
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
