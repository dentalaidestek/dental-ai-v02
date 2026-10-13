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
