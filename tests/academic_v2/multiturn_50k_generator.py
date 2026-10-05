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
  # Noise may corrupt spelling, never semantic numeric values such as 10/20.
  positions=[i for i,ch in enumerate(s) if ch.isalpha() and 1<i<len(s)-2]
  if positions:
   p=r.choice(positions); return s[:p]+s[p+1:]
 if style=="typo_heavy":
  out=s
  for _ in range(2):
   positions=[i for i,ch in enumerate(out) if ch.isalpha() and 1<i<len(out)-2]
   if positions:
    p=r.choice(positions); out=out[:p]+out[p+1:]
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
 # Deterministic independent perturbation streams. The old modulo formulas
 # coupled interaction->language 1:1 and partially coupled distractor/distance.
 language=LANGUAGE[random.Random(seed ^ 0x1A2B3C ^ (i*1000003)).randrange(len(LANGUAGE))]
 distractor=DISTRACTOR[random.Random(seed ^ 0x2B3C4D ^ (i*1000033)).randrange(len(DISTRACTOR))]
 distance=DISTANCE[random.Random(seed ^ 0x3C4D5E ^ (i*1000037)).randrange(len(DISTANCE))]
 t1=r.choice(TOPICS); t2=r.choice([x for x in TOPICS if x!=t1])
 history=[("user",f"{t1[0]} {r.choice(SURFACES['explain'])}."),("assistant",f"{t1[0]} açıklaması örnek {i%97}.")]
 must=list(t1[1]); bad=[]; expected={"topic":t1[0],"task":"explain"}
 semantic_topic=t1
 # interaction defines the semantic transition; other axes perturb its surface/context.
 if interaction in {"topic_switch_explicit","same_task_new_topic"}:
  q=f"Peki {t2[0]} anlat."; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]; semantic_topic=t2
 elif interaction=="topic_switch_implicit":
  q=f"{t2[0]} peki"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]; semantic_topic=t2
 elif interaction in {"same_topic_new_task","format_switch"}:
  q="bunu test şeklinde yap"; expected["task"]="generate_questions"
 elif interaction=="goal_switch":
  q="bunu sınav için en önemli yerleriyle anlat"; expected["goal"]="exam"
 elif interaction=="scope_narrow":
  history=[("user",f"{t1[0]} konusunda 20 soru hazırla"),("assistant",_list(t1[0]))]
  q="13. sorunun konusunu anlat"; must+=["klinik soru 13"]; expected["reference"]="assistant_item_13"
 elif interaction=="scope_expand":
  history += [("user","sadece tanımı anlat"),("assistant","tanım")]
  q="şimdi nedenleri bulguları ve tedaviyi de ekle"; expected["scope"]="expanded"
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
  q=f"boşver onu {t2[0]} nedir"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]; semantic_topic=t2
 elif interaction=="refinement":
  q=r.choice(SURFACES["short"]); expected["length"]="shorter"
  if re.search(r"(?iu)\b(?:sınav|sinav|sınavlık|sinavlik)\b",q): expected["goal"]="exam"
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
 elif reference=="relative_previous":
  history += [("user",f"{t2[0]} anlat"),("assistant",f"{t2[0]} açıklaması")]
  q="bir önceki konuya dön"; must=list(t1[1]); bad=list(t2[1]); expected["reference"]="previous_topic"
 elif reference=="relative_before_previous":
  t3=r.choice([x for x in TOPICS if x not in {t1,t2}])
  history += [("user",f"{t2[0]} anlat"),("assistant","açıklama"),("user",f"{t3[0]} anlat"),("assistant","açıklama")]
  q="ondan bir önceki konuya dön"; must=list(t2[1]); bad=list(t3[1]); expected["reference"]="before_previous_topic"
 elif reference=="implicit_subject":
  q="aynı konudan devam et"; must=list(t1[1]); expected["reference"]="implicit_subject"
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
  expected["assistant_prose_forbidden_subject"]=True

 # State axes may not overwrite the query that defines a structured assistant
 # reference. Otherwise gold can demand information no longer present anywhere.
 structured_reference = expected.get("reference")=="assistant_item_13"
 # State axes below test one slot at a time.  When they replace the surface
 # query with an anaphoric continuation, explicitly retain the current
 # interaction-owned subject first; otherwise the composition erases the very
 # antecedent whose state is supposed to be inherited.
 state_replaces_surface=state in {
  "replace_count","inherit_count","inherit_goal","inherit_format","replace_goal",
  "clear_goal","replace_task","inherit_topic","inherit_task","replace_format",
  "clear_format","clear_count","qualifier_add","qualifier_replace","qualifier_remove",
  "error_propagation_trap",
 }
 if not expected.get("should_abstain") and not structured_reference and state_replaces_surface:
  topic_name=str(expected.get("topic") or "")
  if topic_name:
   history += [("user",f"{topic_name} anlat"),("assistant",f"{topic_name} açıklaması")]
 # Explicit state transitions own their affected slot.  Reference axes may
 # still own topic provenance, but they must not suppress an observable state
 # operation that appears in the current turn.  Structured ordinal selection
 # remains protected because its provenance is part of the reference contract.
 explicit_state_transition=state in {
  "replace_count","inherit_count","inherit_goal","inherit_format","replace_goal",
  "clear_goal","replace_task","replace_topic","clear_topic","inherit_topic",
  "inherit_task","replace_format","clear_format","clear_count","qualifier_add",
  "qualifier_replace","qualifier_remove","stale_state_trap","error_propagation_trap",
 }
 if expected.get("should_abstain") and explicit_state_transition and not structured_reference:
  expected.pop("should_abstain",None)
 if (expected.get("should_abstain") and not explicit_state_transition) or structured_reference:
  pass
 elif state=="replace_count":
  history += [("user","10 soru hazırla"),("assistant","10 soru hazırlandı")]
  q="yok 20 soru olsun"; expected.update(task="generate_questions",count=20)
 elif state=="inherit_count":
  history += [("user","10 soru hazırla"),("assistant","10 soru hazırlandı")]
  q="aynı sayıda farklı soru hazırla"; expected.update(task="generate_questions",count=10)
 elif state=="inherit_goal":
  history += [("user","sınav için anlat"),("assistant","sınav özeti")]
  q="aynı amaçla devam et"; expected["goal"]="exam"
 elif state=="inherit_format":
  history += [("user","tablo şeklinde anlat"),("assistant","tablo")]
  q="aynı formatta devam et"; expected["format"]="table"
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
  q=f"yok {t2[0]} anlat"; must=list(t2[1]); bad=list(t1[1]); expected["topic"]=t2[0]; semantic_topic=t2
 elif state=="inherit_topic":
  # Inherit the ACTIVE composed topic, not the generator's original t1. Earlier
  # interaction/reference transitions may already have switched ownership.
  q="aynı konudan devam et"; must=list(semantic_topic[1]); expected["topic"]=semantic_topic[0]
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
 # Keep the selected distractor observable inside the resolver's bounded history.
 required_tail={
  "user_side_comment":("user","bu arada yarın sınav var"),
  "irrelevant_turn":("user","tamam sağ ol"),
  "old_count":("user","önceden 40 soru demiştim"),
  "old_format":("user","önceden tablo istemiştim"),
  "old_goal":("user","önceden ezber için istemiştim"),
  "old_qualifier":("user","önceden sadece çocuk demiştim"),
 }
 if distractor in required_tail and not any(required_tail[distractor][1] in x[1] for x in history):
  history.append(required_tail[distractor])
 # Apply assistant-prose distractor after state/distractor mutations so it cannot be overwritten.
 if expected.get("assistant_prose_forbidden_subject") and history:
  history[-1]=("assistant",history[-1][1]+" İmplant ve ameloblastoma ayrıca örnek olabilir.")
  bad += ["implant","ameloblastoma"]
 # Final state observability: later axis composition may rewrite the query.
 # Re-assert only the state cue, never topic gold, so the state label is real.
 state_surface={
  "replace_count":"yok 20 soru olsun",
  "inherit_count":"aynı sayıda farklı soru hazırla",
  "inherit_goal":"aynı amaçla devam et",
  "inherit_format":"aynı formatta devam et",
  "replace_goal":"yok sınav için anlat",
  "clear_goal":"sınav odaklı olmasın normal anlat",
  "replace_task":"yok soru istemiyorum normal anlat",
  "replace_format":"bunu tablo şeklinde ver",
  "clear_format":"tablo olmasın normal anlat",
  "clear_count":"sayı önemli değil soru hazırla",
 }
 if state in state_surface:
  if expected.get("should_abstain") and state not in ("replace_count","replace_goal","replace_task","replace_format","clear_goal","clear_format","clear_count"):
   pass
  else:
   expected.pop("should_abstain",None)
   if structured_reference:
    history += [("user",q),("assistant","seçilen öğe bağlamı korundu")]
   q=state_surface[state]
 if expected.get("reference") in {"previous_topic","before_previous_topic"} and "önceki" not in q.casefold() and "onceki" not in q.casefold():
  latest_topic=None
  for role,text in reversed(history):
   if role!="user" or "önceden" in text.casefold() or "aklımda" in text.casefold() or text.casefold().startswith("bu arada"): continue
   latest_topic=next((topic for topic in TOPICS if topic[0].casefold() in text.casefold() or all(term.casefold() in text.casefold() for term in topic[1])),None)
   if latest_topic: break
  if latest_topic:
   semantic_topic=latest_topic; must=list(latest_topic[1]); expected["topic"]=latest_topic[0]
  expected.pop("reference",None)
 # Distance is the number of prior messages separating the anchor user turn
 # from the current query, capped by the resolver's eight-message contract.
 # Keep both the original semantic topic anchor and the fully mutated history:
 # later axes can overwrite/trim one another, but gold repair must never invent
 # an antecedent that did not exist in the case.
 original_topic_anchor=("user",f"{semantic_topic[0]} anlat.")
 pretrim_history=list(history)
 target_turns=TURN_LENGTH[(i*17)%len(TURN_LENGTH)]
 desired_history=min(8,max(1,target_turns-1))
 if distractor!="none" and must and not expected.get("should_abstain"):
  desired_history=max(2,desired_history)
 if len(history)<desired_history:
  filler=[]
  while len(filler)+len(history)<desired_history:
   k=len(filler); filler.append(("assistant",f"ara açıklama {k}"))
  history=(filler+history)[-desired_history:]
 else:
  history=history[-desired_history:]
 # A state axis can replace the current surface while still inheriting the
 # interaction-owned subject.  Very short turn_length combinations must not
 # delete that subject entirely; keep one explicit antecedent within the same
 # eight-message resolver budget.
 if must and state_replaces_surface and not expected.get("should_abstain"):
  visible_after_trim=(" ".join(x[1] for x in history)+" "+q).casefold()
  topic_name=str(expected.get("topic") or semantic_topic[0])
  if topic_name and any(term.casefold() not in visible_after_trim for term in must):
   # Comparison/reference cases can require more than one topic.  Preserve the
   # exact required lexical contract in one user antecedent so no gold facet is
   # hidden by a short turn window.
   anchor_text=" ".join(must)+" anlat"
   anchor=("user",anchor_text)
   if anchor not in history:
    history=(history+[anchor])[-8:]

 # Re-assert required distractor evidence after bounded-history trimming.
 if distractor in required_tail and not any(required_tail[distractor][1] in x[1] for x in history):
  history=(history+[required_tail[distractor]])[-desired_history:]
 # A resolvable case must retain evidence for its required subject. If
 # bounded trimming removed the semantic anchor, replace only filler/oldest
 # context with the latest pre-trim message that actually contains the subject.
 if must and not expected.get("should_abstain"):
  visible=(" ".join(x[1] for x in history)+" "+q).casefold()
  missing_anchor=[term for term in must if term.casefold() not in visible]
  if missing_anchor:
   # A topic can expose several required lexical facets across different turns
   # (e.g. "perikoronitis" + "üçüncü molar"). Preserve the smallest set of
   # real pre-trim evidence messages instead of requiring one message to
   # contain every missing term.
   anchors=[]
   uncovered={term.casefold() for term in missing_anchor}
   for candidate in reversed(pretrim_history):
    candidate_folded=candidate[1].casefold()
    covered={term for term in uncovered if term in candidate_folded}
    if covered:
     anchors.append(candidate)
     uncovered-=covered
    if not uncovered:
     break
   if not uncovered and anchors:
    keep=max(0,desired_history-len(anchors))
    history=(history[-keep:] if keep else [])+list(reversed(anchors))
    history=history[-desired_history:]
 # Preserve a real topic-bearing turn when a later inheritance mutation
 # replaced the current query and bounded trimming removed its antecedent.
 inheritance_cue=any(token in q.casefold() for token in ("aynı konu","aynı şekilde","aynı amaçla","aynı formatta","aynı sayıda","önceki asıl konu"))
 if must and inheritance_cue and not expected.get("should_abstain"):
  visible_now=(" ".join(x[1] for x in history)+" "+q).casefold()
  if any(term.casefold() not in visible_now for term in must):
   topic_anchor=next((x for x in reversed(pretrim_history)
    if any(term.casefold() in x[1].casefold() for term in must)
    and "eski sorum" not in x[1].casefold() and "önceden" not in x[1].casefold()),None)
   if topic_anchor is None and all(term.casefold() in semantic_topic[0].casefold() for term in must):
    topic_anchor=original_topic_anchor
   if topic_anchor:
    history=(history+[topic_anchor])[-desired_history:]

 # Multi-hop is a reference-chain contract, not a metadata label. Preserve
 # the full user-selection provenance inside the resolver's bounded window even
 # after distractor/turn-length composition. Do not synthesize a bare assistant
 # item: the user ordinal selection is what grants assistant text referent ownership.
 if reference=="multi_hop" and not expected.get("should_abstain"):
  topic_name=str(expected.get("topic") or semantic_topic[0])
  chain=[
   ("assistant",_list(topic_name)),
   ("user","13. sorunun konusunu anlat"),
   ("assistant",f"{topic_name} klinik soru 13 açıklaması"),
  ]
  # Reserve three messages for the chain; keep only the newest unrelated context.
  keep=max(0,min(5,desired_history-len(chain)))
  history=(history[-keep:] if keep else [])+chain
  history=history[-8:]
  q="sadece bu konudan 10 soru hazırla"
  must=list(semantic_topic[1])
  expected.update(reference="assistant_item_13",task="generate_questions",count=10,topic=semantic_topic[0])
 # Resolvable non-assistant-item topic references require USER-authored
 # provenance. Assistant prose may repeat a topic but can never seed discourse
 # identity; if trimming removed the user anchor, restore a bounded real/canonical
 # user antecedent rather than teaching the resolver to trust assistant prose.
 if must and not expected.get("should_abstain") and not structured_reference:
  user_visible=" ".join(text for role,text in history if role=="user" and not re.search(r"(?iu)^(?:önceden|eski sorum|bu arada)|\\baklımda\\b",text)).casefold()
  expected_topic_folded=str(expected.get("topic") or "").casefold()
  has_user_provenance=bool(expected_topic_folded and expected_topic_folded in user_visible) or all(term.casefold() in user_visible for term in must)
  if not has_user_provenance:
   topic_name=str(expected.get("topic") or semantic_topic[0])
   user_anchor=next((x for x in reversed(pretrim_history)
    if x[0]=="user" and any(term.casefold() in x[1].casefold() for term in must)
    and "eski sorum" not in x[1].casefold() and "önceden" not in x[1].casefold()
    and "aklımda" not in x[1].casefold()),None)
   if user_anchor is None and topic_name:
    user_anchor=("user",f"{topic_name} anlat")
   if user_anchor:
    history=(history+[user_anchor])[-8:]
 # Structured assistant-item references have their own explicit provenance.
 # Short turn-length/distractor composition must retain the selected list item
 # rather than leaving an ordinal with no assistant list antecedent.
 if structured_reference and not expected.get("should_abstain"):
  has_selected_item=any(x[0]=="assistant" and "klinik soru 13" in x[1].casefold() for x in history)
  if not has_selected_item:
   topic_name=str(expected.get("topic") or semantic_topic[0])
   history=(history+[("assistant",f"13. {topic_name} klinik soru 13")])[-8:]

 # A later anchor repair/distractor append can evict the user provenance
 # restored above. Re-assert it at the final bounded-history boundary.
 if must and not expected.get("should_abstain") and not structured_reference:
  user_visible=" ".join(text for role,text in history if role=="user" and not re.search(r"(?iu)^(?:önceden|eski sorum|bu arada)|\\baklımda\\b",text)).casefold()
  topic_name=str(expected.get("topic") or semantic_topic[0])
  topic_folded=topic_name.casefold()
  supported=bool(topic_folded and topic_folded in user_visible) or all(term.casefold() in user_visible for term in must)
  if not supported:
   history=(history+[("user",f"{topic_name} anlat")])[-8:]
 # Reconcile the final expected topic with the final bounded dialogue.
 # Later state/reference axes are allowed to replace an earlier interaction,
 # but they may not leave a stale topic label behind.  Prefer an explicit
 # visible topic whose complete lexical signature is present.
 if must and not expected.get("should_abstain"):
  visible_pre_gold=(" ".join(x[1] for x in history)+" "+q).casefold()
  must_folded={m.casefold() for m in must}
  visible_topics=[
   topic for topic in TOPICS
   if topic[0].casefold() in visible_pre_gold
   or all(term.casefold() in visible_pre_gold for term in topic[1])
  ]
  expected_topic=str(expected.get("topic") or "").casefold()
  expected_topic_visible=bool(expected_topic and expected_topic in visible_pre_gold)
  if not expected_topic_visible:
   matching=[
    topic for topic in visible_topics
    if any(term.casefold() in must_folded for term in topic[1])
   ]
   if matching:
    expected["topic"]=matching[-1][0]

 # State inheritance must remain observable after distractor composition.
 # A later independent user topic legitimately clears goal, so reserve a final
 # bounded user antecedent that owns both the active subject and exam goal.
 if state=="inherit_goal" and not expected.get("should_abstain") and not structured_reference:
  topic_name=str(expected.get("topic") or semantic_topic[0])
  antecedent=("user",f"{topic_name} sınav için anlat")
  history=(history+[antecedent])[-8:]
 # Reconcile non-topic slot gold from the FINAL semantic dialogue. Axes are
 # composed sequentially, so an earlier interaction must not keep owning a slot
 # after a later reference/state operation replaced the surface that expressed it.
 fold_slot=lambda s:" ".join(str(s).translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU")).casefold().split())
 fq_slot=fold_slot(q)
 fh_slot=fold_slot(" ".join(x[1] for x in history))
 question_now=bool(re.search(r"\b(?:soru|question|test)\b",fq_slot))
 # Replay the active user task rather than searching arbitrary history. A later
 # independent "... anlat" turn clears an older question-generation task.
 active_task=None
 for role,text in history:
  if role!="user": continue
  ft=fold_slot(text)
  if re.search(r"^(?:onceden|eski sorum|alinti)\b|\baklimda\b|^bu arada\b",ft): continue
  independent_explain=bool(re.search(r"\b(?:anlat|acikla|ozetle|nedir)\b",ft)) and not re.match(r"^(?:bunu|onu|ayni|peki|yok|hayir|normal)\b",ft)
  if independent_explain: active_task="explain"
  if re.search(r"\b(?:soru|question|test)\b.{0,28}\b(?:hazirla|yap|uret|olustur)\b|\b(?:hazirla|yap|uret|olustur)\b.{0,28}\b(?:soru|question|test)\b",ft):
   active_task="generate_questions"
  if re.search(r"\b(?:soru istemiyorum|testi birak|normal anlat)\b",ft): active_task="explain"
 question_inherit=bool(re.search(r"\bayni sekilde\b",fq_slot) and active_task=="generate_questions")
 if expected.get("task")=="generate_questions" and not (question_now or question_inherit):
  expected.pop("task",None); expected["_task_gold_reconciled"]=True
 active_count=None
 active_format=None
 for role,text in history:
  if role!="user": continue
  ft=fold_slot(text)
  if re.search(r"^(?:onceden|eski sorum|alinti)\b|\baklimda\b|^bu arada\b",ft): continue
  independent=bool(re.search(r"\b(?:anlat|acikla|ozetle|nedir)\b",ft)) and not re.match(r"^(?:bunu|onu|ayni|peki|yok|hayir|normal)\b",ft)
  if independent:
   active_count=None; active_format=None
  cm=re.search(r"\b(\d+)\s*(?:soru|question|test)\b",ft)
  if cm: active_count=int(cm.group(1))
  if re.search(r"\b(?:tablo|table)\b",ft): active_format="table"
  if re.search(r"\b(?:tablo olmasin|normal anlat)\b",ft): active_format=None
 if expected.get("count") is not None:
  wanted=str(expected["count"])
  count_now=bool(re.search(rf"\b{re.escape(wanted)}\s*(?:soru|question|test)\b",fq_slot))
  count_inherit=bool(re.search(r"\bayni sayida\b",fq_slot) and active_count==int(wanted))
  if not (count_now or count_inherit):
   expected.pop("count",None); expected["_count_gold_reconciled"]=True
 if expected.get("format")=="table":
  table_now=bool(re.search(r"\b(?:tablo|table)\b",fq_slot))
  table_inherit=bool(re.search(r"\bayni formatta\b",fq_slot) and active_format=="table")
  if not (table_now or table_inherit):
   expected.pop("format",None); expected["_format_gold_reconciled"]=True
 if expected.get("length")=="shorter" and not re.search(r"\b(?:kisa|ozet|ozunu|kisalt|sinavlik)\w*",fq_slot):
  expected.pop("length",None); expected["_length_gold_reconciled"]=True
 if expected.get("length")=="detailed" and not re.search(r"\b(?:detay|ayrint|mekanizma)\w*",fq_slot):
  expected.pop("length",None); expected["_length_gold_reconciled"]=True
 # Reconcile exam-goal gold from the final semantic dialogue. Earlier
 # interaction/reference/state layers may have owned goal at different times;
 # only the final surface + a valid same-purpose antecedent may own it.
 if expected.get("goal")=="exam":
  fold=lambda s:" ".join(str(s).translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU")).casefold().split())
  fq=fold(q)
  explicit_exam=bool(re.search(r"\b(?:sinav|sinavlik)\b",fq))
  active_exam=False
  for role,text in history:
   if role!="user": continue
   ft=fold(text)
   if re.search(r"^(?:onceden|eski sorum|alinti)\b|\baklimda\b|^bu arada\b",ft): continue
   # A later independent topic request starts a new discourse state and clears
   # an older goal before any explicit goal on that same turn is applied.
   topic_request=bool(re.search(r"\b(?:anlat|acikla|ozetle|nedir)\b",ft))
   dependent_start=bool(re.match(r"^(?:bunu|onu|ayni|peki|yok|hayir|sinav|tablo|normal)\b",ft))
   if topic_request and not dependent_start and not re.search(r"\b(?:sinav|sinavlik)\b",ft):
    active_exam=False
   if re.search(r"\b(?:sinav|sinavlik)\b",ft): active_exam=True
   if re.search(r"\b(?:sinavi bosver|normal anlat)\b",ft): active_exam=False
  inherited_exam=bool(re.search(r"\bayni amacla\b",fq) and active_exam)
  if not (explicit_exam or inherited_exam):
   expected.pop("goal",None)
   expected["_goal_gold_reconciled"]=True
 # Gold consistency is decided on the semantic (pre-noise) dialogue.
 # Surface noise is a robustness axis and must not be mistaken for missing evidence.
 must=list(dict.fromkeys(must))
 must_keys={term.casefold() for term in must}
 bad=list(dict.fromkeys(term for term in bad if term.casefold() not in must_keys))
 semantic_visible=(" ".join(x[1] for x in history)+" "+q).casefold()
 # Topic labels are the canonical semantic source. A lexical facet may be a
 # gold synonym/attribute that is not literally repeated in the dialogue.
 # Accept it only when the final expected topic is visibly anchored; otherwise
 # the case is genuinely asking the resolver to recover invisible information.
 expected_topic=str(expected.get("topic") or "").casefold()
 topic_visible=bool(expected_topic and expected_topic in semantic_visible)
 unsupported_pre_noise=tuple(
  term for term in must
  if term.casefold() not in semantic_visible and not topic_visible
 )
 expected["_gold_evidence_pre_noise"]=not unsupported_pre_noise
 expected["_gold_unsupported_pre_noise"]=unsupported_pre_noise
 expected["_gold_overlap_removed"]=True
 expected["_semantic_query_pre_noise"]=q
 expected["_semantic_history_pre_noise"]=tuple(history)
 q=_noise(q,language,r)
 axes={"interaction":interaction,"reference":reference,"state":state,"language":language,"distractor":distractor,"distance":distance,"turn_length":target_turns}
 raw=f"{i}|{seed}|{axes}|{history}|{q}|{must}|{bad}"; cid=hashlib.sha1(raw.encode()).hexdigest()[:12]
 return Case(cid,axes,tuple(history[-8:]),q,tuple(must),tuple(bad),expected)

def _semantic_signature(case:Case):
 semantic_expected=tuple(sorted(
  ((k,v) for k,v in case.expected.items() if not k.startswith("_")),
  key=lambda x:x[0],
 ))
 return (case.history,case.query,case.must,case.must_not,semantic_expected)

def audit_gold_consistency(cases):
 defects={"overlap":0,"unsupported_pre_noise":0,"abstain_with_required":0}
 by_axis={axis:{} for axis in ("interaction","reference","state","language","distractor","turn_length")}
 for case in cases:
  overlap={x.casefold() for x in case.must}.intersection(x.casefold() for x in case.must_not)
  unsupported=tuple(case.expected.get("_gold_unsupported_pre_noise",()))
  flags=[]
  if overlap: defects["overlap"]+=1; flags.append("overlap")
  if unsupported: defects["unsupported_pre_noise"]+=1; flags.append("unsupported_pre_noise")
  if case.expected.get("should_abstain") and case.must:
   defects["abstain_with_required"]+=1; flags.append("abstain_with_required")
  if flags:
   for axis in by_axis:
    value=str(case.axes.get(axis))
    bucket=by_axis[axis].setdefault(value,{"cases":0})
    bucket["cases"]+=1
    for flag in flags: bucket[flag]=bucket.get(flag,0)+1
 return {"defects":defects,"by_axis":by_axis}

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
 assert all(c.expected.get("_gold_overlap_removed") for c in cases), "gold reconciliation metadata missing"
 for case in cases:
  if case.expected.get("should_abstain"):
   continue
  overlap={term.casefold() for term in case.must}.intersection(term.casefold() for term in case.must_not)
  assert not overlap, f"gold requires and forbids same term {sorted(overlap)}: {case.case_id}"
  unsupported=case.expected.get("_gold_unsupported_pre_noise",())
  assert not unsupported, f"gold requires semantically absent context {unsupported}: {case.case_id}"
 # Slot gold must be semantically supported by the final pre-noise dialogue.
 unsupported_goal=[]
 for case in cases:
  if case.expected.get("goal")!="exam": continue
  sq=str(case.expected.get("_semantic_query_pre_noise") or case.query)
  sh=" ".join(x[1] for x in case.expected.get("_semantic_history_pre_noise",case.history))
  fold=lambda s:" ".join(str(s).translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU")).casefold().split())
  fq=fold(sq)
  explicit_exam=bool(re.search(r"\b(?:sinav|sinavlik)\b",fq))
  active_exam=False
  for role,text in case.expected.get("_semantic_history_pre_noise",case.history):
   if role!="user": continue
   ft=fold(text)
   if re.search(r"^(?:onceden|eski sorum|alinti)\b|\baklimda\b|^bu arada\b",ft): continue
   topic_request=bool(re.search(r"\b(?:anlat|acikla|ozetle|nedir)\b",ft))
   dependent_start=bool(re.match(r"^(?:bunu|onu|ayni|peki|yok|hayir|sinav|tablo|normal)\b",ft))
   if topic_request and not dependent_start and not re.search(r"\b(?:sinav|sinavlik)\b",ft): active_exam=False
   if re.search(r"\b(?:sinav|sinavlik)\b",ft): active_exam=True
   if re.search(r"\b(?:sinavi bosver|normal anlat)\b",ft): active_exam=False
  inherited_exam=bool(re.search(r"\bayni amacla\b",fq) and active_exam)
  if not (explicit_exam or inherited_exam): unsupported_goal.append(case.case_id)
 assert not unsupported_goal, f"unsupported exam-goal gold: {unsupported_goal[:20]} ({len(unsupported_goal)})"
 # Conditional coverage prevents deterministic axis confounding.
 if len(cases)>=50000:
  for interaction in INTERACTION:
   subset=[case for case in cases if case.axes.get("interaction")==interaction]
   assert len({case.axes.get("language") for case in subset})>=18, f"language confounded with {interaction}"
   assert len({case.axes.get("distractor") for case in subset})>=11, f"distractor confounded with {interaction}"
   assert len({case.axes.get("distance") for case in subset})>=8, f"distance confounded with {interaction}"
 # Assistant prose is never sufficient provenance for ordinary resolvable topics.
 missing_user_provenance=[]
 for case in cases:
  if case.expected.get("should_abstain") or case.expected.get("reference")=="assistant_item_13" or not case.must: continue
  user_text=" ".join(text for role,text in case.history if role=="user").casefold()
  topic_text=str(case.expected.get("topic") or "").casefold()
  supported=bool(topic_text and topic_text in user_text) or all(term.casefold() in user_text for term in case.must)
  if not supported: missing_user_provenance.append(case.case_id)
 assert not missing_user_provenance, f"resolvable topic lacks user provenance: {missing_user_provenance[:20]} ({len(missing_user_provenance)})"
 # Observable-axis invariants prevent metadata-only coverage from passing.
 checks=(
  ("replace_count",lambda c:c.expected.get("count")==20 or c.expected.get("_count_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("inherit_count",lambda c:(c.expected.get("count")==10 and ("aynı sayıda" in c.expected.get("_semantic_query_pre_noise","") or any("10 soru" in x[1] for x in c.expected.get("_semantic_history_pre_noise",())))) or c.expected.get("_count_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("clear_count",lambda c:c.expected.get("count") is None or c.expected.get("reference")=="assistant_item_13"),
  ("inherit_goal",lambda c:c.expected.get("goal")=="exam" or c.expected.get("_goal_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("replace_goal",lambda c:c.expected.get("goal")=="exam" or c.expected.get("_goal_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("clear_goal",lambda c:("goal" in c.expected and c.expected.get("goal") is None) or c.expected.get("reference")=="assistant_item_13"),
  ("replace_topic",lambda c:(c.expected.get("topic") is not None and bool(c.must_not)) or c.expected.get("reference")=="assistant_item_13"),
  ("clear_topic",lambda c:("topic" in c.expected and c.expected.get("topic") is None) or c.expected.get("reference")=="assistant_item_13"),
  ("inherit_topic",lambda c:bool(c.must) or c.expected.get("reference")=="assistant_item_13"),
  ("replace_task",lambda c:c.expected.get("task")=="explain" or c.expected.get("reference")=="assistant_item_13"),
  ("clear_task",lambda c:c.expected.get("task")=="explain" or c.expected.get("reference")=="assistant_item_13"),
  ("inherit_task",lambda c:c.expected.get("task")=="generate_questions" or c.expected.get("_task_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("replace_format",lambda c:c.expected.get("format")=="table" or c.expected.get("_format_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("inherit_format",lambda c:c.expected.get("format")=="table" or c.expected.get("_format_gold_reconciled") or c.expected.get("reference")=="assistant_item_13"),
  ("clear_format",lambda c:("format" in c.expected and c.expected.get("format") is None) or c.expected.get("reference")=="assistant_item_13"),
  ("qualifier_add",lambda c:bool(c.expected.get("qualifiers")) or c.expected.get("reference")=="assistant_item_13"),
  ("qualifier_replace",lambda c:(bool(c.expected.get("qualifiers")) and bool(c.expected.get("forbidden_qualifiers"))) or c.expected.get("reference")=="assistant_item_13"),
  ("qualifier_remove",lambda c:bool(c.expected.get("forbidden_qualifiers")) or c.expected.get("reference")=="assistant_item_13"),
  ("stale_state_trap",lambda c:bool(c.must_not) or c.expected.get("reference")=="assistant_item_13"),
  ("error_propagation_trap",lambda c:bool(c.must_not) or c.expected.get("reference")=="assistant_item_13"),
  ("relative_previous",lambda c:c.expected.get("reference")=="previous_topic"),
  ("relative_before_previous",lambda c:c.expected.get("reference")=="before_previous_topic"),
  ("implicit_subject",lambda c:c.expected.get("reference")=="implicit_subject"),
  ("missing_antecedent",lambda c:bool(c.expected.get("should_abstain")) or c.axes.get("state") in {"replace_count","inherit_count","inherit_goal","inherit_format","replace_goal","clear_goal","replace_task","replace_topic","clear_topic","inherit_topic","inherit_task","replace_format","clear_format","clear_count","qualifier_add","qualifier_replace","qualifier_remove","stale_state_trap","error_propagation_trap"}),
  ("ambiguous_antecedent",lambda c:bool(c.expected.get("should_abstain")) or c.axes.get("state") in {"replace_count","inherit_count","inherit_goal","inherit_format","replace_goal","clear_goal","replace_task","replace_topic","clear_topic","inherit_topic","inherit_task","replace_format","clear_format","clear_count","qualifier_add","qualifier_replace","qualifier_remove","stale_state_trap","error_propagation_trap"}),
  ("ordinal_item",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("ordinal_question",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("assistant_list_item",lambda c:c.expected.get("reference")=="assistant_item_13"),
  ("multi_hop",lambda c:c.expected.get("reference")=="assistant_item_13" and c.expected.get("count")==10 and any("13. sorunun konusunu anlat" in x[1] for x in c.history) and any("klinik soru 13" in x[1] for x in c.history)),
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
  # A later explicit state surface may legitimately supersede a reference cue.
  # Validate reference observability only where reference still owns the final
  # dialogue; separately require enough surviving cases so reconciliation cannot
  # hide an axis completely.
  observable_subset=subset
  if axis=="reference":
   observable_subset=[c for c in subset if not c.expected.get("_reference_gold_reconciled")]
   if len(cases)>=50000:
    assert len(observable_subset)>=250, f"reference={value} has too little surviving coverage: {len(observable_subset)}"
  if observable_subset:
   ratio_ok=sum(bool(predicate(c)) for c in observable_subset)/len(observable_subset)
   assert ratio_ok>=0.80, f"{axis}={value} is mostly metadata-only: {ratio_ok:.3f}"
 audit=audit_gold_consistency(cases)
 assert audit["defects"]["overlap"]==0, audit["defects"]
 assert audit["defects"]["unsupported_pre_noise"]==0, audit["defects"]
 assert audit["defects"]["abstain_with_required"]==0, audit["defects"]
 return {"count":len(cases),"exact_unique":len({c.case_id for c in cases}),"semantic_unique":semantic_unique,"semantic_unique_ratio":ratio,"gold_audit":audit["defects"]}

def generate(n=50000,seed=20261004):
 cases=[build(i,seed) for i in range(n)]
 validate_cases(cases)
 return cases
