import json
from types import SimpleNamespace
import pytest
from app.academic_exam_inventory import parse_inventory,unique_inventory,render_inventory


def record(page=4,number='21',topic='Sefalometri',text=None):
    return dict(material_id=1,page=page,number=number,topic=topic,
        text=text or 'Sefalometrik ölçümler ile yüz yüksekliği arasında hangi ilişki vardır? A) Birinci ifade B) İkinci ifade')


def test_inventory_rejects_foreign_pages_and_continuation_as_question_start():
    evidence=[SimpleNamespace(material_id=1,page_start=4,page_end=5,display_name='Owned.pdf')]
    with pytest.raises(ValueError):parse_inventory(json.dumps({'questions':[record(page=9)]}),evidence)
    assert not parse_inventory(json.dumps({'questions':[record(page=5)]}),evidence,[(1,4)])
    result=parse_inventory(json.dumps({'questions':[record()]}),evidence,[(1,4)])
    assert result[0]['filename']=='Owned.pdf'


def test_unmatched_record_is_excluded_explicitly_without_certifying_full_coverage():
    evidence=[SimpleNamespace(material_id=1,page_start=4,page_end=4,display_name='Owned.pdf')]
    rejected=[]
    records=parse_inventory(json.dumps({'questions':[record(),record(page=99)]}),evidence,rejected=rejected)
    assert len(records)==1 and len(rejected)==1
    answer=render_inventory(records,3,excluded=len(rejected))
    assert '1 kayıt kaynak sayfasıyla eşleşmediği için sayılmadı' in answer
    assert 'eksiksiz bir sınav dökümü değildir' in answer and 'sayfa 99' not in answer


def test_repeated_exam_copy_is_counted_once_but_changed_value_is_not_merged():
    first=record(text='İdeal yüz açısının 87.8 derece olduğu verilen durumda aşağıdaki ifadelerden hangisi doğrudur? A) Bir B) İki')
    duplicate=record(page=9,text=first['text'].replace('olduğu','oldugu'))
    other=record(page=10,text=first['text'].replace('87.8','84.0'))
    assert len(unique_inventory([first,duplicate,other]))==2


def test_frequency_table_sorts_actual_counts_and_lists_unique_sources():
    data=[{**record(),'filename':'Notes.pdf'},
          {**record(page=9),'filename':'Notes.pdf'},
          {**record(page=8,number='3',topic='Gelişim',text='Başın bıngıldak sayısını belirleyen soru ve seçenekler A) dört B) altı C) sekiz'),'filename':'Notes.pdf'},
          {**record(page=12,number='14',topic='Gelişim',text='Kafa kaidesinin geliştiği yapı ve seçenekleri A) Kıkırdak B) Diğer yapı'),'filename':'Notes.pdf'}]
    answer=render_inventory(data,2)
    assert '3 benzersiz' in answer and '1 kopya' in answer
    assert answer.index('| Gelişim | 2 |') < answer.index('| Sefalometri | 1 |')
    assert 'sayfa 9' not in answer and 'sayfa 4, soru 21' in answer


def test_unreadable_questions_cannot_support_counts():
    evidence=[SimpleNamespace(material_id=1,page_start=4,page_end=4,display_name='Owned.pdf')]
    assert not parse_inventory(json.dumps({'questions':[record(text='Soru [okunamadı]')]}),evidence)
