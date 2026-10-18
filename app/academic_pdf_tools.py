"""Owned PDF operations chosen by the model, executed without generation/OCR.

Store a small recipe, not PDF bytes or storage credentials, in the existing
message. Resolve every dependency again at download so deleting a source revokes
access. File work runs after the short read transaction has ended.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import threading

from sqlmodel import select

PREFIX = '<!--ACADEMIC_PDF_TOOL_V1-->\n'
MAX_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PAGES = 500
_slots = threading.BoundedSemaphore(2)

SOURCE_SCHEMA = {'type':'object','properties':{
    'kind':{'type':'string','enum':['generated','uploaded']},
    'turn':{'type':['integer','null']},'filename':{'type':'string'},
    'part':{'type':'integer'}},'required':['kind','turn','filename','part'],'additionalProperties':False}
SEGMENT_SCHEMA = {'type':'object','properties':{
    'source':{'type':'integer'},'pages':{'type':'array','maxItems':500,'items':{'type':'integer'}},
    'exclude':{'type':'array','maxItems':500,'items':{'type':'integer'}},
    'rotation':{'type':'integer','enum':[0,90,180,270]}},
    'required':['source','pages','exclude','rotation'],'additionalProperties':False}
OUTPUT_SCHEMA = {'type':'object','properties':{
    'name':{'type':'string'},'segments':{'type':'array','minItems':1,'maxItems':32,'items':SEGMENT_SCHEMA},
    'fields':{'type':'array','maxItems':200,'items':{'type':'object','properties':{
        'name':{'type':'string'},'value':{'type':'string'}},
        'required':['name','value'],'additionalProperties':False}}},
    'required':['name','segments','fields'],'additionalProperties':False}
TOOL_SCHEMA = {'type':['object','null'],'properties':{
    'action':{'type':'string','enum':['inspect','extract_text','transform']},
    'sources':{'type':'array','minItems':1,'maxItems':8,'items':SOURCE_SCHEMA},
    'outputs':{'type':'array','maxItems':16,'items':OUTPUT_SCHEMA}},
    'required':['action','sources','outputs'],'additionalProperties':False}


class PDFToolError(ValueError):
    pass


def is_recipe(content):
    return isinstance(content,str) and content.startswith(PREFIX)


def _digest(value):
    return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()


def validate_tools(tool):
    if tool is None:
        return
    if not isinstance(tool,dict) or set(tool)!={'action','sources','outputs'} or tool['action'] not in {'inspect','extract_text','transform'}:
        raise PDFToolError('Geçersiz PDF işlemi.')
    sources,outputs=tool['sources'],tool['outputs']
    if not isinstance(sources,list) or not 1<=len(sources)<=8 or not isinstance(outputs,list) or len(outputs)>16:
        raise PDFToolError('PDF işlem kapsamı geçersiz.')
    for source in sources:
        if (not isinstance(source,dict) or set(source)!={'kind','turn','filename','part'}
            or source['kind'] not in {'generated','uploaded'} or type(source['part']) is not int or not 0<=source['part']<16
            or not isinstance(source['filename'],str) or len(source['filename'])>400
            or '\x00' in source['filename']
            or (source['turn'] is not None and (type(source['turn']) is not int or not 0<=source['turn']<8))
            or (source['kind']=='uploaded' and (not source['filename'].strip() or source['turn'] is not None or source['part']))):
            raise PDFToolError('PDF kaynağı geçersiz.')
    if tool['action']=='transform' and not outputs:
        raise PDFToolError('PDF çıktı planı eksik.')
    if tool['action']=='inspect' and outputs:
        raise PDFToolError('İnceleme için çıktı planı kullanılmaz.')
    for output in outputs:
        if (not isinstance(output,dict) or set(output)!={'name','segments','fields'}
            or not isinstance(output['name'],str) or not 1<=len(output['name'])<=100
            or any(char in output['name'] for char in '/\\\x00\r\n')
            or not isinstance(output['segments'],list) or not 1<=len(output['segments'])<=32
            or not isinstance(output['fields'],list) or len(output['fields'])>200):
            raise PDFToolError('PDF çıktı planı geçersiz.')
        for segment in output['segments']:
            if (not isinstance(segment,dict) or set(segment)!={'source','pages','exclude','rotation'}
                or type(segment['source']) is not int or not 0<=segment['source']<len(sources)
                or type(segment['rotation']) is not int or segment['rotation'] not in {0,90,180,270}):
                raise PDFToolError('PDF sayfa işlemi geçersiz.')
            for key in ('pages','exclude'):
                values=segment[key]
                if (not isinstance(values,list) or len(values)>500
                    or any(type(n) is not int or n==0 or abs(n)>MAX_PAGES for n in values)):
                    raise PDFToolError('PDF sayfa seçimi geçersiz.')
        names=[]
        if tool['action'] != 'transform' and output['fields']:
            raise PDFToolError('Form alanları yalnız düzenleme işleminde kullanılabilir.')
        for field in output['fields']:
            if (not isinstance(field,dict) or set(field)!={'name','value'}
                or not isinstance(field['name'],str) or not 1<=len(field['name'])<=200
                or not isinstance(field['value'],str) or len(field['value'])>4000
                or '\x00' in field['name']+field['value']):
                raise PDFToolError('Form alanı geçersiz.')
            names.append(field['name'])
        if len(set(names))!=len(names):
            raise PDFToolError('Aynı form alanı iki kez belirtilmiş.')


def recipe_data(content):
    if not is_recipe(content) or len(content)>120000:
        raise PDFToolError('PDF işlem kaydı geçersiz.')
    try:
        data=json.loads(content[len(PREFIX):])
        if not isinstance(data,dict) or set(data)!={'sources','outputs'}:
            raise ValueError()
        # Reuse all output bounds; source identifiers below are server-owned.
        validate_tools({'action':'transform','sources':[
            {'kind':'generated','turn':None,'filename':'','part':0} for _ in data['sources']],
            'outputs':data['outputs']})
        for source in data['sources']:
            if (not isinstance(source,dict) or set(source)!={'kind','id','digest','part'}
                or source['kind'] not in {'message','material'} or type(source['id']) is not int
                or source['id']<=0 or type(source['part']) is not int or not 0<=source['part']<16
                or not isinstance(source['digest'],str) or len(source['digest'])!=64):
                raise ValueError()
        return data
    except (ValueError,TypeError,KeyError):
        raise PDFToolError('PDF işlem kaydı geçersiz.') from None


def output_files(content,course_id,message_id):
    from app.academic_remote_pdf import is_remote,output_files as remote_files
    if is_remote(content):
        return remote_files(content,course_id,message_id)
    if not is_recipe(content):
        return []
    try:
        data=recipe_data(content)
    except PDFToolError:
        return []
    from app.academic_pdf import pdf_filename
    return [{'type':'pdf','name':pdf_filename(output['name']),
        'url':f'/notes/courses/{int(course_id)}/ai/messages/{int(message_id)}/pdf?part={i}'}
        for i,output in enumerate(data['outputs'])]


def describe_recipe(content):
    from app.academic_remote_pdf import is_remote,describe
    if is_remote(content):
        return describe(content)
    try:
        names=[output['name'] for output in recipe_data(content)['outputs']]
        return '[PDF dosya çıktıları: '+', '.join(names)+'. Sayfa/form işlemleri uygulanmış dosya; özgün metin yanıtı değildir.]'
    except PDFToolError:
        return '[PDF dosyası bu sürümde okunamıyor.]'


def _owned_row(session,model,ident,owner,course):
    row=session.exec(select(model).where(model.id==ident,model.owner_user_id==owner,model.course_id==course)).first()
    if row is None or getattr(row,'deleted_at',None) is not None:
        raise PDFToolError('PDF kaynağı bulunamadı veya erişim yetkiniz yok.')
    return row


def _snapshot(session,message_model,material_model,refs,owner,course,depth=0,seen=None,title='Ders notları'):
    seen=set() if seen is None else seen
    if depth>4:
        raise PDFToolError('PDF işlem zinciri çok uzun; özgün dosyadan tekrar işlem yapın.')
    results=[]
    for ref in refs:
        key=(ref['kind'],ref['id'])
        if key in seen or len(seen)>=16:
            raise PDFToolError('PDF işlem zinciri döngülü veya çok geniş.')
        seen.add(key)
        row=_owned_row(session,message_model if ref['kind']=='message' else material_model,ref['id'],owner,course)
        if ref['kind']=='message':
            if row.role!='ASSISTANT' or not row.mode.endswith('_PDF') or _digest(row.content)!=ref['digest']:
                raise PDFToolError('PDF kaynağı değişmiş; son sürüm üzerinden tekrar deneyin.')
            item={'kind':'message','content':row.content,'part':ref['part'],'title':title}
            if is_recipe(row.content):
                data=recipe_data(row.content)
                item['recipe']=data
                item['children']=_snapshot(session,message_model,material_model,data['sources'],owner,course,depth+1,seen,title)
            elif ref['part']:
                raise PDFToolError('Bu PDF’de seçilen çıktı bulunamadı.')
        else:
            if row.mime_type!='application/pdf' or row.size_bytes>MAX_BYTES:
                raise PDFToolError('Kaynak desteklenen boyutta bir PDF değil.')
            item={'kind':'material','path':row.file_path,'digest':ref['digest']}
        results.append(item)
        seen.remove(key)
    return results


def _reader(data):
    from pypdf import PdfReader
    if len(data)>MAX_BYTES or not data.startswith(b'%PDF-'):
        raise PDFToolError('Kaynak desteklenen boyutta bir PDF değil.')
    reader=PdfReader(BytesIO(data))
    if reader.is_encrypted or not 1<=len(reader.pages)<=MAX_PAGES:
        raise PDFToolError('Şifreli veya çok büyük PDF bu işlemde kullanılamıyor.')
    return reader


def _load(items,budget):
    from app.academic_pdf import render_pdf
    from app.object_storage import ensure_local
    results=[]
    for item in items:
        budget['sources']+=1
        if budget['sources']>16:
            raise PDFToolError('PDF kaynak sayısı işlem sınırını aşıyor.')
        if item['kind']=='material':
            path=Path(ensure_local(item['path']))
            if path.stat().st_size>MAX_BYTES:
                raise PDFToolError('PDF kaynak boyutu işlem sınırını aşıyor.')
            data=path.read_bytes()
            if _digest(data)!=item['digest']:
                raise PDFToolError('Yüklenen PDF değişmiş; son sürüm üzerinden tekrar deneyin.')
        elif 'recipe' in item:
            children=_load(item['children'],budget)
            data=_transform(children,item['recipe']['outputs'],only=item['part'])[0]
        else:
            data=render_pdf(item['title'],item['content'])
        budget['bytes']+=len(data)
        if budget['bytes']>MAX_BYTES:
            raise PDFToolError('Toplam PDF kaynak boyutu işlem sınırını aşıyor.')
        results.append(_reader(data))
    return results


def _indices(segment,reader):
    total=len(reader.pages)
    def resolve(n):
        index=n-1 if n>0 else total+n
        if not 0<=index<total:
            raise PDFToolError('İstenen sayfa PDF’nin sınırları dışında.')
        return index
    excluded={resolve(n) for n in segment['exclude']}
    values=[resolve(n) for n in segment['pages']] if segment['pages'] else list(range(total))
    return [index for index in values if index not in excluded]


def _transform(readers,outputs,only=None):
    from pypdf import PdfReader,PdfWriter
    if only is not None and not 0<=only<len(outputs):
        raise PDFToolError('PDF çıktısı bulunamadı.')
    rendered=[];page_budget=0;byte_budget=0
    for number,output in enumerate(outputs):
        if only is not None and number!=only:
            continue
        writer=PdfWriter()
        try:
            for segment in output['segments']:
                reader=readers[segment['source']]
                for field in (reader.get_fields() or {}).values():
                    if field.get('/FT')=='/Sig' and field.get('/V'):
                        raise PDFToolError('Dijital imzalı PDF’nin imzasını koruyarak bu işlem yapılamaz.')
                indices=_indices(segment,reader)
                page_budget+=len(indices)
                if page_budget>MAX_PAGES:
                    raise PDFToolError('Toplam çıktı sayfa sayısı işlem sınırını aşıyor.')
                start=len(writer.pages)
                writer.append(reader,pages=indices,import_outline=False)
                for page in list(writer.pages)[start:]:
                    if segment['rotation']:
                        page.rotate(segment['rotation'])
                    page.pop('/AA',None)
            if not writer.pages:
                raise PDFToolError('İşlem bütün sayfaları çıkarıyor; boş PDF oluşturulmadı.')
            values={field['name']:field['value'] for field in output['fields']}
            if values:
                fields=writer.get_fields() or {}
                if set(values)-set(fields):
                    raise PDFToolError('Form alanı bulunamadı. Önce PDF’nin form alanlarını inceleyin.')
                for name,value in values.items():
                    if fields[name].get('/FT') not in {'/Tx','/Btn','/Ch'}:
                        raise PDFToolError('Bu form alanı desteklenmiyor.')
                    if fields[name].get('/MaxLen') and len(value)>fields[name]['/MaxLen']:
                        raise PDFToolError('Form alanı değeri izin verilen uzunluğu aşıyor.')
                writer.update_page_form_field_values(None,values,auto_regenerate=False)
            out=BytesIO();writer.write(out);data=out.getvalue()
            byte_budget+=len(data)
            if len(data)>MAX_OUTPUT_BYTES or byte_budget>MAX_BYTES:
                raise PDFToolError('PDF çıktı boyutu işlem sınırını aşıyor.')
            final=PdfReader(BytesIO(data))
            if len(final.pages)!=len(writer.pages):
                raise PDFToolError('PDF sayfa doğrulaması tamamlanamadı.')
            if values:
                fields=final.get_fields() or {}
                if any(name not in fields or str(fields[name].get('/V',''))!=value for name,value in values.items()):
                    raise PDFToolError('Form alanı doğrulaması tamamlanamadı.')
                seen_fields=set()
                for page in final.pages:
                    for ref in page.get('/Annots',[]):
                        widget=ref.get_object();parent=widget;parts=[];value=None;visited=set()
                        while parent is not None and id(parent) not in visited:
                            visited.add(id(parent))
                            if '/T' in parent:
                                parts.insert(0,str(parent['/T']))
                            if value is None and '/V' in parent:
                                value=parent['/V']
                            parent=parent['/Parent'].get_object() if parent.get('/Parent') else None
                        name='.'.join(parts)
                        if name in values:
                            seen_fields.add(name)
                            if str(value or '')!=values[name] or not widget.get('/AP',{}).get('/N'):
                                raise PDFToolError('Form alanının görünümü veya değeri doğrulanamadı.')
                if seen_fields!=set(values):
                    raise PDFToolError('Form alanı ile sayfadaki alan eşleşmedi.')
            rendered.append(data)
        finally:
            writer.close()
    return rendered


def render_owned_recipe(session,*,message_model,material_model,owner_user_id,course_id,content,part=0,title='Ders notları'):
    data=recipe_data(content)
    snapshots=_snapshot(session,message_model,material_model,data['sources'],owner_user_id,course_id,title=title)
    session.rollback()  # End the read transaction before disk/object-storage work.
    if not _slots.acquire(timeout=3):
        raise PDFToolError('PDF işleme kapasitesi dolu. Lütfen tekrar deneyin.')
    try:
        readers=_load(snapshots,{'bytes':0,'sources':0})
        return _transform(readers,data['outputs'],only=part)[0]
    finally:
        _slots.release()


def _prepare_operations(session,*,message_model,material_model,plan,owner_user_id,course_id,history,query,title='Ders notları'):
    from app.study_retrieval_v2 import RetrievalResult
    from app.object_storage import ensure_local
    tool=plan.pdf_tools
    try:
        validate_tools(tool)
        refs=[]
        for source in tool['sources']:
            if source['kind']=='generated':
                if source['turn'] is None:
                    from app.academic_pdf_revision import latest_owned_pdf
                    row=latest_owned_pdf(session,message_model,owner_user_id,course_id)
                else:
                    turns=history[-8:];turn=turns[source['turn']] if source['turn']<len(turns) else {}
                    row=_owned_row(session,message_model,turn.get('id'),owner_user_id,course_id)
                if row is None or row.role!='ASSISTANT' or not row.mode.endswith('_PDF'):
                    raise PDFToolError('İşlenecek oluşturulmuş PDF bulunamadı.')
                part=source['part']
                if source['filename']:
                    from app.academic_pdf import pdf_filename
                    files=output_files(row.content,course_id,row.id)
                    names=[item['name'] for item in files] if files else [pdf_filename(title)]
                    matches=[i for i,name in enumerate(names)
                        if name.casefold()==pdf_filename(source['filename']).casefold()]
                    if len(matches)!=1 or (part and part!=matches[0]):
                        raise PDFToolError('İstenen dosya adı seçilen PDF çıktısıyla eşleşmiyor.')
                    part=matches[0]
                refs.append({'kind':'message','id':row.id,'digest':_digest(row.content),'part':part})
            else:
                rows=list(session.exec(select(material_model).where(
                    material_model.owner_user_id==owner_user_id,material_model.course_id==course_id,
                    material_model.original_filename==source['filename'])).all())
                if len(rows)!=1 or getattr(rows[0],'deleted_at',None) is not None:
                    raise PDFToolError('Yüklenen PDF bulunamadı veya adı birden fazla dosyayla eşleşiyor.')
                row=rows[0]
                if row.mime_type!='application/pdf' or row.size_bytes>MAX_BYTES:
                    raise PDFToolError('Kaynak desteklenen boyutta bir PDF değil.')
                path,ident=row.file_path,row.id
                session.rollback()
                local=Path(ensure_local(path))
                if local.stat().st_size>MAX_BYTES:
                    raise PDFToolError('PDF kaynak boyutu işlem sınırını aşıyor.')
                refs.append({'kind':'material','id':ident,'digest':_digest(local.read_bytes()),'part':0})
        snapshots=_snapshot(session,message_model,material_model,refs,owner_user_id,course_id,title=title)
        session.rollback()
        readers=_load(snapshots,{'bytes':0,'sources':0})
        if tool['action']=='inspect':
            lines=[]
            for i,reader in enumerate(readers,1):
                lines.append(f'### PDF {i}\nSayfa sayısı: {len(reader.pages)}')
                fields=reader.get_fields() or {}
                lines.append('Doldurulabilir alanlar: '+(', '.join(fields) if fields else 'Yok'))
            answer='\n\n'.join(lines);mode='pdf_tool_text'
        elif tool['action']=='extract_text':
            outputs=tool['outputs'] or [{'segments':[{'source':i,'pages':[],'exclude':[],'rotation':0}
                for i in range(len(readers))]}]
            lines=[];pages=0
            for output in outputs:
                for segment in output['segments']:
                    reader=readers[segment['source']]
                    for index in _indices(segment,reader):
                        pages+=1
                        if pages>MAX_PAGES:
                            raise PDFToolError('Metin çıkarma sayfa sınırını aşıyor.')
                        lines.append(f'### PDF {segment["source"]+1}, sayfa {index+1}\n'+
                            (reader.pages[index].extract_text() or 'Bu sayfada çıkarılabilir metin yok; görsel/OCR okuması gerekir.'))
                        if sum(map(len,lines))>200000:
                            raise PDFToolError('Çıkarılan metin çok uzun; daha az sayfa seçin.')
            answer='\n\n'.join(lines);mode='pdf_tool_text'
        else:
            for output in tool['outputs']:
                for field in output['fields']:
                    if field['value'] not in query and field['value'] not in {'/Yes','/Off'}:
                        raise PDFToolError('Formda kullanılacak değeri mesajında aynen belirtir misin?')
            _transform(readers,tool['outputs'])  # Verify real files before advertising them.
            answer=PREFIX+json.dumps({'sources':refs,'outputs':tool['outputs']},ensure_ascii=False)
            mode='pdf_tool_document'
        return RetrievalResult(resolved_query=plan.resolved_query,retrieval_mode=mode,
            prepared_answer=answer,evidence_sufficient=True,
            study_task={'pdf_tool_validated':mode=='pdf_tool_document'})
    except Exception as exc:
        message=str(exc) if isinstance(exc,PDFToolError) else 'PDF dosyası okunamadı; mevcut dosya korunuyor.'
        return RetrievalResult(resolved_query=plan.resolved_query,retrieval_mode='pdf_tool_unavailable',clarification=message)


def prepare_operations(session, **kwargs):
    from app.study_retrieval_v2 import RetrievalResult
    if not _slots.acquire(timeout=3):
        return RetrievalResult(resolved_query=kwargs['plan'].resolved_query,
            retrieval_mode='pdf_tool_unavailable',clarification='PDF işleme kapasitesi dolu. Lütfen tekrar deneyin.')
    try:
        return _prepare_operations(session, **kwargs)
    finally:
        _slots.release()
