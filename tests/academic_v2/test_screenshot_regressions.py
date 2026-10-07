"""Production screenshot requests must keep task and source scope distinct."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import study_retrieval_v2 as retrieval
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task


PRESET = ('Bu ders notlarından 20 zorlayıcı çoktan seçmeli soru hazırla. '
          'Cevap anahtarını şimdilik gösterme; cevaplarımı değerlendirmek için bekle.')
HISTORY = [{'role': 'USER', 'content': 'Bu ders notlarını sınav odaklı özetle'},
           {'role': 'ASSISTANT', 'content': '1. İSKELETSEL VE DİŞSEL ÖLÇÜMLER\nDowns analizi...'}]


class ScreenshotRegressions(unittest.TestCase):
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
