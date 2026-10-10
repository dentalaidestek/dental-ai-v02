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
    def test_course_salience_operators_do_not_become_medical_topics(self):
        from app.academic_task_language import course_source_request
        for query in ('Notlarda önemli noktaları göster', 'Slaytlardan kritik yerleri seç',
                      'Ders notlarından önemli başlıkları belirle'):
            with self.subTest(query=query):
                self.assertTrue(course_source_request(query))
                requirement = build_dental_requirement_plan(query)
                self.assertFalse(requirement.subject_terms)
                self.assertTrue(_course_coverage_requested(query, requirement, classify_academic_study_task(query)))
        for query in ('Notlardan pulpitis tedavisini göster', 'Slaytlardan mandibula kırıklarını bul'):
            self.assertFalse(course_source_request(query))
            self.assertTrue(build_dental_requirement_plan(query).subject_terms)

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

    def test_corrections_use_individual_user_topics_and_unique_matches(self):
        history = [user('kök yüzeyi düzleştirme ve mental foramen anlat.'),
                   assistant('Yanlış örnek olarak mental foramen diyebilirim.')]
        resolved = resolve_followup_query('yok mental forame anlat', history)
        self.assertEqual('mental foramen', resolved.split(' — ', 1)[0])
        pair = [user('alveolit ve mukogingival cerrahi anlat.')]
        resolved = resolve_followup_query('kral yok mukogingival cerrahi anlatsana', pair)
        self.assertNotIn('alveolit', resolved)
        self.assertIn('mukogingival cerrahi', resolved)
        # Two equally close, user-authored terms cannot be resolved by recency.
        ambiguous = [user('Nance anlat'), user('Nanse anlat')]
        self.assertEqual('yok Nante anlat', resolve_followup_query('yok Nante anlat', ambiguous))

    def test_joined_correction_clears_question_generation(self):
        history = [user('furkasyon lezyonları anlat'), assistant('...'),
                   user('test hazırla'), assistant('...')]
        resolved = resolve_followup_query('yoksoru istemiyorum normal anlat', history)
        self.assertIn('furkasyon lezyonları', resolved)
        self.assertNotIn('soru hazırla', resolved)
        repeated = resolve_followup_query('yoook soooru istemiyorum normal anlat', history)
        self.assertIn('furkasyon lezyonları', repeated)
        self.assertNotIn('soru hazırla', repeated)
        for query in ('yok sru istemiyorum normal anlat', 'yok sou isteiyorum normal anlat'):
            resolved = resolve_followup_query(query, history)
            self.assertIn('furkasyon lezyonları', resolved)
            self.assertNotIn('soru hazırla', resolved)

    def test_insufficient_evidence_streams_followup_without_provider_call(self):
        import ast
        from pathlib import Path
        from typing import Iterator
        from app.study_retrieval_v2 import RetrievalResult
        # Exercise the actual generator's early evidence branches without a
        # configured external provider; this is not an HTTP integration test.
        tree = ast.parse((Path(__file__).parents[2] / 'app/study_ai_v2.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'stream_rag_v2')
        def forbidden_provider_call():
            self.fail('Insufficient evidence must not invoke generation')
        import logging
        namespace = {'Iterator': Iterator, 'RetrievalResult': RetrievalResult,
                     'logger': logging.getLogger('test.study_dialogue'),
                     '_generation_targets': forbidden_provider_call}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'study_ai_v2.py', 'exec'), namespace)
        for result in (RetrievalResult(resolved_query='Pulpitis anlat'),
                       RetrievalResult(resolved_query='Pulpitis tedavisi', note_context=['kanıt'],
                                       missing_facets=('tedavi',)),
                       RetrievalResult(resolved_query='Bu ders notlarını özetle', retrieval_mode='coverage')):
            with self.subTest(mode=result.retrieval_mode):
                response = ''.join(namespace['stream_rag_v2']('Ders', 'anlat', [], result))
                self.assertTrue(response)
                self.assertNotIn('Bu soruyla ilişkilendirilebilecek ders notu bulunamadı', response)
        self.assertIn('pulpitis', ''.join(namespace['stream_rag_v2'](
            'Ders', 'anlat', [], RetrievalResult(resolved_query='Pulpitis anlat'))).casefold())

    def test_noisy_scope_controls_do_not_mutate_medical_nouns(self):
        from app.study_retrieval_v2 import _normalize_state_controls
        history = [user('Flor anlat'), assistant('...'),
                   user('çocuk hastalar açısından anlat'), assistant('...')]
        adult = resolve_followup_query('yok çocuk değil rşkin açısından', history)
        self.assertNotIn('çocuk', adult.split(' — ')[0])
        self.assertIn('erişkin açısından', adult)
        general = resolve_followup_query('yaş grubunu bover geel anlat', history)
        self.assertNotIn('çocuk', general)
        self.assertIn('Flor', general)
        for text in ('kök yüzeyi anlat', 'süt pulpa tedavisi', 'erken tanı açısından anlat',
                     'çürük açısından anlat', 'çürük hastalar açısından anlat'):
            self.assertEqual(text, _normalize_state_controls(text))
        self.assertEqual('boru istemiyorum normal anlat',
                         _normalize_state_controls('boru istemiyorum normal anlat'))

    def test_noisy_count_and_table_are_task_slots(self):
        history = [user('Pulpitis anlat'), assistant('...')]
        self.assertIn('soru hazırla', resolve_followup_query('yok 20 sru lsun', history))
        self.assertNotIn('soru hazırla', resolve_followup_query('yok 20 mg olsun', history))
        self.assertIn('tablo şeklinde', resolve_followup_query('bunu talo eklinde ver', history))
        for request in ('20 soru olsun', 'İki soru istiyorum', '10 soru lazım'):
            plan = build_dental_requirement_plan(request)
            self.assertTrue(_course_coverage_requested(request, plan, classify_academic_study_task(request)))
        self.assertIsNone(classify_academic_study_task('20 mg olsun'))

    def test_source_scope_handles_study_goals_and_spelled_counts(self):
        for query in ('Bu notlardan sınava çalışalım, önemli yerleri mantığıyla anlat.',
                      'Ders notlarından iki soru hazırla; cevap anahtarını gösterme.',
                      'Bu ders notlarını konu konu anlat.',
                      'Bu slaytlardaki konuyu bana öğret.',
                      'Bu materyallerden iki soru hazırla.'):
            with self.subTest(query=query):
                plan = build_dental_requirement_plan(query)
                self.assertFalse(plan.subject_terms)
                self.assertTrue(_course_coverage_requested(query, plan, classify_academic_study_task(query)))
        named = 'Bu notlardan flor çalışalım.'
        self.assertTrue(build_dental_requirement_plan(named).subject_terms)

    def test_named_unknown_topic_in_notes_is_not_a_source_search_term(self):
        for query in ('Bu ders notlarında geçen Nance ne işe yarar?',
                      'Notlara göre Nance anlat'):
            with self.subTest(query=query):
                self.assertEqual(('Nance',), build_dental_requirement_plan(query).subject_terms)
                self.assertEqual(['Nance'], _retrieval_terms(query)[0])
                resolved = resolve_followup_query('Bunu daha basit anlat', [user(query)])
                self.assertEqual('Nance', resolved.split(' — ')[0])

    def test_goal_changes_do_not_become_new_topics(self):
        history = [user('apeksifikasyon anlat'), assistant('...'),
                   user('ezberlemek için anlat'), assistant('...')]
        resolved = resolve_followup_query('yok sınav için anlat', history)
        self.assertIn('apeksifikasyon', resolved.split(' — ')[0])
        self.assertNotIn('ezberlemek', resolved.split(' — ')[0])
        correction = resolve_followup_query('taaabloo olmasın normal anlat', history)
        self.assertIn('apeksifikasyon', correction.split(' — ')[0])

    def test_compound_clinical_topic_is_one_referent(self):
        history = [user('mandibula kondil kırığı anlat'), assistant('...'),
                   user('madde madde anlat'), assistant('...')]
        resolved = resolve_followup_query('bunu tablo şeklinde ver', history)
        self.assertIn('kondil kırığı', resolved.split(' — ')[0])
        self.assertEqual('Bu nedir?', resolve_followup_query('Bu nedir?', [user('SNA ve SNB anlat')]))
        repeated = resolve_followup_query('buuunuu çocuk hastalar açısından anlat', history)
        self.assertIn('kondil kırığı', repeated)
        previous = [user('odontoma anlat'), assistant('...'), user('mental foramen anlat'), assistant('...')]
        self.assertIn('odontoma', resolve_followup_query('önceki asıl konudan devam et', previous))
        sole = [user('Wits analizi anlat'), assistant('Yanlışlıkla inferior alveolar sinir dedim.')]
        self.assertIn('Wits', resolve_followup_query('önceki asıl konudan devam et', sole))
        self.assertEqual('bir önceki konuya dön', resolve_followup_query('bir önceki konuya dön', sole))

    def test_free_text_answer_uses_pending_question_but_new_requests_do_not(self):
        history = [user('Bana bir soru sor ve cevabımı bekle'), assistant('Soru 1\n' + QUESTION)]
        for reply in ('Ağrı', 'Ağrı olduğu için pulpitis düşünüyorum', 'Cevabım ağrı'):
            with self.subTest(reply=reply):
                reference = active_question_reference(reply, history)
                self.assertIsNotNone(reference)
                self.assertIn('Pulpitis', reference.topic)
                self.assertIn('Pulpitis', resolve_followup_query(reply, history))
                self.assertIn('ders kanıtlarıyla değerlendir', dialogue_rules(reply, history))
        for query in ('Flor nedir?', 'Şimdi flor anlat', 'Yeni konuya geç', 'devam et',
                      'teşekkürler', 'daha basit', 'tablo'):
            self.assertIsNone(active_question_reference(query, history))
        batch = [assistant('Soru 1\nPulpitis?\nSoru 2\nFlor?')]
        self.assertTrue(answer_needs_reference('Ağrı', batch))
        self.assertFalse(answer_needs_reference('Flor nedir?', batch))
        lecture = [user('Pulpitis anlat'), assistant('Pulpitis neden ağrır? Çünkü ...')]
        self.assertIsNone(active_question_reference('Flor', lecture))
        outline = [user('Notları özetle'), assistant('1. Pulpitis\n2. Flor')]
        self.assertFalse(answer_needs_reference('Nance', outline))

    def test_learner_practice_and_program_requests_are_operations(self):
        for query in ('Beni çalıştır', 'Bana notlardan çalışma programı çıkar'):
            with self.subTest(query=query):
                plan = build_dental_requirement_plan(query)
                self.assertFalse(plan.subject_terms)
                self.assertTrue(_course_coverage_requested(query, plan, classify_academic_study_task(query)))
        self.assertIn('yalnız bir soru', dialogue_rules('Beni çalıştır', []))
        history = [user('Pulpitis anlat'), assistant('...')]
        self.assertIn('Pulpitis', resolve_followup_query('Beni çalıştır', history))
        self.assertNotEqual('generate_questions', getattr(classify_academic_study_task('Motoru çalıştır'), 'task', None))

    def test_comprehension_repair_uses_topic_or_clarifies_without_a_search(self):
        from types import SimpleNamespace
        from app.study_retrieval_v2 import retrieve_course_context_v2
        session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        history = [user('Pulpitis anlat'), assistant('Pulpitis açıklaması.')]
        resolved = resolve_followup_query('anlamadım', history)
        self.assertIn('Pulpitis', resolved)
        self.assertNotIn('anlamadım', build_dental_requirement_plan(resolved).subject_terms)
        raw_plan = build_dental_requirement_plan('anlamadım')
        self.assertFalse(raw_plan.subject_terms)
        self.assertFalse(_course_coverage_requested('anlamadım', raw_plan, classify_academic_study_task('anlamadım')))
        result = retrieve_course_context_v2(session, owner_user_id=1, course_id=3, query='anlamadım')
        self.assertEqual('clarification', result.retrieval_mode)
        self.assertTrue(result.clarification)

    def test_courtesy_bypasses_note_search_and_preserves_pending_question(self):
        from types import SimpleNamespace
        from app.study_retrieval_v2 import retrieve_course_context_v2
        from app.academic_dialogue import ACKNOWLEDGEMENT_RESPONSE
        session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
        for query in ('teşekkürler', 'tamam', 'anladım'):
            result = retrieve_course_context_v2(session, owner_user_id=1, course_id=3, query=query)
            self.assertEqual('conversation', result.retrieval_mode)
            self.assertEqual(ACKNOWLEDGEMENT_RESPONSE, result.clarification)
            self.assertFalse(result.evidence)
        history = [user('Bana bir soru sor'), assistant('Soru 1\n' + QUESTION),
                   user('tamam'), assistant(ACKNOWLEDGEMENT_RESPONSE)]
        self.assertIn('Pulpitis', resolve_followup_query('B', history))
        unnumbered = [user('Bana bir soru sor'), assistant('Pulpitis hangi belirtiyi verir?'),
                      user('tamam'), assistant(ACKNOWLEDGEMENT_RESPONSE)]
        self.assertIsNotNone(active_question_reference('Ağrı', unnumbered))


if __name__ == '__main__':
    unittest.main()
