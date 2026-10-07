"""Natural omitted-subject commands across topics, scope and topic switches."""
import unittest
from types import SimpleNamespace

from app.academic_task_language import elliptical_study_request, course_source_request
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task
from app.study_retrieval_v2 import resolve_followup_query, retrieve_course_context_v2, _course_coverage_requested


TOPICS = ('Çocuklarda flor kullanımını', 'Pulpitis tedavisini', 'Nance apareyinin kullanımını',
          'Mandibula kondil kırıklarını', 'İmplant stabilitesini', 'Akut apikal periodontitisi',
          'Lokal anesteziyi', 'Süt dişlerinde çürüğü')
FOLLOWUPS = ('Bir örnek versene', 'Örnek verir misin?', 'Nasıl uygulanıyor?',
             'Nasıl yapılır?', 'Dozu da söyle', 'Neden böyle oluyor?',
             'Kafam karıştı biraz daha sade anlat', 'Bir tane daha sor')


class ConversationalEllipsisTests(unittest.TestCase):
    def test_study_artifact_transformation_preserves_source_or_named_topic(self):
        history = [{'role': 'USER', 'content': 'Pulpitis anlat'}]
        for query in ('Notları çalışabileceğim hale getir', 'Slaytları çalışılabilir bir hale dönüştür'):
            self.assertTrue(course_source_request(query))
            self.assertEqual(resolve_followup_query(query, history), query)
            self.assertFalse(build_dental_requirement_plan(query).subject_terms)
        query = 'Notlardaki Nance apareyini çalışabileceğim hale getir'
        self.assertFalse(course_source_request(query))
        self.assertIn('Nance', ' '.join(build_dental_requirement_plan(query).subject_terms))

    def test_facet_followups_do_not_get_graded_as_free_text_quiz_answers(self):
        from app.academic_dialogue import active_question_reference
        history = [{'role': 'USER', 'content': 'Çocuklarda flor hakkında bir soru sor'},
                   {'role': 'ASSISTANT', 'content': 'Soru 1\nFlor ne için kullanılır?\nA) Çürük önleme\nB) Anestezi'}]
        self.assertIsNotNone(active_question_reference('Çürüğü önlemek için', history))
        for query in FOLLOWUPS:
            self.assertIsNone(active_question_reference(query, history), query)

    def test_64_topic_and_language_pairs_preserve_user_topic(self):
        for topic in TOPICS:
            history = [{'role': 'USER', 'content': topic + ' anlat'},
                       {'role': 'ASSISTANT', 'content': 'Periodontitis ilgisiz bir örnektir.'}]
            for query in FOLLOWUPS:
                with self.subTest(topic=topic, query=query):
                    resolved = resolve_followup_query(query, history)
                    self.assertIn(topic, resolved)
                    self.assertIn(query, resolved)
                    subjects = ' '.join(build_dental_requirement_plan(resolved).subject_terms)
                    self.assertNotIn('versene', subjects)
                    self.assertNotIn('hazırla', subjects)

    def test_unbound_reference_asks_without_db_candidate_query(self):
        session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        for query in FOLLOWUPS[:-1]:
            with self.subTest(query=query):
                result = retrieve_course_context_v2(session, owner_user_id=1, course_id=3, query=query)
                self.assertTrue(result.clarification)
                self.assertEqual(result.evidence, [])

    def test_request_contains_a_real_subject_does_not_inherit_old_topic(self):
        history = [{'role': 'USER', 'content': 'Çocuklarda flor kullanımını anlat'}]
        for query in ('Pulpitis dozu nedir?', 'İmplant nasıl uygulanıyor?',
                      'Nance apareyinin kullanımını örnekle anlat', 'Şimdi Nance apareyine geçelim'):
            self.assertIsNone(elliptical_study_request(query))
            self.assertEqual(resolve_followup_query(query, history), query)
        history += [{'role': 'USER', 'content': 'Şimdi Nance apareyine geçelim'}]
        resolved = resolve_followup_query('Bir örnek versene', history)
        self.assertIn('Nance', resolved)
        self.assertNotIn('flor', resolved)

    def test_repair_chain_keeps_topic_and_current_facet(self):
        history = [{'role': 'USER', 'content': 'Çocuklarda flor kullanımını anlat'}]
        for query, intent in [('Nasıl uygulanıyor?', 'treatment'), ('Dozu da söyle', 'value'),
                              ('Neden böyle oluyor?', 'cause')]:
            resolved = resolve_followup_query(query, history)
            self.assertIn('Çocuklarda flor', resolved)
            self.assertIn(intent, [item.name for item in build_dental_requirement_plan(resolved).intents])
            history += [{'role': 'USER', 'content': query}, {'role': 'ASSISTANT', 'content': '...'}]

    def test_course_exam_preparation_overrides_stale_named_topic(self):
        history = [{'role': 'USER', 'content': 'Pulpitis anlat'}]
        for query in ('Bu notlardan beni sınava hazırla', 'Ders notlarından beni finale hazırla'):
            with self.subTest(query=query):
                self.assertTrue(course_source_request(query))
                resolved = resolve_followup_query(query, history)
                self.assertEqual(resolved, query)
                requirement = build_dental_requirement_plan(resolved)
                self.assertTrue(_course_coverage_requested(resolved, requirement, classify_academic_study_task(resolved)))


if __name__ == '__main__':
    unittest.main()
