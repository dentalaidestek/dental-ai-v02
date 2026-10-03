"""89K unseen Academic V2 past-question + note workflow holdout.

Models real student requests that combine course notes with prior exam questions.
It is structurally disjoint from the frozen 35K intent and 50K utility suites.
Student markings/answer keys are never treated as truth by this benchmark.
"""
from __future__ import annotations
import random,re,statistics,time
from app.dental_knowledge_graph import ALL_NODES
from app.dental_query_intent import classify_academic_study_task
from tests.academic_v2.test_intent_benchmark_15k import _rows as rows15
from tests.academic_v2.test_intent_holdout_20k import _rows as rows20,_norm
from tests.academic_v2.test_utility_holdout_50k import _rows as rows50,_skeleton

TARGET=89000
SEED=2026100389

FAMILIES={
"past_option_review":(
"Çıkmış {s} sorusundaki şıkları notlara göre tek tek doğru yanlış değerlendir ve gerekçelendir.",
"{s} ile ilgili geçmiş sorunun öncüllerini ders notundan doğrula; hangisi doğru hangisi yanlış açıkla.",
"Bu çıkmış {s} testinde seçenekleri işaretlemeye güvenmeden nottaki kanıtla kontrol et.",
"Çıkmışlarda {s} sorusunun şıklarını neden doğru veya yanlış olduklarıyla incele.",
),
"past_note_alignment":(
"Çıkmış {s} sorusu notta hangi konuya karşılık geliyor, ilgili yeri bulup eşleştir.",
"{s} hakkında geçmiş sınav sorusunu ders notundaki başlık ve kanıtla bağla.",
"Bu çıkmış {s} sorusunun cevabını aramadan önce notlarda dayandığı bölümü göster.",
"Notta {s} konusunu çıkmış soruyla eşleştir; soru hangi bilgiyi yokluyor?",
),
"past_question_explain":(
"Çıkmış {s} sorusunu nottan çöz ve doğru cevabın mantığını gerekçesiyle açıkla.",
"Geçmiş {s} sorusunu bana ezberletmeden neden öyle çözüldüğünü anlat.",
"Çıkmış {s} sorusunda doğru sonuca nottaki hangi bilgiyle gidiyoruz, adım adım çöz.",
"{s} çıkmış sorusunu çöz; çeldiricilerin neden elendiğini de nottan açıkla.",
),
"past_topic_summary":(
"Çıkmış {s} sorularının bağlı olduğu konuyu nottan özetle ve soru bağlantısını koru.",
"{s} için geçmiş sorularda yoklanan başlıkları nottaki konuyla beraber toparla.",
"Çıkmışlarda geçen {s} başlığını sınav odaklı özetle; soruların dayandığı bilgileri ayır.",
"{s} çıkmış sorularından hareketle ilgili konu başlığını nottan toparla.",
),
"repeated_patterns":(
"{s} konusunda çıkmışlarda tekrar tekrar sorulan soru biçimlerini ve konuları bul.",
"Geçmiş sınavlarda {s} için en sık yinelenen noktaları gerçek sorular üzerinden çıkar.",
"{s} çıkmışlarında hangi bilgi veya soru tipi sürekli tekrar ediyor?",
"Çıkmış {s} sorularında tekrar eden örüntüyü nottaki karşılığıyla göster.",
),
"similar_questions":(
"{s} çıkmışlarının tarzını koruyup nottan doğrulanabilen ama kopya olmayan benzer sorular üret.",
"Geçmiş {s} sorularına benzeyen yeni sorular hazırla; cevapları yalnız nottan doğrulanabilsin.",
"{s} için çıkmışla aynı mantığı ölçen fakat aynı cümle olmayan yeni test soruları oluştur.",
"Çıkmış {s} soru tipine benzer yeni sorular üret ve not dışı bilgi katma.",
),
"past_exam_patterns":(
"{s} için çıkmış sorular hangi bilgi türlerini yoklamış, geçmiş sınav örüntüsünü çıkar.",
"Hoca {s} konusunda geçmişte ne sormuş; gerçek çıkmışları konu başlıklarına ayır.",
"{s} çıkmış sorularını tarayıp soru dağılımını ve odaklarını göster.",
"Geçmiş sınavlarda {s} nasıl sorulmuş, soruları not konularına göre grupla.",
),
"summarize":(
"{s} notunu çıkmış sorularla birlikte özetle; çıkmışta geçen yerleri ayrıca belirt.",
"Çıkmış {s} sorularını da dikkate alarak konunun kısa çalışma özetini çıkar.",
"{s} için not + çıkmışları tek tekrar kağıdında toparla.",
"Bu {s} bölümünü geçmiş sorularla bağlantısını kaybetmeden özetle.",
),
}

