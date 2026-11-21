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


def run_client_function(name, end_marker, harness, prefix=''):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the production chat client')
    template=Path('app/templates/notes_ai.html').read_text()
    start=template.index(name)
    end=template.index(end_marker,start)
    # prefix şablon diliminden ÖNCE koşar: dilim üst-seviye ifadeleri (ör.
    # visibilitychange listener'ları) TDZ'ye takılmadan stub'ları bulsun.
    return json.loads(subprocess.check_output([node,'-e',prefix+template[start:end]+harness],text=True))


def test_interrupted_run_keeps_partial_answer_restores_request():
    # 35c2397a sonrası akış durable runs'a geçti: sendMessage POST /runs ile çalışma
    # açar, followRun poll eder; INTERRUPTED çalışma kısmi cevabı sunucuda tutar,
    # istemci bekleyen balonu temizler, isteği geri yükler ve hatayı gösterir.
    result=run_client_function('    async function followRun(',"    async function uploadChatFiles(",r'''
sendMessage('Tüm soruları aktar').then(async()=>{while(activeRun)await new Promise(r=>setTimeout(r,20));process.stdout.write(JSON.stringify({
 removed:made.map(x=>x.removed),input:input.value,status:status.textContent,
 partial:made[1].children.some(x=>x.className==='study-run-partial'),artifacts,enabled:!send.disabled}))});
''', prefix=r'''
function node(){return {removed:false,children:[],classList:{remove(){}},
  querySelector(sel){return sel==='.study-run-partial'?null:this},appendChild(x){this.children.push(x)},remove(){this.removed=true}}}
const document={createElement:node,hidden:false,getElementById:()=>({addEventListener(){}}),addEventListener:()=>{}};
var activeRun=null;var runTimer=null;var learningTimer=null;var learningChannel=null;
var refreshLearning=()=>{};var refreshQuizzes=()=>{};var setWorking=()=>{};
var addRunCancel=()=>{};var learningText=()=>{};
const window={addEventListener:()=>{}};
const made=[];
const materialCount=1,v2Streaming=true,courseId=2,send={disabled:false},status={};
const input={value:'Soru',style:{},focus(){}};
const attach=null,applyIndexReadiness=()=>{};
const addMessage=()=>{const x=node();made.push(x);return x};
const safeMarkdown=x=>x,scrollChatBottom=()=>{};
let artifacts=0;const addPdfArtifact=()=>artifacts++;
const events=[{type:'delta',text:'Tamamlanan bölüm.'},{type:'error',error:'Geçici hizmet sorunu.'}];
const fetch=async url=> url.includes('/ai/runs/active')
 ? {ok:true,json:async()=>({ok:true,run:null})}
 : (url.includes('/ai/runs/9')
    ? {ok:true,json:async()=>({ok:true,run:{id:9,status:'INTERRUPTED',partial:'Tamamlanan bölüm.',
        error:'Geçici hizmet sorunu.',question:'Tüm soruları aktar'}})}
    : {ok:true,json:async()=>({ok:true,run:{id:9,status:'RUNNING'}})});
''')
    assert result['removed']==[True,True]
    assert result['input']=='Tüm soruları aktar'
    assert result['status']=='Geçici hizmet sorunu.'
    assert result['partial'] is True
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
