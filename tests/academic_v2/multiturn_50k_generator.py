"""Deterministic 50k conversation-case generator for Academic AI continuity."""
from __future__ import annotations
import hashlib, random, re
from dataclasses import dataclass
from tests.academic_v2.multiturn_50k_taxonomy import *

TOPICS=[
("çocuklarda flor kullanımı",("flor","çocuk")),("irreversible pulpitis",("irreversible","pulpitis")),
("periodontitis klinik bulguları",("periodontitis",)),("SNB açısı",("snb",)),("SNA açısı",("sna",)),
("ANB açısı",("anb",)),("lokal anestezik maksimum doz",("anestezik","doz")),
("ameloblastoma radyografik bulguları",("ameloblastoma",)),("kök yüzeyi düzleştirme",("kök","yüzeyi")),
("apikal periodontitis",("apikal","periodontitis")),("temporomandibular eklem",("temporomandibular",)),
("süt dişi pulpa tedavisi",("süt","pulpa")),("daimi diş avülsiyonu",("daimi","avülsiyon")),
("Angle sınıf II maloklüzyon",("angle","sınıf")),("oral lökoplaki",("lökoplaki",)),
("furkasyon lezyonları",("furkasyon",)),("periapikal kist",("periapikal","kist")),
("internal rezorpsiyon",("internal","rezorpsiyon")),("dry socket",("dry","socket")),
("gingival indeks",("gingival","indeks")),
("Bennett açısı",("bennett","açı")),("Spee eğrisi",("spee","eğri")),("Wilson eğrisi",("wilson","eğri")),
("overjet değerlendirmesi",("overjet",)),("overbite değerlendirmesi",("overbite",)),("crossbite",("crossbite",)),
("pulpektomi",("pulpektomi",)),("pulpotomi",("pulpotomi",)),("MTA kullanımı",("mta",)),
("kalsiyum hidroksit",("kalsiyum","hidroksit")),("EDTA irrigasyonu",("edta",)),("sodyum hipoklorit",("hipoklorit",)),
("apeksifikasyon",("apeksifikasyon",)),("rejeneratif endodonti",("rejeneratif","endodonti")),
("agresif periodontitis",("agresif","periodontitis")),("gingivitis",("gingivitis",)),("mukogingival cerrahi",("mukogingival",)),
("oral kandidiyazis",("kandidiyazis",)),("liken planus",("liken","planus")),("aftöz ülser",("aftöz","ülser")),
("odontojenik keratokist",("keratokist",)),("dentigeröz kist",("dentigeröz","kist")),("odontoma",("odontoma",)),
("Le Fort kırıkları",("le","fort")),("mandibula kondil kırığı",("kondil","kırık")),("zigoma kırığı",("zigoma","kırık")),
("inferior alveolar sinir",("inferior","alveolar","sinir")),("mental foramen",("mental","foramen")),
("maksiller sinüs",("maksiller","sinüs")),("mandibular kanal",("mandibular","kanal")),
("sefalometrik analiz",("sefalometrik",)),("Wits analizi",("wits",)),("Bolton analizi",("bolton",)),
("yer tutucu",("yer","tutucu")),("fissür örtücü",("fissür","örtücü")),("paslanmaz çelik kron",("çelik","kron")),
("cam iyonomer siman",("cam","iyonomer")),("kompozit rezin",("kompozit","rezin")),("adeziv sistemler",("adeziv",)),
("bruksizm",("bruksizm",)),("TME dislokasyonu",("tme","dislokasyon")),("miyofasiyal ağrı",("miyofasiyal","ağrı")),
("perikoronitis",("perikoronitis",)),("alveolit",("alveolit",)),("osteomiyelit",("osteomiyelit",)),
("bisfosfonat ilişkili osteonekroz",("bisfosfonat","osteonekroz")),("lokal anestezi komplikasyonları",("anestezi","komplikasyon")),
]
@dataclass(frozen=True)
class Case:
 case_id:str; axes:dict; history:tuple[tuple[str,str],...]; query:str
 must:tuple[str,...]; must_not:tuple[str,...]; expected:dict

