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

def build(i:int,seed=20261004)->Case:
 r=random.Random(seed+i*104729)
 interaction=INTERACTION[i%len(INTERACTION)]
 reference=REFERENCE[(i//len(INTERACTION))%len(REFERENCE)]
 state=STATE[(i//(len(INTERACTION)*len(REFERENCE)))%len(STATE)]
 language=LANGUAGE[(i*7)%len(LANGUAGE)]
 distractor=DISTRACTOR[(i*11)%len(DISTRACTOR)]
 distance=DISTANCE[(i*13)%len(DISTANCE)]
 t1=r.choice(TOPICS); t2=r.choice([x for x in TOPICS if x!=t1])
 history=[("user",f"{t1[0]} anlat."),("assistant",f"{t1[0]} açıklaması.")]
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
  q="yok akut değil kronik olanı"; expected["correction"]="replace"
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
 elif interaction=="refinement": q="daha kısa ve sınavlık yap"; expected.update(goal="exam",length="shorter")
 elif interaction=="expansion": q="biraz daha detaylandır"; expected["length"]="detailed"
 elif interaction=="recollection_far":
  fillers=[]
  for k in range(max(1,distance-1)): fillers += [("user",f"tamam {k}"),("assistant","tamam")]
  history=(history+fillers)[-8:]; q="ilk anlattığın konuya dön"
 elif interaction=="followup": q="peki komplikasyonları?"
 else: q="bunu biraz daha anlat"
 if distractor=="assistant_dental_terms": history[-1]=("assistant",history[-1][1]+" amalgam implant pulpitis periodontitis")
 elif distractor=="irrelevant_turn": history += [("user","tamam sağ ol"),("assistant","rica ederim")]
 elif distractor=="two_candidate_topics": history += [("user",f"{t2[0]} de aklımda"),("assistant","not edildi")]
 q=_noise(q,language,r)
 axes={"interaction":interaction,"reference":reference,"state":state,"language":language,"distractor":distractor,"distance":distance}
 raw=f"{i}|{seed}|{axes}|{history}|{q}|{must}|{bad}"; cid=hashlib.sha1(raw.encode()).hexdigest()[:12]
 return Case(cid,axes,tuple(history[-8:]),q,tuple(must),tuple(bad),expected)

def generate(n=50000,seed=20261004):
 cases=[build(i,seed) for i in range(n)]
 assert len({c.case_id for c in cases})==n, "duplicate generated cases"
 return cases
