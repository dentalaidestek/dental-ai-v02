"""Combined 15K + unseen 20K query-understanding consistency benchmark."""
from __future__ import annotations
import statistics
import time

from app.study_retrieval_v2 import build_dental_requirement_plan
from tests.academic_v2.test_intent_benchmark_15k import _rows as rows15
from tests.academic_v2.test_intent_holdout_20k import _rows as rows20, _norm


def test_combined_35k_query_understanding_consistency():
    a = rows15()
    b, forbidden = rows20()
    assert len(a) == 15000 and len(b) == 20000
    # The 20K generator already guarantees normalized separation from the 15K.
    assert not ({_norm(r[0]) for r in a} & {_norm(r[0]) for r in b})

    rows = [("15k", *r) for r in a] + [("20k", *r) for r in b]
    subject = recall = exact = leaks = 0
    timings = []
    split = {"15k": [0,0,0,0,0], "20k": [0,0,0,0,0]}
    failures = {}
    samples = {}
    for source, query, node, facets, style, kind in rows:
        t=time.perf_counter()
        plan=build_dental_requirement_plan(query)
        timings.append((time.perf_counter()-t)*1000)
        nodes=set(plan.subject_node_ids); got=set(plan.requested_facets)
        s=node in nodes; r=facets.issubset(got); leak=got-facets; e=r and not leak
        subject += s; recall += r; exact += e; leaks += bool(leak)
        z=split[source]; z[0]+=1; z[1]+=s; z[2]+=r; z[3]+=e; z[4]+=bool(leak)
        for facet in sorted(facets-got):
            key=(source,"missing",facet,style)
            failures[key]=failures.get(key,0)+1
            samples.setdefault(key,query)
        for facet in sorted(leak):
            key=(source,"leak",facet,style)
            failures[key]=failures.get(key,0)+1
            samples.setdefault(key,query)
        if not s:
            key=(source,"subject",kind,style)
            failures[key]=failures.get(key,0)+1
            samples.setdefault(key,query)

    n=len(rows)
    report={
        "count":n,
        "subject_hit":round(subject/n,4),
        "intent_recall":round(recall/n,4),
        "intent_exact":round(exact/n,4),
        "intent_leak_rate":round(leaks/n,4),
        "ms_p50":round(statistics.median(timings),3),
        "ms_p95":round(sorted(timings)[int(n*.95)-1],3),
        "splits":{k:{
            "n":v[0],"subject":round(v[1]/v[0],4),"recall":round(v[2]/v[0],4),
            "exact":round(v[3]/v[0],4),"leak":round(v[4]/v[0],4)
        } for k,v in split.items()},
    }
    weighted_exact=round((split["15k"][3]+split["20k"][3])/n,4)
    weighted_recall=round((split["15k"][2]+split["20k"][2])/n,4)
    print("ACADEMIC_COMBINED_35K_REPORT",report)
    print("ACADEMIC_COMBINED_35K_FAILURES", [(k,v,samples[k]) for k,v in sorted(failures.items(),key=lambda x:(-x[1],x[0]))[:80]])\n    print("ACADEMIC_COMBINED_35K_WEIGHTED_CHECK",{
        "exact_from_counts":weighted_exact,
        "recall_from_counts":weighted_recall,
        "exact_delta":round(report["intent_exact"]-weighted_exact,6),
        "recall_delta":round(report["intent_recall"]-weighted_recall,6),
        "forbidden_prior_norms":len(forbidden),
    })
    assert n == 35000
    assert report["intent_exact"] == weighted_exact
    assert report["intent_recall"] == weighted_recall