def _list(topic,n=20):
 return "\n".join(f"{i}. {topic} ile ilgili klinik soru {i}\nA) a\nB) b\nC) c\nD) d" for i in range(1,n+1))

def _noise(s,style,r):
 if style=="clean": return s
 if style=="missing_diacritics": return s.translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU"))
 if style=="no_punctuation": return re.sub(r"[?.!,;:]","",s)
 if style=="extra_spaces": return re.sub(r" ",lambda m:" "*r.randint(2,5),s)
 if style=="case_noise": return "".join(ch.upper() if r.random()<.25 else ch for ch in s)
 if style=="repeated_letters": return re.sub(r"([aeiouıöü])",lambda m:m.group(1)*r.randint(1,3),s,count=2,flags=re.I)
 if style=="typo_light":
  if len(s)>8:
   p=r.randrange(2,len(s)-2); return s[:p]+s[p+1:]
 if style=="typo_heavy":
  out=s
  for _ in range(2):
   if len(out)>8:
    p=r.randrange(2,len(out)-2); out=out[:p]+out[p+1:]
  return out
 if style=="fragment": return re.sub(r"^(peki |şimdi |bana )","",s,flags=re.I)
 if style=="colloquial": return "kral "+s.replace("hazırla","yap").replace("anlat","anlatsana")
 if style=="slang": return s+" ya"
 if style=="anger": return "ya "+s+" düzgün yap"
 if style=="polite": return s+" lütfen"
 if style=="telegraphic": return re.sub(r"\b(?:bana|için|şimdi|bir)\b","",s,flags=re.I)
 if style=="mixed_turkish_latin": return s.replace("açısı","angle").replace("soru","question")
 if style=="abbreviation": return s.replace("sınav için","sınavlık").replace("çoktan seçmeli","test")
 if style=="missing_spaces": return s.replace(" soru ","soru ").replace(" bunu ","bunu ")
 if style=="phonetic_spelling": return s.replace("değil","diil").replace("şimdi","simdi")
 if style=="self_correction_mid_sentence": return s+" yani yok, demek istediğim bu"
 return s

SURFACES={
 "explain":("anlat","açıkla","özetle","mantığını anlat","temel noktalarını açıkla"),
 "follow":("peki komplikasyonları?","bunun riskleri neler?","devamında ne olur?","klinikte neye dikkat edilir?","önemli sonuçları neler?"),
 "detail":("biraz daha detaylandır","daha ayrıntılı açıkla","biraz aç bunu","mekanizmasıyla anlat","detaylarını ekle"),
 "short":("daha kısa ve sınavlık yap","kısa özetle","sınav için özünü ver","en kritik yerleri kısalt","özet ve sınav odaklı yap"),
}