PREFIXES=(
"", "Kanka bi bak: ", "Hocam şuna yardım et: ", "Sınava az kaldı, ", "Şöyle bi şey istiyorum; ",
"Ben bunu anlamadım, ", "Finale çalışıyorum; ", "Sözlü için hızlıca ", "Asistan sorarsa diye ",
"Notu açtım ama karıştı; ", "Şimdi sadece nottan giderek ", "Çıkmışları çalışıyorum; ",
)

def _ascii(x:str)->str:
    return x.translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU"))

def _typo(x:str, salt:int)->str:
    # One adjacent transposition in a non-subject operator-ish long token.
    words=x.split()
    candidates=[i for i,w in enumerate(words) if len(re.sub(r"\W","",w))>=7 and _norm(w) not in {"cikmis","gecmis"}]
    if not candidates:return x
    i=candidates[salt%len(candidates)]; w=words[i]
    letters=list(w); positions=[j for j in range(1,len(letters)-2) if letters[j].isalpha() and letters[j+1].isalpha()]
    if not positions:return x
    j=positions[salt%len(positions)]; letters[j],letters[j+1]=letters[j+1],letters[j]; words[i]="".join(letters)
    return " ".join(words)

def _prior():
    a=rows15(); b,_=rows20(); c,_,_=rows50()
    texts={_norm(r[0]) for r in a}|{_norm(r[0]) for r in b}|{_norm(r[0]) for r in c}
    labels=tuple(dict.fromkeys(n.label for n in ALL_NODES))
    sk={_skeleton(r[0],labels) for r in (*a,*b,*c)}
    return texts,sk

def _rows():
    rng=random.Random(SEED); prior,prior_sk=_prior(); out=[]; seen=set()
    for ni,node in enumerate(ALL_NODES):
        names=tuple(dict.fromkeys((node.label,*node.aliases[:3])))
        for name in names:
            for task,templates in FAMILIES.items():
                for ti,t in enumerate(templates):
                    base=t.format(s=name)
                    surfaces=[]
                    for pi,p in enumerate(PREFIXES):
                        q=p+base[:1].lower()+base[1:] if p else base
                        surfaces.extend((q,_ascii(q),_typo(q,ni+ti+pi)))
                    for q in surfaces:
                        k=_norm(q); sk=_skeleton(q,names)
                        if not k or k in prior or sk in prior_sk or k in seen:continue
                        seen.add(k); out.append((q,task,node.id))
    rng.shuffle(out)
    if len(out)<TARGET:raise AssertionError(f"89K için yalnız {len(out)} benzersiz yeni istek üretildi")
    rows=out[:TARGET]
    assert not ({_norm(x[0]) for x in rows}&prior)
    return rows,len(prior),len(prior_sk)

def test_unseen_89k_past_question_note_workflow_holdout():
    rows,prior_n,prior_sk_n=_rows(); ok=0; timings=[]; buckets={}; samples=[]
    for q,expected,node in rows:
        t=time.perf_counter(); plan=classify_academic_study_task(q); timings.append((time.perf_counter()-t)*1000)
        got=plan.task if plan else None; hit=got==expected; ok+=hit
        if not hit:
            key=f"{expected}->{got}"; buckets[key]=buckets.get(key,0)+1
            if len(samples)<60:samples.append((key,q,node))
        if expected.startswith("past_") or expected in {"repeated_patterns","similar_questions"}:
            assert plan is None or plan.requires_note_evidence
    n=len(rows); report={"count":n,"prior_85k_norms":prior_n,"prior_surface_skeletons":prior_sk_n,
      "task_exact":round(ok/n,4),"ms_p50":round(statistics.median(timings),3),
      "ms_p95":round(sorted(timings)[int(n*.95)-1],3),
      "failure_buckets":dict(sorted(buckets.items(),key=lambda x:(-x[1],x[0])))}
    print("ACADEMIC_PAST_NOTE_89K_REPORT",report)
    print("ACADEMIC_PAST_NOTE_89K_FAILURE_SAMPLE",samples)
    assert n==TARGET
    assert report["task_exact"]>=0.50,report
