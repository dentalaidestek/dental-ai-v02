from io import BytesIO
from types import SimpleNamespace
import pytest
from pypdf import PdfReader
from app.academic_pdf import render_pdf, pdf_requested, AcademicPDFError


def test_pdf_preserves_turkish_tables_math_and_hides_internal_metadata():
    data=render_pdf('Ortodonti - çalışma notları',
        '# Deri noktaları\n| Nokta | Tanım |\n| --- | --- |\n'
        '| Pronasale | Burun ucu; ölçüm 90° ± 2; α |\n'
        '| ŞğİıÇöÜ | Üst dudak sınırı |\n\n'
        '<img src="https://private.invalid/secret">\n<!--ACADEMIC_SOURCE_REQUEST:abc-->')
    assert data.startswith(b'%PDF-')
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
    assert 'ŞğİıÇöÜ' in text and 'Üst dudak sınırı' in text
    assert '90° ± 2' in text and 'α' in text and 'Pronasale' in text
    assert 'ACADEMIC_SOURCE_REQUEST' not in text


def test_long_pdf_paginates_without_omitting_last_table_row():
    body='| Soru | Tanım |\n| --- | --- |\n'+'\n'.join(
        f'| Soru {n} | Çalışma - Türkçe diş hekimliği açıklaması. |' for n in range(1,151))
    reader=PdfReader(BytesIO(render_pdf('Sınav soruları',body)))
    assert len(reader.pages)>1
    text='\n'.join(page.extract_text() for page in reader.pages)
    assert 'Soru 1' in text and 'Soru 150' in text


@pytest.mark.parametrize('body', ['', 'x'*240001, '<!--ACADEMIC_SOURCE_REQUEST:abc-->'])
def test_invalid_pdf_content_never_advertises_a_file(body):
    with pytest.raises(AcademicPDFError): render_pdf('Not',body)


@pytest.mark.parametrize('format,operation,evidence,expected', [
    ('text','answer',True,False), ('pdf','answer',True,True),
    ('pdf','clarify',True,False), ('pdf','answer',False,False),
])
def test_pdf_requires_current_semantic_request_and_supported_completed_answer(format,operation,evidence,expected):
    understanding=SimpleNamespace(plan=SimpleNamespace(output_format=format,operation=operation))
    assert pdf_requested(understanding,SimpleNamespace(evidence_sufficient=evidence)) is expected
