"""Compositional Turkish requests: independently vary grammar, not full strings."""
from itertools import product
import unittest

from app.academic_task_language import course_source_request, wants_deeper_evidence
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task, classify_dental_study_plan
from app.study_retrieval_v2 import resolve_followup_query, _course_coverage_requested


PREFIXES = ('', 'Acaba ', 'Rica etsem ', 'Hocam, ')
SOURCES = ('Bu ders notlarını', 'Slaytları', 'Materyalleri', 'Dosyaları')
SCOPES = ('', 'baştan sona ', 'tüm konuları ')
OPERATIONS = (('özetle', 'summarize', None), ('özetler misin?', 'summarize', None),
              ('ayrıntılı öğret', 'explain', None), ('bir hoca gibi öğret', 'explain', None),
              ('20 zorlayıcı soru hazırla', 'generate_questions', 20),
              ('yirmi üç soru hazırlar mısın?', 'generate_questions', 23))


class TurkishRequestCompositionTests(unittest.TestCase):
    def test_case_and_ascii_variants_preserve_semantic_slots(self):
        fold = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
        for source, (operation, task, count) in product(SOURCES, OPERATIONS):
            original = f'Acaba {source} {operation}'
            for query in (original.upper(), original.translate(fold).lower()):
                with self.subTest(query=query):
                    self.assertTrue(course_source_request(query))
                    self.assertEqual(classify_academic_study_task(query).task, task)
                    if count is not None:
                        self.assertEqual(classify_dental_study_plan(query).count, count)

    def test_288_independent_source_scope_style_operation_combinations(self):
        history = [{'role': 'USER', 'content': 'Çocuklarda flor kullanımını anlat'}]
        checked = 0
        for prefix, source, scope, (operation, task, count) in product(PREFIXES, SOURCES, SCOPES, OPERATIONS):
            query = f'{prefix}{source} {scope}{operation}'
            with self.subTest(query=query):
                self.assertTrue(course_source_request(query))
                resolved = resolve_followup_query(query, history)
                self.assertNotIn('flor', resolved.casefold())
                self.assertTrue(course_source_request(resolved))
                requirement = build_dental_requirement_plan(resolved)
                self.assertFalse(requirement.subject_terms)
                self.assertFalse(requirement.requires_visual_source)
                self.assertEqual(classify_academic_study_task(query).task, task)
                self.assertTrue(_course_coverage_requested(query, requirement, classify_academic_study_task(query)))
                if count is not None:
                    self.assertEqual(classify_dental_study_plan(query).count, count)
            checked += 1
        self.assertEqual(checked, 288)

    def test_feedback_and_outline_clauses_compose_without_new_medical_topics(self):
        history = [{'role': 'USER', 'content': 'Bu ders notlarını özetle'}]
        for feedback, subject, manner, verb in product(
                ('Yanıtın eksik. ', 'Bu anlattığın çok yüzeysel; ', ''),
                ('Her başlığı', 'Kalan konuları', 'Diğer başlıkları'),
                ('', 'tek tek ', 'ayrı ayrı '),
                ('anlat', 'açıklar mısın?')):
            query = f'{feedback}{subject} {manner}{verb}'
            with self.subTest(query=query):
                self.assertTrue(wants_deeper_evidence(query))
                resolved = resolve_followup_query(query, history)
                requirement = build_dental_requirement_plan(resolved)
                self.assertFalse(requirement.subject_terms)
                self.assertTrue(_course_coverage_requested(resolved, requirement, classify_academic_study_task(resolved)))

    def test_unknown_and_known_named_topics_survive_polite_source_adjuncts(self):
        history = [{'role': 'USER', 'content': 'Çocuklarda flor kullanımını anlat'}]
        for prefix, topic in product(PREFIXES, ('Nance apareyini', 'Pulpitis tedavisini', 'Mandibula kondil kırıklarını')):
            query = prefix + 'notlardaki ' + topic + ' anlatır mısın?'
            with self.subTest(query=query):
                self.assertFalse(course_source_request(query))
                self.assertNotIn('flor', resolve_followup_query(query, history).casefold())
                self.assertTrue(build_dental_requirement_plan(query).subject_terms)

    def test_written_compound_question_count_survives_followup(self):
        history = [{'role': 'USER', 'content': 'Notlardan yirmi üç zorlayıcı soru hazırlar mısın?'},
                   {'role': 'ASSISTANT', 'content': 'Sorular...'}]
        resolved = resolve_followup_query('Aynı sayıda soru hazırla', history)
        self.assertIn('23 soru', resolved)
        self.assertEqual(classify_dental_study_plan(resolved).count, 23)
        self.assertIsNone(classify_dental_study_plan('Yirmi üç dişin anatomisini anlat'))


if __name__ == '__main__':
    unittest.main()