def build(i:int,seed=20261004)->Case:
 r=random.Random(seed+i*104729)
 interaction=INTERACTION[i%len(INTERACTION)]
 reference=REFERENCE[(i//len(INTERACTION))%len(REFERENCE)]
 state=STATE[(i//(len(INTERACTION)*len(REFERENCE)))%len(STATE)]
 language=LANGUAGE[(i*7)%len(LANGUAGE)]
 distractor=DISTRACTOR[(i*11)%len(DISTRACTOR)]
 distance=DISTANCE[(i*13)%len(DISTANCE)]
 t1=r.choice(TOPICS); t2=r.choice([x for x in TOPICS if x!=t1])
 history=[("user",f"{t1[0]} {r.choice(SURFACES['explain'])}."),("assistant",f"{t1[0]} açıklaması örnek {i%97}.")]
 must=list(t1[1]); bad=[]; expected={"topic":t1[0],"task":"explain"}
 # interaction defines the semantic transition; other axes perturb its surface/context.
 if interaction in {"topic_switch_explicit","same_task_new_topic"}:
  q=f"Peki {t2[0]} anlat."; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]
 elif interaction=="topic_switch_implicit":
  q=f"{t2[0]} peki"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]
 elif interaction in {"same_topic_new_task","format_switch"}:
  q="bunu test şeklinde yap"; expected["task"]="generate_questions"
 elif interaction=="goal_switch":
  q="bunu sınav için en önemli yerleriyle anlat"; expected["goal"]="exam"
 elif interaction=="scope_narrow":
  history=[("user",f"{t1[0]} konusunda 20 soru hazırla"),("assistant",_list(t1[0]))]
  q="13. sorunun konusunu anlat"; must+=["klinik soru 13"]; expected["reference"]="assistant_item_13"
 elif interaction=="regenerate":
  history += [("user","10 soru hazırla"),("assistant",_list(t1[0],10))]
  q="bunlar olmadı baştan 20 farklı soru hazırla"; expected.update(task="generate_questions",count=20)
 elif interaction=="correction":
  history=[("user",f"akut {t1[0]} anlat."),("assistant",f"akut {t1[0]} açıklaması.")]
  q="yok akut değil kronik olanı"; must=list(t1[1])+["kronik"]; bad=["akut"]; expected.update(topic=t1[0],correction="replace")
 elif interaction=="negation_override":
  history += [("user","10 test sorusu hazırla"),("assistant",_list(t1[0],10))]
  q="test istemiyorum normal anlat"; expected["task"]="explain"
 elif interaction=="return_to_old_topic":
  history += [("user",f"{t2[0]} anlat"),("assistant",f"{t2[0]} açıklaması")]
  q="yok bir önceki konuya dön"; bad=list(t2[1]); expected["topic"]=t1[0]
 elif interaction=="comparison_add_target":
  q=f"bunu {t2[0]} ile karşılaştır"; must+=list(t2[1]); expected["task"]="compare"
 elif interaction=="comparison_replace_target":
  history += [("user",f"bunu {t2[0]} ile karşılaştır"),("assistant","karşılaştırma")]
  t3=r.choice([x for x in TOPICS if x not in {t1,t2}]); q=f"yok {t2[0]} değil {t3[0]} ile"; must=list(t1[1])+list(t3[1]); bad=list(t2[1])
 elif interaction=="abandon_previous":
  q=f"boşver onu {t2[0]} nedir"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]
 elif interaction=="refinement": q=r.choice(SURFACES["short"]); expected.update(goal="exam",length="shorter")
 elif interaction=="expansion": q=r.choice(SURFACES["detail"]); expected["length"]="detailed"
 elif interaction=="recollection_far":
  fillers=[]
  for k in range(max(1,distance-1)): fillers += [("user",f"tamam {k}"),("assistant","tamam")]
  history=(history+fillers)[-8:]; q="ilk anlattığın konuya dön"
 elif interaction=="followup": q=r.choice(SURFACES["follow"])
 else: q="bunu biraz daha anlat"
 # Reference semantics: these axes must change the actual dialogue.
 if reference=="pronoun_o":
  q=q.replace("bunu","onu").replace("Bunu","Onu")
 elif reference=="previous_answer":
  q="az önce verdiğin cevapta "+q
 elif reference=="previous_user_turn":
  q="az önce sorduğum şey için "+q
 elif reference=="named_topic" and interaction not in {"topic_switch_explicit","topic_switch_implicit","same_task_new_topic","abandon_previous"}:
  q=f"{t1[0]} için "+q
 elif reference=="missing_antecedent":
  history=[("assistant","Genel bir açıklama yaptım.")]
  q="bunu biraz daha anlat"; must=[]; bad=[]; expected.update(should_abstain=True,forbidden_topics=tuple(term for _,terms in (t1,t2) for term in terms))
 elif reference=="ambiguous_antecedent":
  history=[("user",f"{t1[0]} ve {t2[0]} anlat."),("assistant","İki konuyu da açıkladım.")]
  q="bunu biraz daha anlat"; must=[]; bad=[]; expected["should_abstain"]=True
 elif reference in {"ordinal_item","ordinal_question","assistant_list_item"}:
  history=[("user",f"{t1[0]} konusunda 20 soru hazırla"),("assistant",_list(t1[0]))]
  q="13. sorunun konusunu anlat"; must=list(t1[1]); expected["reference"]="assistant_item_13"
 elif reference=="multi_hop":
  history=[("user",f"{t1[0]} konusunda 20 soru hazırla"),("assistant",_list(t1[0])),("user","13. sorunun konusunu anlat"),("assistant",f"{t1[0]} klinik soru 13 açıklaması")]
  q="sadece bu konudan 10 soru hazırla"; must=list(t1[1]); expected.update(reference="assistant_item_13",task="generate_questions",count=10)
 elif reference=="assistant_prose_forbidden_subject":
  history[-1]=("assistant",history[-1][1]+" İmplant ve ameloblastoma ayrıca örnek olabilir.")
  bad += ["implant","ameloblastoma"]

 # State mutations must not destroy deliberately unresolved reference cases.
 if expected.get("should_abstain"):
  pass
 elif state=="replace_count":
  history += [("user","10 soru hazırla"),("assistant","10 soru hazırlandı")]
  q="yok 20 soru olsun"; expected.update(task="generate_questions",count=20)
 elif state=="inherit_count":
  history += [("user","10 soru hazırla"),("assistant","10 soru hazırlandı")]
  q="aynı sayıda farklı soru hazırla"; expected.update(task="generate_questions",count=10)
 elif state=="replace_goal":
  history += [("user","ezberlemek için anlat"),("assistant","özet")]
  q="yok sınav için anlat"; expected["goal"]="exam"
 elif state=="clear_goal":
  history += [("user","sınav için anlat"),("assistant","özet")]
  q="sınav odaklı olmasın normal anlat"; expected["goal"]=None
 elif state=="replace_task":
  history += [("user","test hazırla"),("assistant","test")]
  q="yok soru istemiyorum normal anlat"; expected["task"]="explain"
 elif state=="replace_topic":
  history += [("user",f"{t1[0]} anlat"),("assistant","açıklama")]
  q=f"yok {t2[0]} anlat"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]
 elif state=="inherit_topic":
  q="aynı konudan devam et"; must=list(t1[1]); expected["topic"]=t1[0]
 elif state=="clear_topic":
  history += [("user",f"{t1[0]} anlat"),("assistant","açıklama")]
  q="önceki konuyu bırak, genel çalışma planı çıkar"; bad=list(t1[1]); must=[]; expected["topic"]=None
 elif state=="inherit_task":
  history += [("user",f"{t1[0]} için test hazırla"),("assistant","test")]
  q="aynı şekilde devam et"; expected["task"]="generate_questions"; must=list(t1[1])
 elif state=="clear_task":
  history += [("user","test hazırla"),("assistant","test")]
  q=f"testi bırak, {t1[0]} hakkında normal konuşalım"; expected["task"]="explain"; must=list(t1[1])
 elif state=="replace_format":
  history += [("user","madde madde anlat"),("assistant","maddeler")]
  q="yok tablo şeklinde ver"; expected["format"]="table"
 elif state=="inherit_format":
  history += [("user","tablo şeklinde anlat"),("assistant","tablo")]
  q="aynı formatta devam et"; expected["format"]="table"
 elif state=="clear_format":
  history += [("user","tablo şeklinde anlat"),("assistant","tablo")]
  q="tablo olmasın normal anlat"; expected["format"]=None
 elif state=="clear_count":
  history += [("user","10 soru hazırla"),("assistant","10 soru")]
  q="soru sayısı önemli değil, konuyu anlat"; expected.update(task="explain",count=None)
 elif state=="qualifier_add":
  q="bunu çocuk hastalar açısından anlat"; expected["qualifiers"]=("çocuk",)
 elif state=="qualifier_replace":
  history += [("user","çocuk hastalar açısından anlat"),("assistant","çocuk")]
  q="yok çocuk değil erişkin açısından"; expected["qualifiers"]=("erişkin",); expected["forbidden_qualifiers"]=("çocuk",)
 elif state=="qualifier_remove":
  history += [("user","çocuk hastalar açısından anlat"),("assistant","çocuk")]
  q="yaş grubunu boşver genel anlat"; expected["qualifiers"]=(); expected["forbidden_qualifiers"]=("çocuk",)
 elif state=="error_propagation_trap":
  history += [("assistant",f"Yanlışlıkla {t2[0]} dedim.")]
  q="önceki asıl konudan devam et"; must=list(t1[1]); bad=list(t2[1]); expected["topic"]=t1[0]
 elif state=="stale_state_trap":
  history += [("user",f"{t2[0]} için 10 test sorusu hazırla"),("assistant","hazırlandı")]
  q=f"boşver, {t1[0]} normal anlat"; must=list(t1[1]); bad=list(t2[1]); expected.update(topic=t1[0],task="explain")

 if expected.get("should_abstain"):
  pass
 elif distractor=="assistant_dental_terms": history[-1]=("assistant",history[-1][1]+" amalgam implant pulpitis periodontitis")
 elif distractor=="assistant_wrong_topic":
  history += [("assistant",f"Yanlış örnek olarak {t2[0]} diyebilirim.")]; bad += list(t2[1])
 elif distractor=="user_side_comment": history += [("user","bu arada yarın sınav var"),("assistant","anladım")]
 elif distractor=="irrelevant_turn": history += [("user","tamam sağ ol"),("assistant","rica ederim")]
 elif distractor=="two_candidate_topics": history += [("user",f"{t2[0]} de aklımda"),("assistant","not edildi")]
 elif distractor=="same_term_different_context": history += [("assistant","Aynı terim başka bir klinik bağlamda da kullanılabilir.")]
 elif distractor=="old_count": history += [("user","önceden 40 soru demiştim"),("assistant","not")]
 elif distractor=="old_format": history += [("user","önceden tablo istemiştim"),("assistant","not")]
 elif distractor=="old_goal": history += [("user","önceden ezber için istemiştim"),("assistant","not")]
 elif distractor=="old_qualifier": history += [("user","önceden sadece çocuk demiştim"),("assistant","not")]
 elif distractor=="quoted_old_question": history += [("user",f'Eski sorum şuydu: "{t2[0]} nedir?"'),("assistant","alıntıyı gördüm")]; bad += list(t2[1])
 # Distance is the number of prior messages separating the anchor user turn
 # from the current query, capped by the resolver's eight-message contract.
 target_turns=TURN_LENGTH[(i*17)%len(TURN_LENGTH)]
 desired_history=min(8,max(1,target_turns-1))
 if len(history)<desired_history:
  filler=[]
  while len(filler)+len(history)<desired_history:
   k=len(filler); filler.append(("assistant",f"ara açıklama {k}"))
  history=(filler+history)[-desired_history:]
 else:
  history=history[-desired_history:]
 q=_noise(q,language,r)
 axes={"interaction":interaction,"reference":reference,"state":state,"language":language,"distractor":distractor,"distance":distance,"turn_length":target_turns}
 raw=f"{i}|{seed}|{axes}|{history}|{q}|{must}|{bad}"; cid=hashlib.sha1(raw.encode()).hexdigest()[:12]
 return Case(cid,axes,tuple(history[-8:]),q,tuple(must),tuple(bad),expected)

