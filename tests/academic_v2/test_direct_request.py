from unittest.mock import Mock
import pytest
from app.academic_direct_request import direct_request, previous_source_request, source_marker
from app.academic_request_understanding import understand_study_request


@pytest.fixture(autouse=True)
def opt_in_local_routing(monkeypatch):
    monkeypatch.setenv('STUDY_ACADEMIC_LOCAL_ROUTING','1')


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


@pytest.mark.parametrize('subject',['Pulpitis tedavisi','Hipofiz etkisi','Labiale superior','ANB açısı'])
@pytest.mark.parametrize('suffix,operation', [('kısaca anlat','explain'),('detaylı açıkla','explain'),
    ('özetle','summarize'),('öğret','teach'),('tablo halinde anlat','explain'),
    ('hakkında 10 zor soru hazırla','generate_questions')])
def test_complete_tasks_across_different_subjects_skip_planning(monkeypatch,subject,suffix,operation):
    provider=Mock(side_effect=AssertionError('Unexpected planner call'))
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider',provider)
    query=subject+' '+suffix
    result=understand_study_request(query,[])
    assert result.plan.operation==operation
    assert result.plan.retrieval_queries==(subject,)
    assert result.plan.resolved_query==query
    assert result.plan.count==(10 if operation=='generate_questions' else None)
    provider.assert_not_called()


def test_explicit_comparison_keeps_independent_searches_and_original_request():
    result=direct_request('SNA ile ANB arasındaki farkları açıkla',[])
    assert result.operation=='compare'
    assert result.retrieval_queries==('SNA','ANB')
    assert result.resolved_query=='SNA ile ANB arasındaki farkları açıkla'


@pytest.mark.parametrize('query', ['Hepsini tablo halinde anlat','Bunu kısaca açıkla',
    'Kodlama yap bunları kolay ezberleyeyim'])
def test_complete_style_followups_reuse_source_topic_not_all_course(query):
    history=[{'role':'ASSISTANT','content':source_marker(dict(operation='explain',scope='topic',
        retrieval_queries=['sefalometrik deri tek noktalar'],resolved_query='Deri tek noktaları anlat',
        source_kind='notes'))}]
    result=direct_request(query,history)
    assert result.scope=='topic'
    assert result.retrieval_queries==('sefalometrik deri tek noktalar',)
    assert query in result.resolved_query


@pytest.mark.parametrize('query', ['ANB anlat ama SNA olmasın','ANB ile SNA açıkla',
    'ANB yerine SNA özetle','ANB 10 değil 20 soru hazırla', 'ANB özetle sonra soru hazırla',
    'Hepsini tablo halinde anlat'])
def test_unaccounted_clauses_and_missing_references_are_not_guessed(query):
    assert direct_request(query,[]) is None
