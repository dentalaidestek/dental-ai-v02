"""Exercise actual UI prompts through shared course routing and output contracts."""
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import study_retrieval_v2 as retrieval
from app.academic_study_contract import study_output_rules
from app.academic_task_language import wants_deeper_evidence
from app.dental_query_intent import classify_academic_study_task, build_dental_requirement_plan, classify_dental_study_plan


class PromptReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.prompts = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'button' and 'data-prompt' in values:
            self.prompts.append(values['data-prompt'])


def prompts():
    reader = PromptReader()
    reader.feed(Path('app/templates/notes_ai.html').read_text())
    return reader.prompts


class QuickStudyPromptTests(unittest.TestCase):
    def test_output_manner_is_not_a_source_figure_and_real_figures_stay_visual(self):
        for query in (prompts()[0], 'Pulpitis basit şekilde anlat', 'Notları aynı şekilde özetle'):
            self.assertFalse(build_dental_requirement_plan(query).requires_visual_source, query)
        for query in ('Şekildeki mandibula kırığını açıkla', 'Bu şekil neyi gösteriyor?',
                      'Bu tablodaki bulguları açıkla'):
            self.assertTrue(build_dental_requirement_plan(query).requires_visual_source, query)

    def test_count_survives_shared_difficulty_and_format_modifiers(self):
        for query in (prompts()[2], 'Notlardan 20 zorlayıcı klinik soru hazırla',
                      'Notlardan 10 zorlayici soru oluştur'):
            plan = classify_dental_study_plan(query)
            self.assertIsNotNone(plan)
            self.assertEqual(plan.count, 10 if '10 ' in query else 20)

    def test_actual_three_buttons_have_distinct_shared_tasks(self):
        requests = prompts()
        self.assertEqual(len(requests), 3)
        self.assertEqual([classify_academic_study_task(q).task for q in requests],
                         ['summarize', 'explain', 'generate_questions'])
        self.assertTrue(wants_deeper_evidence(requests[1]))

    def test_18_button_material_history_combinations_hydrate_owned_note_scope(self):
        histories = [[], [{'role': 'USER', 'content': 'Pulpitis anlat'}],
            [{'role': 'USER', 'content': 'SNB nedir?'},
             {'role': 'ASSISTANT', 'content': 'Soru 1\nSNB kaçtır?\n<!--ACADEMIC_Q_CURSOR:5:14001-->'}]]
        session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        for material_count in (1, 6):
            buckets = tuple(SimpleNamespace(question_budget=1, chunk_ids=(i,), material_id=i)
                            for i in range(1, material_count + 1))
            plan = SimpleNamespace(buckets=buckets, scanned_rows=material_count)
            rows = [(i, i, f'Not {i}', i, i, f'Başlık {i}', 'TEXT', 'Kaynak açıklaması',
                     None, None, None, None, 1.0, i, '{}') for i in range(1, material_count + 1)]
            for history in histories:
                for query in prompts():
                    with self.subTest(materials=material_count, history=history, query=query), \
                         patch.object(retrieval, 'get_or_build_coverage_plan', return_value=plan), \
                         patch.object(retrieval, '_coverage_evidence_rows', return_value=rows) as hydrate, \
                         patch.object(retrieval, '_question_rows', side_effect=AssertionError('wrong source-solving route')):
                        result = retrieval.retrieve_course_context_v2(session,
                            owner_user_id=7, course_id=3, query=query, recent_history=history)
                        self.assertEqual(result.retrieval_mode, 'coverage')
                        self.assertTrue(result.evidence_sufficient)
                        self.assertEqual(result.resolved_query, query)
                        self.assertEqual(result.source_material_ids, list(range(1, material_count + 1)))
                        self.assertEqual(hydrate.call_args.kwargs['owner_user_id'], 7)
                        self.assertEqual(hydrate.call_args.kwargs['course_id'], 3)

    def test_shared_output_contracts_include_source_headings_and_question_count(self):
        headings = ['Downs analizi', 'Splintler']
        summary, teach, quiz = [study_output_rules(q, headings) for q in prompts()]
        self.assertIn('ana başlıklarını listele', summary)
        self.assertIn('neden-sonuç', teach)
        self.assertIn('toplam sayı 20', quiz)
        self.assertIn('kaynak sorularını', quiz)
        self.assertIn('Cevap anahtarını', quiz)
        for rules in (summary, teach, quiz):
            self.assertIn('Downs analizi, Splintler', rules)
            self.assertIn('Görülmeyen başlıkların', rules)

    def test_natural_equivalents_use_the_same_contract_not_button_equality(self):
        for query, expected in [('Notlarımı özetler misin?', 'Özet:'),
                                ('Ders notlarını ayrıntılı anlat', 'Öğretme:'),
                                ('Notlardan 20 soru oluştur', 'toplam sayı 20')]:
            self.assertIn(expected, study_output_rules(query, ['Kaynak başlığı']))


if __name__ == '__main__':
    unittest.main()