def _semantic_signature(case:Case):
 return (case.history,case.query,case.must,case.must_not,tuple(sorted(case.expected.items(),key=lambda x:x[0])))

def validate_cases(cases):
 assert cases, "no generated cases"
 assert len({c.case_id for c in cases})==len(cases), "duplicate case ids"
 semantic_unique=len({_semantic_signature(c) for c in cases})
 ratio=semantic_unique/len(cases)
 assert ratio>=0.90, f"semantic diversity too low: {ratio:.4f}"
 if len(cases)>=5000:
  for axis,values in (("interaction",INTERACTION),("reference",REFERENCE),("state",STATE),("language",LANGUAGE),("distractor",DISTRACTOR),("distance",DISTANCE),("turn_length",TURN_LENGTH)):
   seen={c.axes.get(axis) for c in cases}
   missing=set(values)-seen
   assert not missing, f"{axis} coverage missing: {sorted(missing,key=str)}"
 assert any(c.expected.get("should_abstain") for c in cases), "no abstention cases"
 assert any(c.expected.get("reference")=="assistant_item_13" for c in cases), "no assistant-item reference cases"
 assert any(c.expected.get("count")==20 for c in cases), "no count replacement cases"
 # Observable-axis invariants prevent metadata-only coverage from passing.
 checks=(
  ("replace_count",lambda c:c.expected.get("count")==20),
  ("inherit_count",lambda c:c.expected.get("count")==10),
  ("clear_count",lambda c:c.expected.get("count") is None),
  ("replace_goal",lambda c:c.expected.get("goal")=="exam"),
  ("clear_goal",lambda c:"goal" in c.expected and c.expected.get("goal") is None),
  ("replace_topic",lambda c:c.expected.get("topic") is not None and bool(c.must_not)),
  ("clear_topic",lambda c:"topic" in c.expected and c.expected.get("topic") is None),
  ("inherit_topic",lambda c:bool(c.must)),
  ("replace_task",lambda c:c.expected.get("task")=="explain"),
  ("clear_task",lambda c:c.expected.get("task")=="explain"),
  ("inherit_task",lambda c:c.expected.get("task")=="generate_questions"),
  ("replace_format",lambda c:c.expected.get("format")=="table"),
  ("inherit_format",lambda c:c.expected.get("format")=="table"),
  ("clear_format",lambda c:"format" in c.expected and c.expected.get("format") is None),
  ("qualifier_add",lambda c:bool(c.expected.get("qualifiers"))),
  ("qualifier_replace",lambda c:bool(c.expected.get("qualifiers")) and bool(c.expected.get("forbidden_qualifiers"))),
  ("qualifier_remove",lambda c:bool(c.expected.get("forbidden_qualifiers"))),
  ("stale_state_trap",lambda c:bool(c.must_not)),
  ("error_propagation_trap",lambda c:bool(c.must_not)),
  ("missing_antecedent",lambda c:bool(c.expected.get("should_abstain"))),
  ("ambiguous_antecedent",lambda c:bool(c.expected.get("should_abstain"))),
  ("ordinal_item",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("ordinal_question",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("assistant_list_item",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("multi_hop",lambda c:c.expected.get("reference")=="assistant_item_13" and c.expected.get("count")==10),
  ("assistant_prose_forbidden_subject",lambda c:"implant" in c.must_not or "ameloblastoma" in c.must_not),
 )
 distractor_checks={
  "assistant_wrong_topic":lambda c:bool(c.must_not),
  "user_side_comment":lambda c:any("yarın sınav" in x[1] for x in c.history),
  "irrelevant_turn":lambda c:any("sağ ol" in x[1] for x in c.history),
  "two_candidate_topics":lambda c:any("aklımda" in x[1] for x in c.history),
  "old_count":lambda c:any("40 soru" in x[1] for x in c.history),
  "old_format":lambda c:any("tablo istemiştim" in x[1] for x in c.history),
  "old_goal":lambda c:any("ezber için" in x[1] for x in c.history),
  "old_qualifier":lambda c:any("sadece çocuk" in x[1] for x in c.history),
  "quoted_old_question":lambda c:bool(c.must_not),
 }
 for value,predicate in distractor_checks.items():
  subset=[c for c in cases if c.axes.get("distractor")==value and not c.expected.get("should_abstain")]
  if subset:
   ratio_ok=sum(bool(predicate(c)) for c in subset)/len(subset)
   assert ratio_ok>=0.70, f"distractor={value} is mostly metadata-only: {ratio_ok:.3f}"
 for value,predicate in checks:
  axis="state" if value in STATE else "reference"
  subset=[c for c in cases if c.axes.get(axis)==value and not c.expected.get("should_abstain")]
  if subset:
   ratio_ok=sum(bool(predicate(c)) for c in subset)/len(subset)
   assert ratio_ok>=0.80, f"{axis}={value} is mostly metadata-only: {ratio_ok:.3f}"
 return {"count":len(cases),"exact_unique":len({c.case_id for c in cases}),"semantic_unique":semantic_unique,"semantic_unique_ratio":ratio}

def generate(n=50000,seed=20261004):
 cases=[build(i,seed) for i in range(n)]
 validate_cases(cases)
 return cases
