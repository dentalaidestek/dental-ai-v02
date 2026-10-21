import json
import pytest
from app.academic_long_answer import stream_complete_structured_answer,LongAnswerError,_complete_question_prefix

class Provider:
    def __init__(self,segments):self.segments=iter(segments);self.calls=[]
    def generate_stream(self,**options):
        self.calls.append(options)
        text,self.last_finish_reason=next(self.segments)
        yield text

def options():
    return dict(prompt='Kaynaklar ve 20 soru isteği',max_output_tokens=16000,response_schema={'type':'object'})

def test_complete_questions_survive_and_only_missing_questions_requested():
    first={'stem':'İlk soru aynen korunmalı','options':['A','B'],'correct':'A'}
    second={'stem':'İkinci soru','correct':'B'}
    prefix='{"questions":['+json.dumps(first)+',{"stem":"yarım'
    provider=Provider([(prefix,'MAX_TOKENS'),(json.dumps({'questions':[second]}),'STOP')])
    result=json.loads(''.join(stream_complete_structured_answer(provider,options(),expected_count=2)))
    assert result['questions']==[first,second]
    assert 'Yalnız kalan 1 soruyu üret' in provider.calls[1]['prompt']
    assert 'İlk soru aynen korunmalı' in provider.calls[1]['prompt']
    assert 'yarım' not in provider.calls[1]['prompt']
    assert provider.calls[1]['response_schema']==provider.calls[0]['response_schema']

def test_multiple_continuations_preserve_order():
    p=Provider([('{"questions":[{"stem":"1"},','MAX_TOKENS'),
        ('{"questions":[{"stem":"2"},','MAX_TOKENS'),
        ('{"questions":[{"stem":"3"}]}','STOP')])
    result=json.loads(''.join(stream_complete_structured_answer(p,options(),expected_count=3)))
    assert [q['stem'] for q in result['questions']]==['1','2','3']
    assert 'Yalnız kalan 1 soruyu üret' in p.calls[2]['prompt']

def test_complete_count_can_close_truncated_envelope():
    p=Provider([('{"questions":[{"stem":"1"}','MAX_TOKENS')])
    assert json.loads(''.join(stream_complete_structured_answer(p,options(),expected_count=1)))=={'questions':[{'stem':'1'}]}
    assert len(p.calls)==1

def test_ordinary_json_needs_one_call():
    p=Provider([('{}','STOP')])
    assert ''.join(stream_complete_structured_answer(p,options()))=='{}'
    assert len(p.calls)==1

def test_no_progress_after_retained_questions_fails_without_publishing():
    p=Provider([('{"questions":[{"stem":"1"},','MAX_TOKENS'),('{"questions":[','MAX_TOKENS')])
    output=[]
    with pytest.raises(LongAnswerError):
        output.extend(stream_complete_structured_answer(p,options(),expected_count=2))
    assert output==[] and len(p.calls)==2

def test_wrong_remaining_count_fails_closed():
    p=Provider([('{"questions":[{"stem":"1"},','MAX_TOKENS'),('{"questions":[]}','STOP')])
    with pytest.raises(LongAnswerError):
        list(stream_complete_structured_answer(p,options(),expected_count=2))

def test_thinking_only_limit_has_no_completed_questions_to_reuse():
    p=Provider([('','MAX_TOKENS'),('{}','STOP')])
    assert ''.join(stream_complete_structured_answer(p,options()))=='{}'

def test_prefix_decoder_respects_escaped_quotes_and_braces():
    item={'stem':'A quote " and } bracket ] inside text'}
    raw='{"questions":['+json.dumps(item)+',{"stem":"partial'
    assert _complete_question_prefix(raw)==[item]
