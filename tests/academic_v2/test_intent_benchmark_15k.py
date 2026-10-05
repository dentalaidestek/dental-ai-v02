from __future__ import annotations

import random
import statistics
import time

from app.dental_knowledge_graph import ALL_NODES
from app.dental_query_intent import build_dental_requirement_plan

TARGET = 15_000
ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

KIND_FACETS = {
    "measurement": ("definition", "value", "measurement"),
    "index": ("definition", "value", "measurement"),
    "anatomy": ("definition", "anatomy"),
    "tissue": ("definition", "anatomy"),
    "cell": ("definition", "anatomy"),
    "diagnosis": ("definition", "diagnosis", "treatment", "cause", "classification", "complication"),
    "finding": ("definition", "diagnosis", "cause", "classification"),
    "complication": ("definition", "cause", "treatment"),
    "procedure": ("definition", "indication", "contraindication", "complication"),
    "material": ("definition", "indication", "contraindication"),
    "appliance": ("definition", "indication", "contraindication"),
    "drug": ("definition", "indication", "contraindication", "complication"),
    "drug_class": ("definition", "indication", "contraindication", "complication"),
    "imaging": ("definition", "indication"),
    "classification": ("definition", "classification"),
}
TEMPLATES = {
    "definition": ("{s} nedir?", "{s} ne demektir?", "{s} kavramını açıkla."),
    "value": ("{s} normal değeri kaçtır?", "{s} referans aralığı nedir?", "{s} için normal değer nedir?"),
    "measurement": ("{s} nasıl ölçülür?", "{s} hangi ölçümle değerlendirilir?", "{s} ölçüm mantığını açıkla."),
    "classification": ("{s} nasıl sınıflandırılır?", "{s} sınıflaması nedir?", "{s} evreleri veya sınıfları nelerdir?"),
    "diagnosis": ("{s} tanısı nasıl konur?", "{s} tanı bulguları nelerdir?", "{s} nasıl teşhis edilir?"),
    "treatment": ("{s} nasıl tedavi edilir?", "{s} tedavisinde ne yapılır?", "{s} yönetimini açıkla."),
    "complication": ("{s} komplikasyonları nelerdir?", "{s} yan etkileri nelerdir?", "{s} komplikasyon riskini açıkla."),
    "cause": ("{s} neden gelişir?", "{s} risk faktörleri nelerdir?", "{s} için yatkınlaştıran etkenler nelerdir?"),
    "indication": ("{s} hangi durumlarda uygulanır?", "{s} endikasyonları nelerdir?", "{s} ne zaman tercih edilir?"),
    "contraindication": ("{s} hangi durumlarda uygulanmamalıdır?", "{s} kontrendikasyonları nelerdir?", "{s} ne zaman tercih edilmez?"),
    "anatomy": ("{s} nerede bulunur?", "{s} anatomik ilişkileri nelerdir?", "{s} hangi yapılarla komşudur?"),
}
NOUN = {
    "diagnosis": "tanısı", "treatment": "tedavisi", "complication": "komplikasyonları",
    "cause": "risk faktörleri", "classification": "sınıflaması",
    "indication": "endikasyonları", "contraindication": "kontrendikasyonları",
}
MULTI = tuple(NOUN)

def _typo(text: str, rng: random.Random) -> str:
    words = text.split()
    candidates = [i for i, w in enumerate(words) if len(w) >= 7]
    if not candidates:
        return text
    i = candidates[rng.randrange(len(candidates))]
    w = words[i]
    p = rng.randrange(1, len(w) - 2)
    words[i] = w[:p] + w[p + 1] + w[p] + w[p + 2:]
    return " ".join(words)

def _styles(query: str, rng: random.Random):
    base = query.strip()
    yield "formal", base
    yield "ascii", base.translate(ASCII)
    yield "lower", base.casefold()
    yield "upper", base.replace("i", "İ").replace("ı", "I").upper()
    yield "typo", _typo(base, rng)
    yield "natural", "Ders notuna göre " + base[:1].lower() + base[1:]
    yield "short", base.rstrip("?") + "?"
    yield "exam", "Sınav açısından " + base[:1].lower() + base[1:]

