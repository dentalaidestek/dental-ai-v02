"""Execute the real client renderer, including untrusted model output."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def render(value):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the production chat renderer')
    template=Path('app/templates/notes_ai.html').read_text()
    start=template.index('    function escapeHtml(')
    end=template.index("    document.querySelectorAll('.study-chat-markdown')",start)
    script=template[start:end]+'\nprocess.stdout.write(JSON.stringify(safeMarkdown(JSON.parse(process.argv[1]))));'
    return json.loads(subprocess.check_output([node,'-e',script,json.dumps(value)],text=True))


@pytest.mark.parametrize('gap',['\n','\n\n'])
def test_tables_keep_all_rows_and_following_paragraph(gap):
    value=gap.join(['| Nokta | Tanım |','| :--- | :--- |',
        '| Pronasale | Burun ucu |','| Ls | Üst dudak |',
        '| Li | Alt dudak |','| Stomion | Dudak çizgisi |'])+'\n\nSonraki açıklama.'
    html=render(value)
    assert html.count('<tr>')==5
    assert html.count('<td>')==8
    assert '<p>Sonraki açıklama.</p>' in html
    assert '<th scope="col">Nokta</th>' in html


def test_table_cells_escape_untrusted_markup_and_keep_literal_pipes():
    html=render('| Ad | Açıklama |\n| --- | --- |\n| A\\|B | <img src=x onerror=alert(1)> **kalın** |')
    assert '<td>A|B</td>' in html
    assert '<img' not in html and '<script' not in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert '<strong>kalın</strong>' in html


def test_streaming_incomplete_table_is_not_discarded_and_metadata_is_hidden():
    partial='| Nokta | Tanım |\n| --'
    html=render(partial+'\n<!--ACADEMIC_SOURCE_REQUEST:abc-->')
    assert 'Nokta' in html and 'Tanım' in html
    assert '<table' not in html
    assert 'ACADEMIC_SOURCE_REQUEST' not in html
    assert '<h3>Başlık</h3>' in render('# Başlık\n- Madde')


def run_client_function(name, end_marker, harness):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the production chat client')
    template=Path('app/templates/notes_ai.html').read_text()
    start=template.index(name)
    end=template.index(end_marker,start)
    return json.loads(subprocess.check_output([node,'-e',template[start:end]+harness],text=True))


def test_interrupted_stream_keeps_partial_answer_restores_request_and_disables_export():
    result=run_client_function('    async function sendMessage(',"    form.addEventListener",r'''
const made=[];
function node(){return {removed:false,children:[],classList:{remove(){}},
  querySelector(){return this},appendChild(x){this.children.push(x)},remove(){this.removed=true}}}
const document={createElement:node};
const materialCount=1,v2Streaming=true,courseId=2,send={disabled:false},status={};
const input={value:'Soru',style:{},focus(){}};
const addMessage=()=>{const x=node();made.push(x);return x};
const safeMarkdown=x=>x,scrollChatBottom=()=>{};
let printButtons=0;const addPrintButton=()=>printButtons++;
const events=[{type:'delta',text:'Tamamlanan bölüm.'},{type:'error',error:'Geçici hizmet sorunu.'}];
const fetch=async()=>({ok:true,body:{getReader:()=>({read:async()=>({done:false,
 value:new TextEncoder().encode(events.map(x=>JSON.stringify(x)).join('\n')+'\n')})})}});
sendMessage('Tüm soruları aktar').then(()=>process.stdout.write(JSON.stringify({
 removed:made.map(x=>x.removed),input:input.value,status:status.textContent,
 warning:made[1].children[0].textContent,printButtons,enabled:!send.disabled})));
''')
    assert result['removed']==[False,False]
    assert result['input']=='Tüm soruları aktar'
    assert result['status']=='Geçici hizmet sorunu.'
    assert 'tamamlanmadı' in result['warning']
    assert result['printButtons']==0 and result['enabled']


def test_print_exports_only_selected_completed_answer_and_cleans_up():
    result=run_client_function('    function addPrintButton(',"    document.querySelectorAll('.study-chat-message.assistant')",r'''
let printed=0,cleanup;const classes=new Set();
function node(){return {children:[],appendChild(x){this.children.push(x)},
 addEventListener(name,fn){this[name]=fn},remove(){this.removed=true}}}
const body=node();body.classList={add:x=>classes.add(x),remove:x=>classes.delete(x)};
const document={body,createElement:node,getElementById:()=>null,
 querySelector:()=>({textContent:'Ders <script>başlığı</script>'})};
const window={addEventListener:(name,fn)=>{cleanup=fn},print:()=>printed++};
const selected={textContent:'Seçilen cevap'},content=node();
const article={querySelector:selector=>selector==='.study-answer-print'?null:
 selector==='.study-chat-content'?content:{cloneNode:()=>selected}};
addPrintButton(article);content.children[0].click();
const area=body.children[0];
const before={printed,title:area.children[0].textContent,selected:area.children[1]===selected,
 printing:classes.has('study-printing'),button:content.children[0].textContent};
cleanup();process.stdout.write(JSON.stringify({...before,removed:area.removed,clean:classes.size===0}));
''')
    assert result['printed']==1 and result['selected'] and result['printing']
    assert result['title']=='Ders <script>başlığı</script>'  # textContent, never HTML
    assert result['button']=='Yazdır / PDF kaydet'
    assert result['removed'] and result['clean']
