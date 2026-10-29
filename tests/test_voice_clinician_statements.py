"""Transient clinician attribution is not a diagnosis or verified speaker label."""
from app import voice_exam_core as core, voice_exam_final as final

QUOTE = 'Bu ilaçla diğer ilaç birlikte kesinlikle sorun çıkarmaz.'


def test_clinician_statement_is_preserved_without_becoming_a_patient_fact():
    result = core.normalize({'transcript': 'Hekim: '+QUOTE, 'clinical_facts': [
        {'field': 'clinician_statement', 'value': 'İlaç güvenliği iddiası', 'quote': QUOTE, 'temporality': 'CURRENT'}]})
    assert result['fields'] == {}
    assert len(result['communication']) == 1
    assert result['communication'][0]['category'] == 'CLINICAL_STATEMENT'
    assert result['communication'][0]['quote'] == QUOTE
    assert not core.normalize({'transcript':'Başka bir konuşma.', 'clinical_facts': [
        {'field':'clinician_statement','value':'Uydurma','quote':QUOTE,'temporality':'CURRENT'}]})['communication']


def test_unsupported_clinician_statement_is_explicitly_unverified_not_silently_cleared(monkeypatch):
    calls=[]
    monkeypatch.setattr(final,'retrieve',lambda *a,**kw:{'references':[],'unavailable':[], 'coverage':'limited','notice':'Synthetic'})
    def review(prompt,data,schema):
        calls.append(data)
        return {'questions':[],'contradictions':[],'clinical_items':[]}
    monkeypatch.setattr(final,'review',review)
    context={'fields':{'chief_complaint':{'value':'Kontrole geldim.','quote':'Kontrole geldim.'}}}
    insight={'category':'CLINICAL_STATEMENT','quote':QUOTE,'observation':'Hekime atfedilen klinik ifade','suggestion':'Kaynak kapsamını kontrol edin.'}
    result=final.finalize(context,[insight])
    assert calls[0]['clinical_fields']['clinician_0']['value']==QUOTE
    assert not any(item['field'].startswith('clinician_') for item in result['summary'])
    assert result['clinician_review']==[{'field':'clinician_0','quote':QUOTE,'status':'unverified','source_ids':[]}]
    assert not result['clinical_items']


def test_clinician_statement_overflow_is_explicit_instead_of_silently_dropping_claims():
    import pytest
    quotes=[f'Klinik ifade {i}.' for i in range(25)]
    facts=[{'field':'clinician_statement','value':q,'quote':q,'temporality':'CURRENT'} for q in quotes]
    with pytest.raises(core.VoiceError):core.normalize({'transcript':' '.join(quotes),'clinical_facts':facts})


def test_clinician_only_encounter_can_be_reviewed_without_creating_a_patient_fact(monkeypatch):
    monkeypatch.setattr(final,'retrieve',lambda *a,**kw:{'references':[],'unavailable':[],'coverage':'limited','notice':'Synthetic'})
    monkeypatch.setattr(final,'review',lambda *a,**kw:{'questions':[],'contradictions':[],'clinical_items':[]})
    result=final.finalize({},[{'category':'CLINICAL_STATEMENT','quote':QUOTE,'observation':'Hekime atfedilen ifade'}])
    assert result['summary']==[]
    assert result['clinician_review'][0]['status']=='unverified'


def test_literal_control_point_is_reported_without_claiming_statement_verified(monkeypatch):
    source='Synthetic source text requiring assessment.'
    monkeypatch.setattr(final,'retrieve',lambda *a,**kw:{'references':[{'id':'s','excerpts':[source],'clinical_use':True}],
        'unavailable':[],'coverage':'limited','notice':'Synthetic'})
    monkeypatch.setattr(final,'review',lambda *a,**kw:{'questions':[],'contradictions':[], 'clinical_items':[
        {'source_id':'s','source_quote':source,'patient_field':'clinician_0','patient_quote':QUOTE,
         'consideration':'Hekim kapsamı değerlendirsin.','missing_information':'Klinik bağlam','alternative':''}]})
    output=final.finalize({},[{'category':'CLINICAL_STATEMENT','quote':QUOTE,'observation':'Hekime atfedilen ifade'}])
    assert output['clinician_review']==[{'field':'clinician_0','quote':QUOTE,'status':'control_point_present','source_ids':['s']}]
    assert output['summary']==[]


def test_clinician_patient_contradiction_can_be_expressed_in_provider_schema(monkeypatch):
    patient='Alerjim var.'
    monkeypatch.setattr(final,'retrieve',lambda *a,**kw:{'references':[],'unavailable':[],'coverage':'limited','notice':'Synthetic'})
    def review(prompt,data,schema):
        props=schema['properties']['contradictions']['items']['properties']
        assert 'clinician_0' in props['field']['enum']
        assert 'clinician_0' in props['other_field']['enum']
        return {'questions':[],'clinical_items':[],'contradictions':[
            {'field':'clinician_0','quote':QUOTE,'other_field':'allergies','other_quote':patient,'text':'Beyanların kapsamını netleştirin.'}]}
    monkeypatch.setattr(final,'review',review)
    output=final.finalize({'fields':{'allergies':{'value':patient,'quote':patient}}},[
        {'category':'CLINICAL_STATEMENT','quote':QUOTE,'observation':'Hekime atfedilen ifade'}])
    assert output['contradictions'][0]['field']=='clinician_0'
