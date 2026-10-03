from __future__ import annotations

import json
import random
import re
import statistics
import time
from pathlib import Path

from app.dental_knowledge_graph import ALL_NODES
from app.dental_query_intent import build_dental_requirement_plan

TARGET = 20_000
SEED = 20261004
ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# This holdout intentionally uses different discourse families from the 15K
# diagnostic benchmark: student recall, assistant chairside/clinic-note lookup,
# and instructor/oral-exam prompts.
FACETS_BY_KIND = {
    "measurement": ("definition","value","measurement"), "index": ("definition","value","measurement"),
    "anatomy": ("definition","anatomy"), "tissue": ("definition","anatomy"), "cell": ("definition","anatomy"),
    "diagnosis": ("definition","diagnosis","treatment","cause","classification","complication"),
    "finding": ("definition","diagnosis","cause","classification"), "complication": ("definition","cause","treatment"),
    "procedure": ("definition","indication","contraindication","complication"),
    "material": ("definition","indication","contraindication"), "appliance": ("definition","indication","contraindication"),
    "drug": ("definition","indication","contraindication","complication"), "drug_class": ("definition","indication","contraindication","complication"),
    "imaging": ("definition","indication"), "classification": ("definition","classification"),
}

PROMPTS = {
 "definition": (
   "Notta {s} ifadesiyle tam olarak ne anlatılıyor?",
   "Bir öğrenci {s} terimini nasıl tanımlamalı?",
   "Hocam sözlüde {s} sorarsa tanım olarak ne söylemeliyim?",
   "{s} için nottaki temel kavramsal açıklamayı çıkar.",
 ),
 "value": (
   "Notlarda {s} için verilen sayısal sınır veya normal aralık hangisi?",
   "{s} açısından kabul edilen normal sayı/değer ne olarak geçiyor?",
   "Hocanın {s} için sorabileceği referans değeri nottan bul.",
   "{s} ile ilgili eşik, oran ya da normal aralığı söyle.",
 ),
 "measurement": (
   "{s} pratikte hangi yöntem veya parametreyle ölçülüyor?",
   "Asistan olarak {s} değerlendirmesini nasıl yapmam gerekiyor?",
   "{s} ölçerken notta tarif edilen yöntemi çıkar.",
   "Bu notlara göre {s} değerlendirmesinde hangi ölçüm esas alınıyor?",
 ),
 "classification": (
   "{s} için notta geçen grupları/evreleri düzenli biçimde ayır.",
   "Sözlüde {s} sınıflarını saysam hangi başlıkları vermeliyim?",
   "{s} hangi kategorilere ayrılmış, nottan çıkar.",
   "Hocanın anlattığı biçimiyle {s} evreleme sistemini özetle.",
 ),
 "diagnosis": (
   "Bir vakada {s} düşünmek için notta hangi bulgular aranıyor?",
   "{s} şüphesini destekleyen tanısal ipuçlarını nottan çıkar.",
   "Asistan gözüyle {s} tanısına giderken nelere bakmalıyım?",
   "Sınavda {s} tanısını gerekçelendirmek için hangi özellikleri yazmalıyım?",
 ),
 "treatment": (
   "{s} ile karşılaşınca notlara göre yönetim sırası nasıl?",
   "Bu ders notunda {s} için önerilen yaklaşım nedir?",
   "{s} vakasının yönetimini nottaki basamaklarla anlat.",
   "Asistan olarak {s} durumunda ne yapmam gerektiğini nottan çıkar.",
 ),
 "complication": (
   "{s} sonrasında karşılaşılabilecek istenmeyen sonuçlar hangileri?",
   "{s} ile ilişkili sorunları/komplikasyonları nottan çıkar.",
   "Hocanın {s} için özellikle uyardığı olumsuz sonuçlar neler?",
   "{s} uygulamasının ardından hangi problemler gelişebilir?",
 ),
 "cause": (
   "{s} gelişmesini kolaylaştıran koşullar veya etkenler hangileri?",
   "{s} ortaya çıkmasına zemin hazırlayan faktörleri nottan bul.",
   "Hocanın {s} için saydığı predispozan etkenler neler?",
   "{s} neden ortaya çıkıyor; notta hangi etiyolojik etkenler verilmiş?",
 ),
 "indication": (
   "{s} seçimini hangi klinik koşullarda düşünmeliyim?",
   "Notlara göre {s} kullanımını uygun kılan durumlar hangileri?",
   "Bir asistan {s} tercihine hangi durumda yönelmeli?",
   "{s} için uygun kullanım senaryolarını dersten çıkar.",
 ),
 "contraindication": (
   "{s} seçeneğinden hangi koşullarda kaçınmam gerekir?",
   "Notlarda {s} kullanımını uygun görmeyen durumlar hangileri?",
   "Bir vakada {s} tercih etmemem gereken şartları çıkar.",
   "{s} açısından sakıncalı kabul edilen durumları nottan bul.",
 ),
 "anatomy": (
   "{s} çevresindeki önemli anatomik komşulukları nottan çıkar.",
   "Bir asistan {s} bölgesinde hangi yapılarla ilişkiyi bilmeli?",
   "{s} anatomik olarak nerede ve hangi yapılarla ilişkili?",
   "Sözlüde {s} komşulukları sorulursa hangi yapıları saymalıyım?",
 ),
}

def _norm(q: str) -> str:
    q = q.casefold().translate(ASCII)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    return " ".join(q.split())

