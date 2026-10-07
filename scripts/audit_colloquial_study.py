"""Reproducible audit of frozen colloquial requests across three histories.

Corpus is authored, not taken from ChatGPT private conversations or a public dataset.
Pass criteria measure routing only; generation correctness is not measured.
"""
import argparse, json, runpy, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
parser=argparse.ArgumentParser(description='Audit hand-authored colloquial study intent and context; no provider/browser validation.')
parser.add_argument('--language-only',action='store_true',help='Use AST harness without database/storage imports.')
parser.add_argument('--report',default='artifacts/colloquial-study-after.json')
args=parser.parse_args()
if args.language_only:runpy.run_path(str(root/'tests/academic_v2/language_probe.py'))
from app import study_retrieval_v2 as r
from app.dental_query_intent import build_dental_requirement_plan as bp,classify_academic_study_task as ct
from app.academic_dialogue import active_question_reference
try:
 from app.academic_request_slots import conversational_repair
except ImportError:
 conversational_repair=lambda x:False
cases=json.loads((root/'tests/academic_v2/colloquial_study_cases.json').read_text())
histories={'course':[{'role':'USER','content':'Bu ders notlarını özetle'},{'role':'ASSISTANT','content':'1. Downs analizi\n2. Nance apareyi'}],'topic':[{'role':'USER','content':'Çocuklarda flor kullanımını anlat'},{'role':'ASSISTANT','content':'Flor açıklaması. Pulpitis ayrı bir konudur.'}],'quiz':[{'role':'USER','content':'Çocuklarda flor kullanımından bir soru sor'},{'role':'ASSISTANT','content':'Soru 1\nFlor ne için kullanılır?\nA) Çürük önleme\nB) Anestezi'}]}
rows=[]
for case in cases:
 for name,history in histories.items():
  q=case['query']; resolved=r.resolve_followup_query(q,history);p=bp(resolved);task=ct(resolved);scope=r._course_coverage_requested(resolved,p,task)
  category=case['category'];ok=False
  if category=='named':ok=resolved==q and bool(p.subject_terms or p.subject_node_ids)
  elif category=='feedback':ok=bool(conversational_repair(q)) and active_question_reference(q,history) is None
  elif category=='course':ok=scope and not p.subject_terms and not p.subject_node_ids
  else:ok=bool(task) and (scope if name=='course' else 'flor' in resolved.lower()) and active_question_reference(q,history) is None
  if category=='quiz':ok=ok and bool(task and task.generate_new_questions)
  if case.get('expected_behavior') and name in {'topic','quiz'}:
   from types import SimpleNamespace
   session=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
   result=r.retrieve_course_context_v2(session,owner_user_id=1,course_id=3,query=q,recent_history=history)
   ok=result.retrieval_mode=='clarification' and 'Hangi iki kavramı' in (result.clarification or '')
  rows.append({**case,'history':name,'resolved':resolved,'subjects':p.subject_terms,'task':task.task if task else None,'course_scope':scope,'passed':ok})
report={'total':len(rows),'passed':sum(x['passed'] for x in rows),'failed':sum(not x['passed'] for x in rows),'gold_note':'The ambiguous comparison case explicitly expects clarification with only one referent. Earlier exploratory report used overly strict task/scope gold and is not a directly comparable score.', 'limits':'Hand-authored intent/context audit; no SQL, provider generation or authenticated production browser. Quiz requests anchored to actual pending question may legitimately preserve the selected question stem.','cases':rows}
out=args.report;(root/out).write_text(json.dumps(report,ensure_ascii=False,indent=2));print({k:v for k,v in report.items() if k!='cases'});print('Failed unique prompts:');print('\n'.join(dict.fromkeys(x['query'] for x in rows if not x['passed'])))
