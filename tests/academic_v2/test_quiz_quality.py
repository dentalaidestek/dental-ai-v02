import json
from copy import deepcopy
import pytest
from app.academic_quiz import parse_quiz


def question():
    return {'stem':'Hangileri doğrudur?\nI. Risk olasılıktır.\nII. Risk kesin sonuçtur.\nIII. İlişki nedensellik değildir.',
        'options':['Yalnız I','Yalnız II','I ve II','I ve III','I, II ve III'],
        'correct':'D','rationale':'I ve III doğrudur.','fact':'Risk, ilişki ve nedensellik ayrımları.',
        'source':'Not.pdf, sayfa 1','material_id':1,'page':1,'topic':'Risk kavramları','asked_truth':True,
        'statements':[{'text':'Risk olasılıktır.','true':True},{'text':'Risk kesin sonuçtur.','true':False},
            {'text':'İlişki nedensellik değildir.','true':True}],
        'option_combinations':[[1],[2],[1,2],[1,3],[1,2,3]]}


def validate(q):return parse_quiz(json.dumps({'questions':[q]},ensure_ascii=False),1,require_quality=True)


def test_valid_multi_statement_key_matches_actual_displayed_option():
    assert validate(question())['questions'][0]['correct']=='D'


@pytest.mark.parametrize('damage',['key','displayed_option','truth','missing','bool_coercion','stem'])
def test_statement_errors_are_rejected_before_publishing(damage):
    q=question()
    if damage=='key':q['correct']='C'
    elif damage=='displayed_option':q['options'][3]='II ve III'
    elif damage=='truth':q['statements'][1]['true']=True
    elif damage=='missing':q['statements']=[];q['option_combinations']=[]
    elif damage=='bool_coercion':q['statements'][0]['true']='true'
    else:q['statements'][0]['text']='Not present in the question'
    with pytest.raises(ValueError):validate(q)


def test_false_statement_question_uses_requested_polarity():
    q=question();q['asked_truth']=False;q['correct']='B'
    q['stem']=q['stem'].replace('doğrudur','yanlıştır')
    assert validate(q)['questions'][0]['correct']=='B'


def test_requested_distinct_topics_cannot_be_cosmetic_duplicates():
    first=question();second=deepcopy(first)
    second['fact']='Başka bir bilginin sınanması.'
    second['stem']=second['stem'].replace('Risk','RİSK')
    with pytest.raises(ValueError,match='repeated main topic'):
        parse_quiz(json.dumps({'questions':[first,second]}),2,require_quality=True,distinct_topics=True)


def test_old_saved_quizzes_remain_readable_but_new_generation_requires_metadata():
    old=question()
    for key in ('topic','asked_truth','statements','option_combinations'):old.pop(key)
    assert parse_quiz(json.dumps({'questions':[old]}),1)
    with pytest.raises(ValueError):parse_quiz(json.dumps({'questions':[old]}),1,require_quality=True)
