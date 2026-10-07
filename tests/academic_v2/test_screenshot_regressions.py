"""Production screenshot requests must keep task and source scope distinct."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import study_retrieval_v2 as retrieval
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task
from app.academic_task_language import study_priority_request
from app.academic_study_contract import study_output_rules


PRESET = ('Bu ders notlarından 20 zorlayıcı çoktan seçmeli soru hazırla. '
          'Cevap anahtarını şimdilik gösterme; cevaplarımı değerlendirmek için bekle.')
HISTORY = [{'role': 'USER', 'content': 'Bu ders notlarını sınav odaklı özetle'},
           {'role': 'ASSISTANT', 'content': '1. İSKELETSEL VE DİŞSEL ÖLÇÜMLER\nDowns analizi...'}]


class ScreenshotRegressions(unittest.TestCase):
    def test_exam_selection_is_a_task_with_owned_course_or_topic(self):
        for who in ('Hoca', 'Hocamız', 'Öğretmen', ''):
            for where in ('nerden', 'nereden', 'ne', 'neler', 'hangi konulardan'):
                query = f'{who} {where} sorabilir'.strip()
                self.assertEqual(study_priority_request(query), 'exam_points', query)
                for history, course_scope in ((HISTORY, True),
                        ([{'role': 'USER', 'content': 'Pulpitis anlat'}], False)):
                    resolved = retrieval.resolve_followup_query(query, history)
                    requirement = build_dental_requirement_plan(resolved)
                    task = classify_academic_study_task(resolved)
                    self.assertEqual(task.task, 'exam_points')
                    self.assertEqual(retrieval._course_coverage_requested(resolved, requirement, task), course_scope)
                    if not course_scope:
                        self.assertIn('pulpitis', requirement.subject_terms)
                    self.assertFalse(requirement.requires_visual_source)

    def test_selection_rejection_requests_real_source_emphasis(self):
        for query in ('Bence burdan gelmez hocanın özellikle vurguladığı işaretli yerler var mı',
                      'Hocanın altını çizdiği yerler nerede',
                      'Notlarda altı çizili yerler var mı',
                      'Slaytlarda işaretlenmiş kısımlar hangileri',
                      'Öğretmenin üzerinde durduğu noktaları göster'):
            self.assertEqual(study_priority_request(query), 'source_emphasis', query)
            resolved = retrieval.resolve_followup_query(query, HISTORY)
            plan = build_dental_requirement_plan(resolved)
            self.assertFalse(plan.subject_terms)
            self.assertTrue(plan.requires_visual_source)
            self.assertTrue(retrieval._course_coverage_requested(resolved, plan, classify_academic_study_task(resolved)))

    def test_source_emphasis_is_not_a_claim_about_exam_predictions(self):
        exam = study_output_rules('Hoca nerden sorabilir', ['Downs analizi'])
        marked = study_output_rules('Bu ders notlarını açıkla — Notlarda altı çizili yerler var mı', ['Downs analizi'])
        self.assertIn('çalışma önerisi', exam)
        self.assertIn('tüm dosyada yok deme', marked)
        self.assertIn('gerçekten görülüyorsa', marked)

    def test_priority_grammar_does_not_erase_unknown_or_named_subjects(self):
        for query in ('Pulpitis nereden sorulabilir', 'Nance apareyinde işaretli yerler var mı',
                      'Zorbital sendromunda hoca ne sorabilir', 'Hocanın işaretlediği pulpitis ne demek'):
            self.assertIsNone(study_priority_request(query), query)
            self.assertTrue(build_dental_requirement_plan(query).subject_terms, query)
            self.assertEqual(retrieval.resolve_followup_query(query, HISTORY), query)

    def test_outline_feedback_continues_course_scope(self):
        for query in ('Bu çok yüzeysel her başlığı açıkla', 'Diğer başlıklar nerede',
                      'Eksik kalan başlıkları anlat', 'Bu yetersiz bütün konuları detaylandır'):
            with self.subTest(query=query):
                resolved = retrieval.resolve_followup_query(query, HISTORY)
                requirement = build_dental_requirement_plan(resolved)
                self.assertFalse(requirement.subject_terms)
                self.assertTrue(retrieval._course_coverage_requested(resolved, requirement, classify_academic_study_task(resolved)))

    def test_generation_does_not_become_source_question_solving(self):
        for query in (PRESET, 'Bütün notlardan soru hazırla, cevaplarımı bekle',
                      'Tüm konulardan test üret', '20 soru oluştur; sonra cevaplarımı değerlendir'):
            self.assertFalse(retrieval._is_exhaustive_question_request(query), query)
        for query in ('Soruları çöz', 'Soruları cevapla', 'Dosyadaki tüm soruları çöz'):
            self.assertTrue(retrieval._is_exhaustive_question_request(query), query)
        self.assertFalse(retrieval._is_exhaustive_question_request('Sorulara cevaplarımı daha sonra göndereceğim'))

    def test_preset_hydrates_note_coverage_not_source_question_pages(self):
        session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        bucket = SimpleNamespace(question_budget=20, chunk_ids=(42,), material_id=5)
        plan = SimpleNamespace(buckets=(bucket,), scanned_rows=1)
        row = (42, 5, 'Orto', 2, 2, 'Downs analizi', 'TEXT', 'Downs analizi açıklaması',
               None, None, None, None, 1.0, 2, '{}')
        with patch.object(retrieval, 'get_or_build_coverage_plan', return_value=plan), \
             patch.object(retrieval, '_coverage_evidence_rows', return_value=[row]) as hydrate, \
             patch.object(retrieval, '_question_rows', side_effect=AssertionError('wrong source-question route')):
            result = retrieval.retrieve_course_context_v2(session, owner_user_id=7, course_id=3,
                query=PRESET, recent_history=HISTORY)
        self.assertEqual(result.retrieval_mode, 'coverage')
        self.assertTrue(result.evidence_sufficient)
        self.assertEqual(result.source_material_ids, [5])
        self.assertEqual(hydrate.call_args.kwargs['owner_user_id'], 7)
        self.assertEqual(hydrate.call_args.kwargs['course_id'], 3)

    def test_old_cursor_cannot_override_a_new_task(self):
        history = [{'role': 'ASSISTANT', 'content': 'Sorular...\n<!--ACADEMIC_Q_CURSOR:5:14001-->'}]
        self.assertEqual(retrieval._continuation_cursor('devam et', history), (5, 14001))
        self.assertIsNone(retrieval._continuation_cursor('devam, yeni 20 soru hazırla', history))
        self.assertIsNone(retrieval._continuation_cursor('devam, notları özetle', history))

    def test_named_clinical_topics_are_not_erased_by_outline_controls(self):
        for query in ('Pulpitis başlığını açıkla', 'Diğer başlıkta geçen Nance apareyini anlat'):
            self.assertEqual(retrieval.resolve_followup_query(query, HISTORY), query)
            self.assertTrue(build_dental_requirement_plan(query).subject_terms)


if __name__ == '__main__':
    unittest.main()
