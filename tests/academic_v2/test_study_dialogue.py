"""Behavioral scenarios across source scope, quiz answers, references and switches."""
import unittest

from app.academic_dialogue import active_question_reference, numbered_answer_references, dialogue_rules, answer_needs_reference
from app.dental_query_intent import build_dental_requirement_plan, classify_academic_study_task
from app.study_retrieval_v2 import resolve_followup_query, _retrieval_terms, _course_coverage_requested


def user(text):
    return {'role': 'user', 'content': text}


def assistant(text):
    return {'role': 'assistant', 'content': text}


QUESTION = 'Pulpitis tanısında hangi bulgu beklenir?\nA) Ağrı\nB) Amalgam\nC) İmplant'


class StudyDialogueTests(unittest.TestCase):
    def test_question_headers_and_inflections(self):
        for heading in ('Soru 1', 'Soru 1:', '**Soru 1**', '1.', '1)', '### Soru 1'):
            history = [user('Notlardan soru hazırla'), assistant(heading + '\n' + QUESTION)]
            for query in ('1. soruyu açıkla', '1. sorunun konusunu anlat', 'birincisini açıkla'):
                with self.subTest(heading=heading, query=query):
                    resolved = resolve_followup_query(query, history)
                    self.assertIn('Pulpitis', resolved)
                    self.assertNotIn('Amalgam', resolved)
                    self.assertNotIn('İmplant', resolved)

    def test_latest_question_batch_owns_missing_ordinal(self):
        history = [user('Soru hazırla'), assistant('3. Pulpitis sorusu'),
                   user('Baştan iki soru hazırla'), assistant('Soru 1\nFlor?\nSoru 2\nSNB?')]
        query = '3. soruyu açıkla'
        self.assertEqual(query, resolve_followup_query(query, history))

    def test_short_answers_bind_actual_question(self):
        history = [user('Bana notlardan soru sor'), assistant('Soru 1\n' + QUESTION)]
        for query in ('B', 'bence C', 'Cevabım A', 'Bu soruyu çöz', 'önceki soruyu açıkla'):
            with self.subTest(query=query):
                reference = active_question_reference(query, history)
                self.assertIsNotNone(reference)
                self.assertIn('Pulpitis', resolve_followup_query(query, history))
                self.assertIn('ders kanıtlarıyla değerlendir', dialogue_rules(query, history))

    def test_unnumbered_answer_does_not_guess_a_batch_question(self):
        history = [assistant('Soru 1\n' + QUESTION + '\nSoru 2\nSNB kaçtır?\nA) 80\nB) 82')]
        self.assertIsNone(active_question_reference('B', history))
        self.assertIsNone(active_question_reference('B', []))
        self.assertTrue(answer_needs_reference('B', history))
        self.assertTrue(answer_needs_reference('B', []))
        self.assertFalse(answer_needs_reference('B', [assistant('Soru 1\n' + QUESTION)]))

    def test_numbered_multiple_answers_preserve_each_question(self):
        history = [assistant('Soru 1\n' + QUESTION + '\nSoru 2\nSNB kaçtır?\nA) 80\nB) 82')]
        for query in ('1A, 2B', 'Cevaplarım: 1. A ve 2. B'):
            with self.subTest(query=query):
                references = numbered_answer_references(query, history)
                self.assertEqual([1, 2], [item.number for item in references])
                resolved = resolve_followup_query(query, history)
                self.assertIn('Pulpitis', resolved)
                self.assertIn('SNB', resolved)
        self.assertEqual([], numbered_answer_references('1A, 9C', history))

    def test_course_scope_survives_followups_and_drops_old_topic(self):
        history = [user('Pulpitis anlat'), assistant('...'),
                   user('Bu ders notlarını özetle'), assistant('...')]
        for query in ('Daha basit anlat', '20 soru hazırla', 'Bunu tablo yap'):
            with self.subTest(query=query):
                resolved = resolve_followup_query(query, history)
                self.assertNotIn('Pulpitis', resolved)
                self.assertTrue(_course_coverage_requested(
                    resolved, build_dental_requirement_plan(resolved), classify_academic_study_task(resolved)))
        query = 'Şimdi SNB nedir?'
        self.assertEqual(query, resolve_followup_query(query, history))

    def test_generated_question_answer_then_followup_keeps_selected_topic(self):
        history = [user('Notlardan soru sor'), assistant('Soru 1\n' + QUESTION),
                   user('B'), assistant('Cevabının değerlendirmesi...')]
        resolved = resolve_followup_query('Bunu daha detaylı anlat', history)
        self.assertIn('Pulpitis', resolved)
        self.assertNotIn('Amalgam', resolved)

    def test_interactive_generation_waits_without_dumping_answer_key(self):
        query = '20 soru sor, tek tek gidelim, cevabımı bekle'
        rules = dialogue_rules(query, [])
        self.assertIn('yalnız bir soru sor', rules)
        self.assertIn('henüz açıklama', rules)
        self.assertEqual('', dialogue_rules('SNB nedir?', []))

    def test_followup_controls_do_not_pollute_topic_search(self):
        history = [user('Nance apareyinin kullanımını anlat'), assistant('...')]
        resolved = resolve_followup_query('Bunu daha basit ve tablo şeklinde anlat', history)
        subject = build_dental_requirement_plan(resolved).subject_terms
        self.assertTrue(any('Nance' in term for term in subject))
        self.assertFalse(any('tablo' in term or 'basit' in term for term in subject))
        terms, _ = _retrieval_terms(resolved)
        self.assertNotIn('tablo', terms)
        self.assertNotIn('basit', terms)

    def test_course_sampling_represents_small_materials(self):
        from app.academic_coverage import CoverageAccumulator
        accumulator = CoverageAccumulator()
        rows = [(i, 1, '', 1, 1, 'Büyük bölüm', 'TEXT', None,
                 None, None, None, None, None, None, None) for i in range(1, 301)]
        rows += [(300 + material_id, material_id, '', 1, 1, 'Kısa bölüm', 'TEXT', None,
                  None, None, None, None, None, None, None) for material_id in range(2, 7)]
        accumulator.add_rows(rows)
        plan = accumulator.build(24, ensure_material_coverage=True)
        self.assertEqual(set(range(1, 7)), {bucket.material_id for bucket in plan.buckets})
        self.assertEqual(24, sum(bucket.question_budget for bucket in plan.buckets))

    def test_medical_noun_is_not_a_typoed_correction_prefix(self):
        history = [user('kök yüzeyi düzleştirme anlat'), assistant('...')]
        self.assertIn('kök yüzeyi düzleştirme', resolve_followup_query('aynı konudan devam et', history))
        noisy = [user('alveolit anlat'), assistant('...')]
        self.assertIn('alveolit', resolve_followup_query('yoook aveolit anlat', noisy))

    def test_explicit_explanation_clears_old_format_even_on_same_topic(self):
        history = [user('Pulpitis anlat'), assistant('...'),
                   user('tablo şeklinde anlat'), assistant('...'),
                   user('Pulpitis anlat'), assistant('...')]
        resolved = resolve_followup_query('aynı formatta devam et', history)
        prefix = resolved.split(' — ', 1)[0]
        self.assertNotIn('table', prefix)
        self.assertNotIn('tablo', prefix)

    def test_natural_unknown_topic_and_polite_question_generation(self):
        requirement = build_dental_requirement_plan('Nance ne işe yarar?')
        self.assertEqual(('Nance',), requirement.subject_terms)
        self.assertEqual(['Nance'], _retrieval_terms('Nance ne işe yarar?')[0])
        for query in ('20 soru hazırlar mısın?', 'Bana bir soru sorar mısın?'):
            with self.subTest(query=query):
                self.assertTrue(_course_coverage_requested(
                    query, build_dental_requirement_plan(query), classify_academic_study_task(query)))

    def test_deictic_questions_and_collective_comparisons(self):
        history = [user('Pulpitis anlat'), assistant('...')]
        for query in ('Bu nedir?', 'Bu ne demek?', 'Neden?', 'Nasıl yani?'):
            with self.subTest(query=query):
                self.assertIn('Pulpitis', resolve_followup_query(query, history))
        pair = [user('SNA ve SNB anlat'), assistant('...')]
        resolved = resolve_followup_query('Bu ikisinin farkları ne ve normal değerleri kaç?', pair)
        requirement = build_dental_requirement_plan(resolved)
        self.assertEqual(2, len(requirement.subject_node_ids))
        self.assertIn('comparison', requirement.requested_facets)
        self.assertIn('value', requirement.requested_facets)
        self.assertEqual('Bu nedir?', resolve_followup_query('Bu nedir?', pair))


if __name__ == '__main__':
    unittest.main()
