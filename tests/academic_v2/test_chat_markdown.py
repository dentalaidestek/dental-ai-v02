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
    result=run_client_function('    async function sendMessage(',"    async function uploadChatFiles(",r'''
const made=[];
function node(){return {removed:false,children:[],classList:{remove(){}},
  querySelector(){return this},appendChild(x){this.children.push(x)},remove(){this.removed=true}}}
const document={createElement:node};
const materialCount=1,v2Streaming=true,courseId=2,send={disabled:false},status={};
const input={value:'Soru',style:{},focus(){}};
const attach=null,applyIndexReadiness=()=>{};
const addMessage=()=>{const x=node();made.push(x);return x};
const safeMarkdown=x=>x,scrollChatBottom=()=>{};
let artifacts=0;const addPdfArtifact=()=>artifacts++;
const events=[{type:'delta',text:'Tamamlanan bölüm.'},{type:'error',error:'Geçici hizmet sorunu.'}];
const fetch=async()=>({ok:true,body:{getReader:()=>({read:async()=>({done:false,
 value:new TextEncoder().encode(events.map(x=>JSON.stringify(x)).join('\n')+'\n')})})}});
sendMessage('Tüm soruları aktar').then(()=>process.stdout.write(JSON.stringify({
 removed:made.map(x=>x.removed),input:input.value,status:status.textContent,
 warning:made[1].children[0].textContent,artifacts,enabled:!send.disabled})));
''')
    assert result['removed']==[False,False]
    assert result['input']=='Tüm soruları aktar'
    assert result['status']=='Geçici hizmet sorunu.'
    assert 'tamamlanmadı' in result['warning']
    assert result['artifacts']==0 and result['enabled']


def test_pdf_outputs_have_separate_safe_links_without_duplicates():
    result=run_client_function('    function addPdfArtifact(', '    function isNearBottom(', r'''
const courseId=6,links=[],markdown={textContent:''};
const article={querySelectorAll:()=>links,querySelector:s=>s==='.study-chat-content'?{appendChild:x=>links.push(x)}:markdown};
const document={createElement:()=>({children:[],appendChild(x){this.children.push(x)},getAttribute(name){return this[name]}})};
const files=[0,1].map(part=>({type:'pdf',url:'/notes/courses/6/ai/messages/40/pdf?part='+part,name:'<script>name</script>.pdf'}));
addPdfArtifact(article,{files});addPdfArtifact(article,{files});
addPdfArtifact(article,{type:'pdf',url:'/notes/courses/7/ai/messages/40/pdf?part=0'});
addPdfArtifact(article,{type:'pdf',url:'/notes/courses/6/ai/messages/40/pdf?part=16'});
addPdfArtifact(article,{type:'pdf',url:'javascript:alert(1)'});
process.stdout.write(JSON.stringify({urls:links.map(x=>x.href),names:links.map(x=>x.children[1].textContent),notice:markdown.textContent}));
''')
    assert result['urls']==[f'/notes/courses/6/ai/messages/40/pdf?part={i}' for i in range(2)]
    assert result['names']==['<script>name</script>.pdf']*2  # textContent, never HTML
    assert result['notice']=='İstediğin PDF hazır.'
