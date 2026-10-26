from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from types import SimpleNamespace
import json,re,shutil
root=Path(__file__).resolve().parents[1]
env=Environment(loader=FileSystemLoader(root/'app/templates'))
panel=env.get_template('voice_exam_panel.html').render(patient=SimpleNamespace(id=999000))
panel=re.sub(r'<script\b[^>]*>.*?</script>','',panel,flags=re.S)
js=(root/'app/static/voice-exam.js').read_text()
helper=js[js.index('  function reviewIcon('):js.index('  async function finalizeReview(')]
fixture={'summary':[{'text':'Örnek klinik bilgi 1','quote':'Örnek hasta beyanı 1'},{'text':'Örnek klinik bilgi 2','quote':'Örnek hasta beyanı 2'}], 'clinical_items':[{'title':'İlaç ve tedavi uyumu','consideration':'İlaç adı ve dozu doğrulanmalı; kaynak önerisi hasta özelinde incelenmeli.','patient_quote':'Konuşmada belirtilen ilaç ve planlanan işlem birlikte değerlendirildi.','source_quote':'Yalnız görsel düzen testi için sentetik alıntı. Klinik öneri değildir.','missing_information':'','alternative':'','source_id':'s1'}], 'questions':[{'text':'Örnek soru 1','quote':'Örnek dayanak 1'},{'text':'Örnek soru 2','quote':'Örnek dayanak 2'}], 'contradictions':[], 'references':[{'id':f's{i}','url':'https://example.org','institution':'Örnek','title':f'Görsel test kaynağı {i}'} for i in range(1,4)],'notice':'Sentetik örnek; canlı muayene değerlendirmesi değildir.','unavailable':[]}
nav='<nav class="mobile-bottom-nav">'+''.join(f'<a href="#" aria-label="{label}"><img src="/static/vendor/tabler/{icon}.svg" alt="" width="24" height="24"><span>{label}</span></a>' for label,icon in [('Anasayfa','home'),('Hastalar','users'),('Analiz','chart-bar'),('Mesajlar','message'),('Profilim','user')])+'</nav>'
style='body{max-width:390px;margin:0 auto;font-family:Arial,sans-serif;background:#f5f7fb;color:#14243b}.mobile-bottom-nav{max-width:390px;margin:0 auto;position:fixed;bottom:0;left:0;right:0;height:50px;z-index:10;align-items:center;justify-content:space-around;background:white;border-top:1px solid #dce3ee}.mobile-bottom-nav a{display:grid;justify-items:center;gap:4px;font-size:10px;text-decoration:none;color:#6c7890}.voice-review-actions{display:flex;flex-direction:column}.voice-exam[data-final-ready="true"] .voice-review>.voice-advanced,.voice-exam[data-final-ready="true"] .voice-review-actions>[data-voice-discard],.voice-review-actions+.voice-help{display:none}'
html='<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Muayene özeti · sentetik önizleme</title><style>'+style+'</style><section class="voice-entry voice-session-page"><header class="voice-session-top"><a href="#" aria-label="Geri"><img src="/static/vendor/tabler/arrow-left.svg" width="24" height="24" alt=""></a><strong>Muayene özeti</strong><span>DENTAL <b>AI</b></span></header>'+panel+'</section>'+nav+'<script>'+helper+'\nconst root=document.getElementById("voice-exam");root.dataset.finalReady="true";root.dataset.liveState="paused";root.dataset.liveFinished="true";root.dataset.showReview="true";root.querySelector(".voice-review").hidden=false;root.querySelector(".voice-stage").hidden=true;root.querySelector(".voice-review-heading .voice-eyebrow").textContent="Sesli muayene tamamlandı";renderFinalReview(root.querySelector("[data-voice-final-results]"),'+json.dumps(fixture,ensure_ascii=False)+',[{observation:"Örnek iletişim gözlemi",quote:"Örnek söz",suggestion:"Örnek öneri"}]);root.querySelector(".voice-result-clinical").open=true;const save=root.querySelector("[data-voice-save]");save.disabled=false;save.addEventListener("click",()=>{save.textContent="Örnek kayıt tamamlandı";save.disabled=true});</script></html>'
(root/'design-preview/screen.html').write_text(html)
print('Preview built from production template, renderer and CSS; synthetic data only.')

assets=root/'design-preview/static'
assets.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'app/static/voice-exam.css',assets/'voice-exam.css')
shutil.copytree(root/'app/static/vendor',assets/'vendor',dirs_exist_ok=True)
