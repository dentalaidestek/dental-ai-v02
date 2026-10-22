from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader, select_autoescape


def test_voice_panel_is_inline_and_requires_explicit_confirmation():
    env = Environment(loader=FileSystemLoader('app/templates'), autoescape=select_autoescape())
    html = env.get_template('voice_exam_panel.html').render(patient=SimpleNamespace(id=7))
    assert 'data-patient-id="7"' in html
    assert 'data-voice-consent' in html and 'data-voice-confirm' in html
    assert 'data-voice-save-appointment' in html
    assert 'live ilaç' not in html
    assert 'canlı ilaç etkileşimi veya acil durum takibi yapmaz' in html
    assert 'speechRecognition' not in Path('app/static/voice-exam.js').read_text()
    assert 'localStorage' not in Path('app/static/voice-exam.js').read_text()
