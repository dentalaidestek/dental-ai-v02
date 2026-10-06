"""Course source arguments must not become lexical topics or history references."""
import re
import unittest
from pathlib import Path

from app.academic_task_language import course_source_request
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task


class CourseSourceScopeTests(unittest.TestCase):
    def test_presets_and_natural_source_requests(self):
        template = Path('app/templates/notes_ai.html').read_text()
        requests = re.findall('data-prompt="([^"]+)"', template) + [
            'Bu ders notlarını özetler misin?',
            'Ders notlarını bana öğret',
            'Bu ders notlarını basit bir dille anlat',
            'Notlardan soru hazırla',
            'Notlarımı özetle',
            'Bu dersin tamamını özetle',
        ]
        for query in requests:
            with self.subTest(query=query):
                self.assertTrue(course_source_request(query))
                requirement = build_dental_requirement_plan(query)
                self.assertFalse(requirement.subject_terms)
                self.assertFalse(requirement.subject_node_ids)
                self.assertIsNotNone(classify_academic_study_task(query))

    def test_explicit_topics_and_history_references_are_not_course_scope(self):
        for query in [
            'Bu ders notlarındaki trismus konusunu anlat',
            'Bu ders notlarındaki SNA değerini açıkla',
            'Bu ders notlarındaki bilinmeyen terimi anlat',
            'Bu konuyu özetle',
            'Bunu bana öğret',
            'SNA konusunu bu ders notlarından özetle',
            'Bu ders notlarını özetleme.',
            '"Bu ders notlarını özetle" ifadesi ne demek?',
        ]:
            with self.subTest(query=query):
                self.assertFalse(course_source_request(query))

    def test_current_course_scope_survives_old_topic(self):
        from app.study_retrieval_v2 import resolve_followup_query
        query = 'Bu ders notlarını sınav odaklı özetle'
        self.assertEqual(query, resolve_followup_query(
            query, [{'role': 'USER', 'content': 'SNA kaç derece?'}]))


if __name__ == '__main__':
    unittest.main()