def _transpose_one(text: str, rng: random.Random) -> str:
    words=text.split()
    idx=[i for i,w in enumerate(words) if len(re.sub(r"\W","",w))>=8]
    if not idx: return text
    i=rng.choice(idx); w=words[i]
    positions=[p for p in range(1,len(w)-2) if w[p:p+2].isalpha()]
    if not positions: return text
    p=rng.choice(positions)
    words[i]=w[:p]+w[p+1]+w[p]+w[p+2:]
    return " ".join(words)

def _surface_variants(q: str, rng: random.Random):
    yield "student", q
    yield "assistant", "Klinikte hızlıca bakmam lazım: " + q[:1].lower()+q[1:]
    yield "instructor", "Öğrenciye bunu soracağım; " + q[:1].lower()+q[1:]
    yield "oral", "Sözlü provası: " + q
    yield "ascii", q.translate(ASCII)
    yield "typo", _transpose_one(q, rng)

def _old_15k_norms():
    # Reuse the existing generator only as a forbidden-text source.
    from tests.academic_v2.test_intent_benchmark_15k import _rows
    return {_norm(row[0]) for row in _rows()}

def _external_old_norms():
    # CI can optionally receive Claude's old JSONL as an artifact/file. The
    # committed holdout never silently depends on it; a generated denylist file
    # is used when present.
    deny = Path(__file__).with_name("benchmark_prior_questions_norm.txt")
    if not deny.exists():
        return set()
    return {line.strip() for line in deny.read_text(encoding="utf-8").splitlines() if line.strip()}

def _rows():
    rng=random.Random(SEED)
    forbidden=_old_15k_norms() | _external_old_norms()
    candidates=[]
    for node in ALL_NODES:
        facets=FACETS_BY_KIND.get(node.kind,("definition",))
        names=[node.label,*node.aliases[:3]]
        for name in names:
            for facet in facets:
                for prompt in PROMPTS[facet]:
                    for style,q in _surface_variants(prompt.format(s=name),rng):
                        candidates.append((q,node.id,frozenset((facet,)),style,"single"))
        # New compositional family: professor/student requests two compatible
        # dimensions in prose rather than the old comma-list templates.
        pairs=[]
        if "diagnosis" in facets and "treatment" in facets: pairs.append(("diagnosis","treatment"))
        if "cause" in facets and "complication" in facets: pairs.append(("cause","complication"))
        if "indication" in facets and "contraindication" in facets: pairs.append(("indication","contraindication"))
        for a,b in pairs:
            q=f"{name} konusunda önce {PROMPTS[a][0].format(s=name).split(name,1)[-1].strip()} Ardından {PROMPTS[b][1].format(s=name).split(name,1)[-1].strip()}"
            for style,v in _surface_variants(q,rng):
                candidates.append((v,node.id,frozenset((a,b)),style,"composed2"))

    # Deduplicate and exclude every normalized 15K/prior question.
    by_norm={}; conflicts=set()
    for row in candidates:
        k=_norm(row[0]); gold=(row[1],row[2])
        if not k or k in forbidden: continue
        if k in by_norm and (by_norm[k][1],by_norm[k][2]) != gold: conflicts.add(k)
        else: by_norm.setdefault(k,row)
    rows=[row for k,row in by_norm.items() if k not in conflicts]
    rng.shuffle(rows)
    if len(rows)<TARGET:
        raise AssertionError(f"20K unseen holdout için yalnız {len(rows)} benzersiz soru üretildi")
    return rows[:TARGET], forbidden

def test_unseen_20k_academic_query_holdout():
    rows,forbidden=_rows()
    assert len(rows)==TARGET
    assert not ({_norm(r[0]) for r in rows} & forbidden)

    timings=[]; subject=recall=exact=leaks=0; buckets={}; styles={}; failures=[]
    for q,node,facets,style,kind in rows:
        t=time.perf_counter(); plan=build_dental_requirement_plan(q); timings.append((time.perf_counter()-t)*1000)
        nodes=set(plan.subject_node_ids); got=set(plan.requested_facets)
        s=node in nodes; r=facets.issubset(got); leak=got-facets; e=r and not leak
        subject+=s; recall+=r; exact+=e; leaks+=bool(leak)
        st=styles.setdefault(style,[0,0,0]); st[0]+=1; st[1]+=s; st[2]+=e
        if not s or not e:
            reason="subject" if not s else ("missing:"+ "+".join(sorted(facets-got)) if facets-got else "leak:"+ "+".join(sorted(leak)))
            buckets[reason]=buckets.get(reason,0)+1
            if len(failures)<40: failures.append((reason,q,node,sorted(facets),sorted(nodes),sorted(got)))
    n=len(rows)
    report={
      "count":n,"forbidden_prior_norms":len(forbidden),
      "subject_hit":round(subject/n,4),"intent_recall":round(recall/n,4),
      "intent_exact":round(exact/n,4),"intent_leak_rate":round(leaks/n,4),
      "ms_p50":round(statistics.median(timings),3),
      "ms_p95":round(sorted(timings)[int(n*.95)-1],3),
      "styles":{k:{"n":v[0],"subject":round(v[1]/v[0],4),"exact":round(v[2]/v[0],4)} for k,v in sorted(styles.items())},
      "failure_buckets":dict(sorted(buckets.items(),key=lambda x:(-x[1],x[0]))),
    }
    print("ACADEMIC_UNSEEN_20K_REPORT",report)
    print("ACADEMIC_UNSEEN_20K_FAILURE_SAMPLE",failures)
    # Diagnostic holdout: only catastrophic-regression guards. Do not tune
    # thresholds to make a red benchmark green.
    assert report["subject_hit"]>=0.70, report
    assert report["intent_recall"]>=0.70, report
    assert report["intent_leak_rate"]<=0.20, report
