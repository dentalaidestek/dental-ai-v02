"""50K independent utility-oriented Academic V2 holdout.

Unlike the 15K/20K facet benchmarks, this suite models what a student/assistant/
researcher asks the notes to *do*: exam preparation, teaching, condensation,
question generation and evidence-grounded study workflows.  It rejects every
normalized 35K question and every old 35K surface skeleton.
"""
from __future__ import annotations
import random,re,statistics,time
from app.dental_knowledge_graph import ALL_NODES
from app.dental_query_intent import classify_academic_study_task
from tests.academic_v2.test_intent_benchmark_15k import _rows as rows15
from tests.academic_v2.test_intent_holdout_20k import _rows as rows20,_norm

TARGET=50000
SEED=2026100350

FAMILIES={
"summarize":(
"Finalden önce {s} bölümünü üç dakikalık tekrar kağıdına dönüştür.",
"{s} anlatımını çalışırken bakacağım kısa ders fişine sıkıştır.",
"{s} kısmındaki ana mesajı ve ayrıntıları ayrı başlıklarla toparla.",
"Yarınki kurul için {s} bölümünü hızlı tekrar özeti haline getir.",
"{s} konusunda dağınık geçen bilgileri tek çalışma sayfasında birleştir.",
"Bu gece çalışmak için {s} içeriğini öncelik sırasıyla yoğunlaştır.",
),
"exam_points":(
"{s} bölümünü sınava çalışan biri için tarayıp hocanın yoklayabileceği kritik yerleri göster.",
"{s} anlatımında sınavda gözden kaçırmamam gereken ayrıntıları ayıkla.",
"Vizede {s} üzerinden zorlayıcı soru kurulabilecek noktaları işaretle.",
"{s} çalışırken ezberlemem gerekenlerle mantığını anlamam gerekenleri ayır.",
"Bu derste {s} için sınav öncesi mutlaka kontrol etmem gereken yerler neresi?",
"{s} başlığından sözlüde takılabileceğim kritik bağlantıları çıkar.",
),
"generate_questions":(
"{s} çalışmamı sınamak için cevapları nottan doğrulanabilen yeni alıştırmalar hazırla.",
"{s} konusunu gerçekten anlayıp anlamadığımı ölçecek mini deneme oluştur.",
"{s} için kolaydan zora ilerleyen çalışma soruları üret.",
"{s} bölümünden kendimi test edeceğim açık uçlu alıştırmalar oluştur.",
"{s} bilgisini ezber değil yorumla ölçen pratik sorular hazırla.",
"{s} tekrarından sonra çözmem için kısa bir quiz oluştur.",
),
"explain":(
"{s} bölümünü ilk kez öğrenen üçüncü sınıf öğrencisine ders anlatır gibi öğret.",
"{s} kısmındaki mantık zincirini basamak basamak kurarak anlat.",
"{s} konusunu ezberletmeden neden-sonuç bağlantılarıyla öğret.",
"{s} bölümünde birbirine karışabilecek fikirleri sade bir dille açıklığa kavuştur.",
"Asistanın tahtada anlattığı gibi {s} konusunun mantığını kur.",
"{s} anlatımını önce temel fikir sonra ayrıntı şeklinde açıkla.",
),
}

PERSONAS=(
"Sınava iki gün kaldı; ","Klinik öncesi hızlı tekrar yapıyorum; ",
"Tez girişini hazırlamadan önce notu anlamam lazım; ","Sözlü provası yapıyorum; ",
"Arkadaşıma konuyu anlatacağım; ","Makale okurken ders notuyla bağ kurmak istiyorum; ",
"Final için son tekrarımı yapıyorum; ","Asistan sunumuna hazırlanıyorum; ",
)

def _skeleton(q:str,names:tuple[str,...])->str:
    x=_norm(q)
    for name in sorted(names,key=len,reverse=True):
        n=_norm(name)
        if n: x=re.sub(r"(?<!\w)"+re.escape(n)+r"(?!\w)","<subject>",x)
    return x

def _prior():
    a=rows15(); b,_=rows20()
    texts={_norm(r[0]) for r in a}|{_norm(r[0]) for r in b}
    # Structural denylist: exact old surface after replacing the known subject
    # with a placeholder. This blocks "same question, different dental noun".
    sk=set()
    labels=tuple(dict.fromkeys(n.label for n in ALL_NODES))
    for r in (*a,*b):
        sk.add(_skeleton(r[0],labels))
    return texts,sk

def _rows():
    rng=random.Random(SEED); prior,prior_sk=_prior(); out=[]; seen=set(); seen_sk=set()
    nodes=list(ALL_NODES)
    for node in nodes:
        names=tuple(dict.fromkeys((node.label,*node.aliases[:2])))
        for name in names:
            for task,templates in FAMILIES.items():
                for template in templates:
                    base=template.format(s=name)
                    variants=(base,*(p+base[:1].lower()+base[1:] for p in PERSONAS))
                    for q in variants:
                        k=_norm(q); sk=_skeleton(q,names)
                        if not k or k in prior or sk in prior_sk or k in seen: continue
                        # Keep this holdout internally unique in wording; persona is
                        # part of user intent, but identical normalized surfaces are forbidden.
                        seen.add(k); seen_sk.add(sk); out.append((q,task,node.id))
    rng.shuffle(out)
    if len(out)<TARGET: raise AssertionError(f"50K için yalnız {len(out)} benzersiz yeni istek üretildi")
    rows=out[:TARGET]
    assert not ({_norm(x[0]) for x in rows}&prior)
    node_map={n.id:n for n in ALL_NODES}
    row_skeletons=set()
    for q,_task,node_id in rows:
        node=node_map[node_id]
        names=tuple(dict.fromkeys((node.label,*node.aliases[:2])))
        row_skeletons.add(_skeleton(q,names))
    assert not (row_skeletons & prior_sk)
    return rows,len(prior),len(prior_sk)

def test_independent_50k_student_assistant_research_utility_holdout():
    rows,prior_n,prior_sk_n=_rows(); ok=0; timings=[]; buckets={}; samples=[]
    for q,expected,node in rows:
        t=time.perf_counter(); plan=classify_academic_study_task(q); timings.append((time.perf_counter()-t)*1000)
        got=plan.task if plan else None; hit=got==expected; ok+=hit
        if not hit:
            key=f"{expected}->{got}"; buckets[key]=buckets.get(key,0)+1
            if len(samples)<40:samples.append((key,q,node))
    n=len(rows); report={
      "count":n,"prior_35k_norms":prior_n,"prior_surface_skeletons":prior_sk_n,
      "task_exact":round(ok/n,4),"ms_p50":round(statistics.median(timings),3),
      "ms_p95":round(sorted(timings)[int(n*.95)-1],3),
      "failure_buckets":dict(sorted(buckets.items(),key=lambda x:(-x[1],x[0]))),
    }
    print("ACADEMIC_UTILITY_50K_REPORT",report)
    print("ACADEMIC_UTILITY_50K_FAILURE_SAMPLE",samples)
    assert n==TARGET
    assert report["task_exact"]>=0.50,report