def _rows():
    rng = random.Random(20261003)
    candidates = []
    for node in ALL_NODES:
        facets = KIND_FACETS.get(node.kind, ("definition",))
        names = [node.label, *node.aliases[:2]]
        for name in names:
            for facet in facets:
                for template in TEMPLATES[facet]:
                    q = template.format(s=name)
                    for style, variant in _styles(q, rng):
                        candidates.append((variant, node.id, frozenset((facet,)), style, "single"))
            pool = [f for f in facets if f in MULTI]
            if len(pool) >= 2:
                for width in (2, 3):
                    if len(pool) < width:
                        continue
                    chosen = tuple(pool[:width])
                    nouns = [NOUN[f] for f in chosen]
                    q = f"{name} " + ", ".join(nouns[:-1]) + " ve " + nouns[-1] + " nelerdir?"
                    for style, variant in _styles(q, rng):
                        candidates.append((variant, node.id, frozenset(chosen), style, f"multi{width}"))

    # Semantic-role contrasts deliberately span multiple subjects and combinations.
    role_subjects = [n for n in ALL_NODES if n.kind in {"diagnosis", "procedure", "drug", "finding"}][:80]
    role_templates = (
        ("{s} için risk faktörleri nelerdir?", {"cause"}),
        ("{s} riskini artıran nedenleri açıkla.", {"cause"}),
        ("{s} açısından yatkınlaştıran etkenleri say.", {"cause"}),
        ("{s} komplikasyonları nelerdir?", {"complication"}),
        ("{s} yan etkileri nelerdir?", {"complication"}),
        ("{s} komplikasyon riski nedir?", {"complication"}),
        ("{s} risk faktörleri ve komplikasyonları nelerdir?", {"cause", "complication"}),
        ("{s} endikasyonları ve kontrendikasyonları nelerdir?", {"indication", "contraindication"}),
        ("{s} endikasyonları, kontrendikasyonları, komplikasyonları ve risk faktörlerini özetle.", {"indication", "contraindication", "complication", "cause"}),
    )
    for node in role_subjects:
        for template, facets in role_templates:
            q = template.format(s=node.label)
            for style, variant in _styles(q, rng):
                candidates.append((variant, node.id, frozenset(facets), style, "role"))

    # Remove query collisions with conflicting gold labels instead of rewarding ambiguity.
    by_query = {}
    conflicts = set()
    for row in candidates:
        key = row[0].casefold().strip()
        gold = (row[1], row[2])
        if key in by_query and (by_query[key][1], by_query[key][2]) != gold:
            conflicts.add(key)
        else:
            by_query.setdefault(key, row)
    rows = [row for key, row in by_query.items() if key not in conflicts]
    rng.shuffle(rows)
    if len(rows) < TARGET:
        raise AssertionError(f"15K benchmark için yalnız {len(rows)} benzersiz/çelişkisiz soru üretildi")
    return rows[:TARGET]

def test_deterministic_15k_query_understanding_benchmark():
    rows = _rows()
    failures = []
    subject_ok = exact_ok = recall_ok = 0
    failure_buckets = {}
    leak_count = 0
    timings = []
    by_style = {}
    by_kind = {}

    for query, expected_node, expected_facets, style, qkind in rows:
        started = time.perf_counter()
        plan = build_dental_requirement_plan(query)
        timings.append((time.perf_counter() - started) * 1000)
        got_nodes = set(plan.subject_node_ids)
        got_facets = set(plan.requested_facets)
        s_ok = expected_node in got_nodes
        r_ok = expected_facets.issubset(got_facets)
        leak = got_facets - expected_facets
        e_ok = r_ok and not leak
        subject_ok += int(s_ok)
        recall_ok += int(r_ok)
        exact_ok += int(e_ok)
        leak_count += int(bool(leak))
        bucket = by_style.setdefault(style, [0, 0, 0])
        bucket[0] += 1
        bucket[1] += int(s_ok)
        bucket[2] += int(e_ok)
        kind = by_kind.setdefault(qkind, [0, 0, 0])
        kind[0] += 1
        kind[1] += int(s_ok)
        kind[2] += int(e_ok)
        if not s_ok or not e_ok:
            missing = expected_facets - got_facets
            qfold = query.casefold()
            if not s_ok:
                reason = "subject_typo" if style == "typo" else ("subject_ascii" if style == "ascii" else "subject_other")
            elif missing:
                reason = "intent_missing:" + "+".join(sorted(missing))
            elif leak:
                reason = "intent_leak:" + "+".join(sorted(leak))
            else:
                reason = "other"
            failure_buckets[reason] = failure_buckets.get(reason, 0) + 1
            if len(failures) < 120:
                failures.append((reason, query, expected_node, sorted(expected_facets), sorted(got_nodes), sorted(got_facets)))

    n = len(rows)
    report = {
        "count": n,
        "subject_hit": round(subject_ok / n, 4),
        "intent_recall": round(recall_ok / n, 4),
        "intent_exact": round(exact_ok / n, 4),
        "intent_leak_rate": round(leak_count / n, 4),
        "ms_p50": round(statistics.median(timings), 3),
        "ms_p95": round(sorted(timings)[int(n * .95) - 1], 3),
        "styles": {k: {"n": v[0], "subject": round(v[1]/v[0],4), "exact": round(v[2]/v[0],4)} for k,v in sorted(by_style.items())},
        "kinds": {k: {"n": v[0], "subject": round(v[1]/v[0],4), "exact": round(v[2]/v[0],4)} for k,v in sorted(by_kind.items())},
        "failure_buckets": dict(sorted(failure_buckets.items(), key=lambda item: (-item[1], item[0]))),
    }
    print("ACADEMIC_15K_REPORT", report)
    if failures:
        print("ACADEMIC_15K_FAILURE_SAMPLE", failures[:30])

    assert n == TARGET
    # Benchmark is diagnostic first: guard catastrophic regressions while the
    # detailed percentages guide general semantic fixes on the dev branch.
    assert report["subject_hit"] >= 0.70, report
    assert report["intent_recall"] >= 0.90, report
    assert report["intent_leak_rate"] <= 0.20, report
