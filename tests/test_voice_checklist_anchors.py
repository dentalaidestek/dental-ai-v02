from app import voice_exam_final as final


def test_whitespace_is_not_a_patient_anchor_for_a_question():
    fields={'medications':{'value':'Bir ilaç kullanıyorum.'}}
    assert final._anchored([{'field':'medications','quote':' ','text':'Soru'}],fields)==[]


def test_blank_explanation_cannot_create_an_empty_question_card():
    fields={'medications':{'value':'Bir ilaç kullanıyorum.'}}
    assert final._anchored([{'field':'medications','quote':'Bir ilaç','text':' \n'}],fields)==[]


def test_whitespace_cannot_be_one_side_of_a_contradiction():
    fields={'medications':{'value':'Bir ilaç kullanıyorum.'},'plan':{'value':'İlaçX'}}
    item={'field':'medications','quote':' ','other_field':'plan','other_quote':'İlaçX','text':'Çelişki'}
    assert final._contradictions([item],fields)==[]
