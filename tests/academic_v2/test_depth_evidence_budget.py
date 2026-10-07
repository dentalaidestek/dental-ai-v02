"""Detailed answers allocate more evidence without changing the relevance gate."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.academic_task_language import wants_deeper_evidence
from app import study_retrieval_v2 as retrieval


def session():
    return SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))


class DepthEvidenceBudgetTests(unittest.TestCase):
    def test_depth_and_negated_depth_have_distinct_budgets(self):
        for query in ('Pulpitis detaylı anlat', 'Biraz daha ayrıntılı anlat',
                      'Bu çok yüzeysel her başlığı açıkla', 'Diğer başlıklar nerede', 'Bu eksik'):
            self.assertTrue(wants_deeper_evidence(query), query)
        for query in ('Pulpitis nedir?', 'Kısaca açıkla', 'Detay istemiyorum',
                      'Pulpitis detaylı anlatma', 'Ayrıntılı açıklama istemiyorum'):
            self.assertFalse(wants_deeper_evidence(query), query)

    def test_course_detail_hydrates_larger_budget_while_fast_path_stays_24(self):
        history = [{'role': 'USER', 'content': 'Bu ders notlarını özetle'}]
        plan = SimpleNamespace(buckets=(), scanned_rows=0)
        for query, expected in [('Notları özetle', 24), ('Bu eksik', 48),
                                ('Diğer başlıklar nerede', 48)]:
            with self.subTest(query=query), \
                 patch.object(retrieval, 'get_or_build_coverage_plan', return_value=plan) as build, \
                 patch.object(retrieval, '_coverage_evidence_rows', return_value=[]) as hydrate:
                result = retrieval.retrieve_course_context_v2(session(), owner_user_id=7,
                    course_id=3, query=query, recent_history=history)
                self.assertEqual(build.call_args.kwargs['requested_count'], expected)
                self.assertEqual(hydrate.call_args.kwargs['limit'], expected)
                self.assertFalse(result.evidence_sufficient)

    def test_topic_detail_requests_more_candidates_and_reads_neighbor_even_if_sufficient(self):
        row = (42, 5, 'Endo', 2, 2, 'Pulpitis', 'TEXT',
               'Pulpitis pulpanın iltihabıdır. Pulpitis pulpa dokusunda gelişen inflamasyondur.',
               None, None, None, None, 1.0, 2, '{}')
        history = [{'role': 'USER', 'content': 'Pulpitis nedir?'}]
        for query, candidate_limit, neighbor_expected in [('Pulpitis nedir?', 24, False),
                                                        ('Daha detaylı anlat', 48, True)]:
            with self.subTest(query=query), \
                 patch.object(retrieval, '_fts_rows', return_value=[row]) as fts, \
                 patch.object(retrieval, '_neighbor_rows', return_value=[]) as neighbors, \
                 patch.object(retrieval, '_evidence_sufficiency', return_value=SimpleNamespace(
                     sufficient=True, confidence=1.0, covered_facets=(), missing_facets=())):
                result = retrieval.retrieve_course_context_v2(session(), owner_user_id=7,
                    course_id=3, query=query, recent_history=history)
                self.assertEqual(fts.call_args_list[0].kwargs['limit'], candidate_limit)
                self.assertEqual(neighbors.called, neighbor_expected)
                if neighbor_expected:
                    self.assertEqual(neighbors.call_args.kwargs['limit'], 4)
                self.assertTrue(result.evidence_sufficient)

    def test_empty_expanded_candidates_do_not_pass_existing_gate(self):
        with patch.object(retrieval, '_fts_rows', return_value=[]), \
             patch.object(retrieval, '_neighbor_rows', return_value=[]):
            result = retrieval.retrieve_course_context_v2(session(), owner_user_id=7,
                course_id=3, query='Pulpitis detaylı anlat')
        self.assertFalse(result.evidence_sufficient)
        self.assertEqual(result.evidence_confidence, 0.0)


if __name__ == '__main__':
    unittest.main()
