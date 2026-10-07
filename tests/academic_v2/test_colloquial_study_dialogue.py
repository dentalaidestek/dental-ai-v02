"""Behavioral regression checks for format, frustration and real quiz transitions."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from app.academic_request_slots import output_slots, conversational_repair, REPAIR_RESPONSE
from app.academic_dialogue import active_question_reference, answer_needs_reference
from app.academic_study_contract import study_output_rules
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task
from app import study_retrieval_v2 as r

COURSE=[{'role':'USER','content':'Bu ders notlarını özetle'},
        {'role':'ASSISTANT','content':'1. Downs analizi\n2. Nance apareyi'}]
TOPIC=[{'role':'USER','content':'Çocuklarda flor kullanımını anlat'}]
QUIZ=[{'role':'USER','content':'Çocuklarda flor kullanımından bir soru sor'},
      {'role':'ASSISTANT','content':'Soru 1\nFlor ne için kullanılır?\nA) Çürük önleme\nB) Anestezi'}]
CASES=json.loads((Path(__file__).parent/'colloquial_study_cases.json').read_text())

class ColloquialStudyDialogueTests(unittest.TestCase):
    def test_comparison_does_not_invent_an_unmentioned_second_concept(self):
        session=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        for history in (TOPIC,QUIZ):
            result=r.retrieve_course_context_v2(session,owner_user_id=1,course_id=3,
                query='ikisinin farkı ne',recent_history=history)
            self.assertEqual(result.retrieval_mode,'clarification')
            self.assertIn('Hangi iki kavramı',result.clarification)
        self.assertFalse(r._missing_comparison_reference('ikisinin farkı ne',COURSE))
        self.assertFalse(r._missing_comparison_reference('Flor ve pulpitis arasındaki fark ne',TOPIC))

    def test_format_scope_and_action_compositions_survive_resolution(self):
        scopes=('Her başlığı','Bütün konuları','Kalan başlıkları','Diğer konuları')
        manners=('tek bir paragrafla','madde madde','3 cümleyle','ayrı ayrı','tablo halinde')
        verbs=('anlat','açıkla','göster','yaz')
        for scope in scopes:
            for manner in manners:
                for verb in verbs:
                    query=f'{scope} {manner} {verb}'
                    for history in (COURSE,TOPIC,QUIZ):
                        resolved=r.resolve_followup_query(query,history)
                        self.assertEqual(classify_academic_study_task(resolved).task,'explain',query)
                        self.assertIsNone(active_question_reference(query,history),query)
                        if history is COURSE:
                            p=build_dental_requirement_plan(resolved)
                            self.assertFalse(p.subject_terms)
                            self.assertTrue(r._course_coverage_requested(resolved,p,classify_academic_study_task(resolved)))
                        else:self.assertIn('flor',resolved.casefold(),query)

    def test_actual_screenshot_typo_preserves_requested_paragraph_format(self):
        query='Her başlığı tek bir oaragrafla anlat'
        resolved=r.resolve_followup_query(query,COURSE)
        self.assertIn(query,resolved)
        self.assertIn('her başlık için ayrı tek paragraf',study_output_rules(resolved,['Downs','Nance']))
        self.assertFalse(build_dental_requirement_plan(resolved).subject_terms)

    def test_frustration_never_queries_candidates_or_grades_a_quiz(self):
        session=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        for case in CASES:
            if case['category']!='feedback':continue
            query=case['query']
            self.assertTrue(conversational_repair(query),query)
            self.assertIsNone(active_question_reference(query,QUIZ),query)
            self.assertFalse(answer_needs_reference(query,QUIZ),query)
            result=r.retrieve_course_context_v2(session,owner_user_id=1,course_id=3,query=query,recent_history=QUIZ)
            self.assertEqual(result.clarification,REPAIR_RESPONSE)
            self.assertEqual(result.evidence,[])

    def test_frustration_preserves_real_pending_quiz_and_active_topic(self):
        history=QUIZ+[{'role':'USER','content':'Kral sen dalga mı geçiyorsun'},
                      {'role':'ASSISTANT','content':REPAIR_RESPONSE}]
        self.assertIsNotNone(active_question_reference('A',history))
        resolved=r.resolve_followup_query('Her başlığı tek bir paragrafla anlat',history)
        self.assertIn('flor',resolved.casefold())
        self.assertNotIn('dalga',resolved)

    def test_complaint_plus_new_format_request_runs_the_task(self):
        query='Sen dalga mı geçiyorsun? Her başlığı madde madde anlat'
        self.assertFalse(conversational_repair(query))
        resolved=r.resolve_followup_query(query,TOPIC)
        self.assertIn('flor',resolved.casefold())
        self.assertEqual(classify_academic_study_task(resolved).task,'explain')
        self.assertIn('madde madde',study_output_rules(resolved,[]))
        query='Başlıkları atlama, her başlığı tek bir paragrafla anlat'
        resolved=r.resolve_followup_query(query,TOPIC)
        self.assertIn('flor',resolved.casefold())
        self.assertIn('tek paragraf',study_output_rules(resolved,[]))

    def test_new_quiz_with_wait_is_not_an_answer_to_previous_question(self):
        for query in ('bi soru sor cevabımı bekle','Bana zor bi soru sor',
                      'Cevapları söyleme 5 soru hazırla'):
            self.assertIsNone(active_question_reference(query,QUIZ),query)
            resolved=r.resolve_followup_query(query,QUIZ)
            self.assertIn('flor',resolved.casefold(),query)
            self.assertTrue(classify_academic_study_task(resolved).generate_new_questions)
        self.assertIsNotNone(active_question_reference('Çürüğü önlemek için',QUIZ))

    def test_new_named_topic_is_not_graded_and_output_nouns_are_not_fuzzed(self):
        for query in ('Şimdi implant stabilitesine geçelim','Zorbital sendromunu anlat',
                      'İkinci molar nedir','Apikal periodontitiste kalan başlıkları açıkla',
                      'Paragrafla sendromunu anlat'):
            self.assertIsNone(output_slots(query),query)
            self.assertIsNone(active_question_reference(query,QUIZ),query)
            resolved=r.resolve_followup_query(query,QUIZ)
            self.assertNotIn('Flor ne',resolved)
            self.assertNotIn('Çocuklarda flor',resolved)
            self.assertTrue(build_dental_requirement_plan(resolved).subject_terms)

    def test_source_based_request_overrides_previous_topic_with_natural_output_words(self):
        for case in CASES:
            if case['category']!='course':continue
            query=case['query'];resolved=r.resolve_followup_query(query,TOPIC)
            p=build_dental_requirement_plan(resolved)
            self.assertFalse(p.subject_terms,query)
            self.assertTrue(r._course_coverage_requested(resolved,p,classify_academic_study_task(resolved)),query)

if __name__=='__main__':unittest.main()
