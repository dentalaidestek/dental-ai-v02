from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment,DictLoader
import re
import pytest

@pytest.mark.parametrize('mode',['RAG_V2_HYBRID','RAG_V2_HYBRID_PDF'])
def test_answer_actions_render_before_javascript_for_owned_answer(mode):
    template=Path('app/templates/notes_ai.html').read_text()
    env=Environment(loader=DictLoader({'notes_ai.html':template,'base.html':'{% block content %}{% endblock %}'}),autoescape=True)
    messages=[SimpleNamespace(id=1,role='USER',content='Soru',mode='NOTES_PLUS'),
        SimpleNamespace(id=2,role='ASSISTANT',content='Yanıt',mode=mode)]
    html=env.get_template('notes_ai.html').render(course=SimpleNamespace(id=6,title='Ders'),
        material_count=1,messages=messages,v2_streaming=True,v2_ready=True)
    articles=re.findall(r'<article[^>]*class="study-chat-message ([^"]+)"[^>]*>(.*?)</article>',html,re.S)
    assistant=next(body for role,body in articles if role=='assistant')
    user=next(body for role,body in articles if role=='user')
    for label in ('Beğen','Beğenme','Kopyala'):
        assert re.search(r'<button[^>]*aria-label="'+label+r'"[^>]*><svg',assistant)
    assert 'study-answer-actions' not in user
