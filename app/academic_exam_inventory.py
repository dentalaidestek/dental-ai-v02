"""Validate readable exam records, deduplicate copies and count without an LLM."""
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

# Keep the provider grammar small. The owned-record validator below enforces
# the 160-record budget; expanding a large bounded array in the remote grammar
# is unnecessary and can make otherwise valid structured requests fail.
INVENTORY_SCHEMA = {'type':'object','properties':{'questions':{'type':'array',
    'items':{'type':'object','properties':{
        'material_id':{'type':'integer'},'page':{'type':'integer'},
        'number':{'type':['string','null']},'text':{'type':'string'},'topic':{'type':'string'}},
        'required':['material_id','page','number','text','topic'],'additionalProperties':False}}},
    'required':['questions'],'additionalProperties':False}


def parse_inventory(raw, evidence, primary_pages=(), *, rejected=None):
    raw=re.sub(r'<!--ACADEMIC_SOURCE_REQUEST:[A-Za-z0-9_=-]+-->','',raw).strip()
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)!={'questions'} or not isinstance(data['questions'],list) or len(data['questions'])>160:
        raise ValueError('invalid inventory')
    allowed={(e.material_id,p):e.display_name for e in evidence for p in range(e.page_start,e.page_end+1)}
    starts={tuple(pair) for pair in primary_pages} or set(allowed)
    records=[]
    for item in data['questions']:
        if not isinstance(item,dict) or set(item)!={'material_id','page','number','text','topic'}:
            raise ValueError('invalid question record')
        if type(item['material_id']) is not int or type(item['page']) is not int:
            raise ValueError('invalid source reference')
        key=(item['material_id'],item['page'])
        if key not in allowed:
            if rejected is not None:
                rejected.append('source_reference')
                continue
            raise ValueError('question outside selected start pages')
        if key not in starts:
            # This page is present only to finish the previous question. New
            # questions on it belong to the following batch, not this one.
            continue
        for field,limit in [('number',40),('text',6000),('topic',160)]:
            if field=='number' and item[field] is None:
                continue
            if not isinstance(item[field],str) or not item[field].strip() or len(item[field])>limit or '\x00' in item[field]:
                raise ValueError('invalid inventory field')
        # Unreadable question text cannot substantiate a frequency count.
        if re.search(r'\[(?:okunamadı|okunamadi|illegible)\]',item['text'],re.I):
            continue
        records.append({**item,'filename':allowed[key]})
    return records


def _key(value):
    value=unicodedata.normalize('NFKD',value.casefold())
    value=''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+',value))


def unique_inventory(records):
    unique=[];seen=set();physical=set();fingerprints=[]
    for item in sorted(records,key=lambda r:(r['material_id'],r['page'],r['number'] or '')):
        identity=(item['material_id'],item['page'],item['number'] or _key(item['text']))
        key=_key(item['text']);numbers=tuple(re.findall(r'\d+(?:[.,]\d+)?',item['text']))
        duplicate=identity in physical or (len(key)>=40 and key in seen)
        if not duplicate and len(key)>=60:
            for previous,old_numbers in fingerprints:
                if numbers!=old_numbers:
                    continue  # Different clinical values are different questions.
                match=SequenceMatcher(None,key,previous)
                if match.real_quick_ratio()>=.96 and match.quick_ratio()>=.96 and match.ratio()>=.96:
                    duplicate=True;break
        physical.add(identity)
        if duplicate:
            continue
        seen.add(key);fingerprints.append((key,numbers));unique.append(item)
    return unique


def render_inventory(records, count=None, *, excluded=0):
    unique=unique_inventory(records)
    if not unique:
        return 'Kaynak sayfalarında sayılabilir ve okunabilir bir soru envanteri doğrulayamadım; konu sıklığı sıralaması vermiyorum.'
    groups=defaultdict(list)
    for item in unique:
        groups[_key(item['topic'])].append(item)
    groups=sorted(groups.values(),key=lambda items:(-len(items),items[0]['topic'].casefold()))
    top=groups[:count if type(count) is int else 10]
    def cell(value):
        return ' '.join(str(value).split()).replace('|','\\|')
    lines=[f'Okunabilen {len(unique)} benzersiz soru kaydı sayıldı; {len(records)-len(unique)} kopya kayıt birleştirildi.',
           '', '| Konu | Benzersiz soru | Kaynaklar |','| --- | --- | --- |']
    if excluded:
        lines.insert(1,f'{excluded} kayıt kaynak sayfasıyla eşleşmediği için sayılmadı. Bu sonuç eksiksiz bir sınav dökümü değildir.')
    for items in top:
        refs='; '.join(f"{cell(q['filename'])}, sayfa {q['page']}, "
            +(f"soru {cell(q['number'])}" if q['number'] else 'numarasız soru') for q in items)
        lines.append(f"| {cell(items[0]['topic'])} | {len(items)} | {refs} |")
    lines+=['','Bu dağılım yalnız okunabilen ve kaynak sayfasıyla eşleşen kayıtlara dayanır. '
            'Konu etiketleri ayrı gruplar olarak sayılmıştır; okunamayan sorular hesaba katılmamıştır. '
            'Gelecek sınav için yalnız bir çalışma önceliği tahminidir.']
    return '\n'.join(lines)
