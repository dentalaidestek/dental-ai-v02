"""Run the 50k deterministic multi-turn continuity benchmark."""
from __future__ import annotations
import argparse,json,time,unicodedata
from collections import Counter,defaultdict
# benchmark revision: post-ordinal-typo
from pathlib import Path
from app.study_retrieval_v2 import resolve_followup_query
from tests.academic_v2.multiturn_50k_generator import generate, validate_cases

def n(s):
 # Unicode decomposition removes combining accents but does not fold Turkish
 # dotless ı. Hard-coded semantic checks use ASCII (sinav/kisa/ayrinti), so use
 # the same Turkish fold contract as the conversation state engine first.
 s=str(s or "").translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU"))
 s=unicodedata.normalize("NFKD",s).casefold()
 s="".join(ch for ch in s if not unicodedata.combining(ch))
 return " ".join(s.split())

def has_term(text,term):
 term=n(term)
 if not term:return False
 return bool(__import__("re").search(r"(?<!\\w)"+__import__("re").escape(term)+r"(?!\\w)",text))

def score(case):
 hist=[{"role":r,"content":c} for r,c in case.history]
 try: out=resolve_followup_query(case.query,hist)
 except Exception as e:return False,"exception",repr(e),""
 z=n(out)
 exp=case.expected
 if exp.get("should_abstain"):
  leaked=[x for x in exp.get("forbidden_topics",()) if has_term(z,x) and not has_term(n(case.query),x)]
  if leaked:return False,"resolved_but_should_abstain"," | ".join(leaked),out
  return True,"ok","",""
 miss=[x for x in case.must if not has_term(z,x)]
 qz=n(case.query)
 resolver_context=z.replace(qz,"",1) if qz and qz in z else z
 stale=[x for x in case.must_not if has_term(resolver_context,x) or (has_term(z,x) and not has_term(qz,x))]
 if miss:return False,"missing_required"," | ".join(miss),out
 if stale:return False,"stale_context"," | ".join(stale),out
 if exp.get("task")=="generate_questions" and not any(x in z for x in ("soru","test")):return False,"task_loss","generate_questions",out
 if exp.get("goal")=="exam" and "sinav" not in z:return False,"goal_loss","exam",out
 if exp.get("count") and str(exp["count"]) not in z:return False,"count_loss",str(exp["count"]),out
 if exp.get("format")=="table" and not any(x in z for x in ("tablo","table")):return False,"format_loss","table",out
 if exp.get("format") is None and "tablo" in z and "tablo" not in n(case.query):return False,"stale_format","table",out
 for x in exp.get("qualifiers",()):
  if not has_term(z,x):return False,"qualifier_loss",x,out
 for x in exp.get("forbidden_qualifiers",()):
  if has_term(resolver_context,x) or (has_term(z,x) and not has_term(qz,x)):return False,"stale_qualifier",x,out
 if exp.get("length")=="shorter" and not any(x in z for x in ("kisa","oz")):return False,"length_loss","shorter",out
 if exp.get("length")=="detailed" and not any(x in z for x in ("detay","ayrinti","kapsam")):return False,"length_loss","detailed",out
 return True,"ok","",out

def main():
 p=argparse.ArgumentParser();p.add_argument("--count",type=int,default=50000);p.add_argument("--seed",type=int,default=20261004);p.add_argument("--report",default="artifacts/multiturn_50k_report.json");a=p.parse_args()
 cases=generate(a.count,a.seed); quality=validate_cases(cases); reasons=Counter(); axes=defaultdict(lambda:defaultdict(lambda:[0,0])); samples=[]; reason_samples=defaultdict(list); failure_axes=defaultdict(Counter); failure_combos=defaultdict(Counter); failure_pairs=defaultdict(Counter); t=time.perf_counter()
 for c in cases:
  ok,reason,detail,out=score(c); reasons[reason]+=1
  if not ok:
   if len(reason_samples[reason])<20: reason_samples[reason].append({"id":c.case_id,"axes":c.axes,"query":c.query,"history":c.history,"expected":c.expected,"must":c.must,"must_not":c.must_not,"detail":detail,"resolved":out})
   for axis,val in c.axes.items(): failure_axes[reason][f"{axis}={val}"]+=1
   failure_combos[reason][(str(c.axes.get("interaction")),str(c.axes.get("reference")),str(c.axes.get("state")),str(c.axes.get("language")),str(c.axes.get("turn_length")))]+=1
   for left,right in (("reference","state"),("language","state"),("reference","language"),("interaction","state"),("interaction","reference")):
    failure_pairs[reason][f"{left}={c.axes.get(left)} | {right}={c.axes.get(right)}"]+=1
  for axis,val in c.axes.items():
   axes[axis][str(val)][0]+=1;axes[axis][str(val)][1]+=int(ok)
  if not ok and len(samples)<500:samples.append({"id":c.case_id,"axes":c.axes,"query":c.query,"history":c.history,"expected":c.expected,"must":c.must,"must_not":c.must_not,"reason":reason,"detail":detail,"resolved":out})
 elapsed=time.perf_counter()-t
 axis_report={ax:{v:{"n":q[0],"passed":q[1],"accuracy":q[1]/q[0]} for v,q in vals.items()} for ax,vals in axes.items()}
 failure_diagnostics={reason:{"top_axes":counter.most_common(40),"top_pairs":failure_pairs[reason].most_common(80),"top_combinations":[{"interaction":k[0],"reference":k[1],"state":k[2],"language":k[3],"turn_length":k[4],"n":v} for k,v in failure_combos[reason].most_common(40)]} for reason,counter in failure_axes.items()}
 report={"count":len(cases),"seed":a.seed,"quality":quality,"passed":reasons["ok"],"accuracy":reasons["ok"]/len(cases),"elapsed_s":elapsed,"cases_per_s":len(cases)/max(elapsed,.001),"failure_reasons":dict(reasons),"axes":axis_report,"failure_diagnostics":failure_diagnostics,"reason_samples":reason_samples,"failure_samples":samples}
 path=Path(a.report);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in report.items() if k not in {"failure_samples","axes"}},ensure_ascii=False,indent=2))
 worst=[]
 for ax,vals in axis_report.items():
  for val,d in vals.items(): worst.append((d["accuracy"],ax,val,d["n"]))
 print("WORST AXES")
 for row in sorted(worst)[:30]:print(row)
 print("TARGET_FAILURE_SAMPLES")
 for reason in ("goal_loss","missing_required","task_loss","length_loss","count_loss","format_loss","qualifier_loss","stale_qualifier","stale_context"):
  print(reason.upper())
  print(json.dumps(reason_samples.get(reason,[])[:20],ensure_ascii=False,indent=2))
if __name__=="__main__":main()
