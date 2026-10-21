import pytest
from app.academic_long_answer import stream_complete_structured_answer,LongAnswerError

class Provider:
    def __init__(self,segments):self.segments=iter(segments);self.calls=[]
    def generate_stream(self,**options):
        self.calls.append(options)
        text,self.last_finish_reason=next(self.segments)
        yield text

def options():
    return dict(prompt='Kaynaklar ve 20 soru isteği',max_output_tokens=16000,response_schema={'type':'object'})

def test_truncated_json_replaced_by_one_complete_document():
    provider=Provider([('{"questions":[','MAX_TOKENS'),('{"questions":[]}','STOP')])
    assert ''.join(stream_complete_structured_answer(provider,options()))=='{"questions":[]}'
    assert len(provider.calls)==2
    assert provider.calls[1]['max_output_tokens']==32000
    assert provider.calls[1]['prompt']==provider.calls[0]['prompt']
    assert provider.calls[1]['response_schema']==provider.calls[0]['response_schema']

def test_ordinary_json_needs_one_call():
    provider=Provider([('{}','STOP')])
    assert ''.join(stream_complete_structured_answer(provider,options()))=='{}'
    assert len(provider.calls)==1

def test_repeated_limit_never_publishes_partial_json():
    provider=Provider([('{"questions":[','MAX_TOKENS'),('{"questions":[','MAX_TOKENS')])
    output=[]
    with pytest.raises(LongAnswerError):
        output.extend(stream_complete_structured_answer(provider,options()))
    assert output==[] and len(provider.calls)==2

def test_thinking_only_limit_can_recover():
    provider=Provider([('','MAX_TOKENS'),('{}','STOP')])
    assert ''.join(stream_complete_structured_answer(provider,options()))=='{}'
