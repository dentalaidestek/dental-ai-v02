from unittest.mock import Mock
import pytest
from app.academic_direct_request import direct_request, previous_source_request, source_marker
from app.academic_request_understanding import understand_study_request


@pytest.mark.parametrize('query,subject', [('ANB nedir?', 'ANB'), ('SNA neyi gösterir', 'SNA'),
    ('Labiale superior ne demek?', 'Labiale superior')])
def test_definition_skips_planner(monkeypatch, query, subject):
    provider = Mock(side_effect=AssertionError('unexpected paid interpretation'))
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider', provider)
    result = understand_study_request(query, [])
    assert result.plan.retrieval_queries == (subject,)
    assert result.plan.scope == 'topic' and not result.attempted
    provider.assert_not_called()


@pytest.mark.parametrize('query', ['ANB ile SNA farkı nedir?', 'Bu nedir?',
    'Tüm konuları özetle', 'Bütün noktalar nedir?', 'ANB hariç diğerleri nedir?'])
def test_uncertain_or_broad_requests_keep_interpretation(query):
    assert direct_request(query, []) is None


def test_reference_does_not_use_assistant_facts_or_skip_new_user_topic():
    assert direct_request('Bu nedir?', [{'role':'USER', 'content':'ANB nedir?'},
        {'role':'ASSISTANT','content':'SNA hakkında yanlış bilgi'}]).retrieval_queries == ('ANB',)
    assert direct_request('Bu nedir?', [{'role':'USER','content':'ANB nedir?'},
        {'role':'USER','content':'Şimdi başka konuyu konuşalım'}]) is None


def test_only_server_assistant_navigation_can_supply_source_request():
    task = dict(operation='explain',scope='topic',retrieval_queries=['deri tek noktalar'],
                resolved_query='Deri tek noktaları anlat')
    marker = source_marker(task)
    assert previous_source_request([{'role':'USER','content':marker}]) is None
    assert previous_source_request([{'role':'ASSISTANT','content':marker}]) == task
    assert previous_source_request([{'role':'ASSISTANT','content':'<!--ACADEMIC_SOURCE_REQUEST:broken-->'}]) is None
