"""Run the 50k deterministic multi-turn continuity benchmark."""
from __future__ import annotations
import argparse,json,time,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
from app.study_retrieval_v2 import resolve_followup_query
from tests.academic_v2.multiturn_50k_generator import generate, validate_cases

def n(s):
 s=unicodedata.normalize("NFKD",str(s or "")).casefold()
 return "".join(ch for ch in s if not unicodedata.combining(ch))

def score(case):
 hist=[{"role":r,"content":c} for r,c in case.history]
 try: out=resolve_followup_query(case.query,hist)
 except Exception as e:return False,"exception",repr(e),""
 z=n(out)
 exp=case.expected
 if exp.get("should_abstain"):
  leaked=[x for x in exp.get("forbidden_topics",()) if n(x) in z and n(x) not in n(case.query)]
  if leaked:return False,"resolved_but_should_abstain"," | ".join(leaked),out
  return True,"ok","",""
 miss=[x for x in case.must if n(x) not in z]
 stale=[x for x in case.must_not if n(x) in z]
 if miss:return False,"missing_required"," | ".join(miss),out
 if stale:return False,"stale_context"," | ".join(stale),out
 if exp.get("task")=="generate_questions" and not any(x in z for x in ("soru","test")):return False,"task_loss","generate_questions",out
 if exp.get("goal")=="exam" and "sinav" not in z:return False,"goal_loss","exam",out
 if exp.get("count") and str(exp["count"]) not in z:return False,"count_loss",str(exp["count"]),out
 if exp.get("format")=="table" and not any(x in z for x in ("tablo","table")):return False,"format_loss","table",out
 if exp.get("format") is None and "tablo" in z and "tablo" not in n(case.query):return False,"stale_format","table",out
 for x in exp.get("qualifiers",()):
  if n(x) not in z:return False,"qualifier_loss",x,out
 for x in exp.get("forbidden_qualifiers",()):
  if n(x) in z:return False,"stale_qualifier",x,out
 if exp.get("length")=="shorter" and not any(x in z for x in ("kisa","oz")):return False,"length_loss","shorter",out
 if exp.get("length")=="detailed" and not any(x in z for x in ("detay","ayrinti","kapsam")):return False,"length_loss","detailed",out
 return True,"ok","",out

def main():
 p=argparse.ArgumentParser();p.add_argument("--count",type=int,default=50000);p.add_argument("--seed",type=int,default=20261004);p.add_argument("--report",default="artifacts/multiturn_50k_report.json");a=p.parse_args()
 cases=generate(a.count,a.seed); quality=validate_cases(cases); reasons=Counter(); axes=defaultdict(lambda:defaultdict(lambda:[0,0])); samples=[]; t=time.perf_counter()
 for c in cases:
  ok,reason,detail,out=score(c); reasons[reason]+=1
  for axis,val in c.axes.items():
   axes[axis][str(val)][0]+=1;axes[axis][str(val)][1]+=int(ok)
  if not ok and len(samples)<500:samples.append({"id":c.case_id,"axes":c.axes,"query":c.query,"history":c.history,"expected":c.expected,"must":c.must,"must_not":c.must_not,"reason":reason,"detail":detail,"resolved":out})
 elapsed=time.perf_counter()-t
 axis_report={ax:{v:{"n":q[0],"passed":q[1],"accuracy":q[1]/q[0]} for v,q in vals.items()} for ax,vals in axes.items()}
 report={"count":len(cases),"seed":a.seed,"quality":quality,"passed":reasons["ok"],"accuracy":reasons["ok"]/len(cases),"elapsed_s":elapsed,"cases_per_s":len(cases)/max(elapsed,.001),"failure_reasons":dict(reasons),"axes":axis_report,"failure_samples":samples}
 path=Path(a.report);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in report.items() if k not in {"failure_samples","axes"}},ensure_ascii=False,indent=2))
 worst=[]
 for ax,vals in axis_report.items():
  for val,d in vals.items(): worst.append((d["accuracy"],ax,val,d["n"]))
 print("WORST AXES")
 for row in sorted(worst)[:30]:print(row)
if __name__=="__main__":main()
