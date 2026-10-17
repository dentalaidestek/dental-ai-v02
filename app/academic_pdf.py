"""Private, source-answer PDFs. No vendor calls or external HTML resources."""
import html
from io import BytesIO
from pathlib import Path
import re
import threading

MAX_PDF_TEXT = 240_000
_font_lock = threading.Lock()
_render_slots = threading.BoundedSemaphore(2)
_fonts_ready = False


class AcademicPDFError(ValueError):
    pass


def pdf_requested(understanding, retrieval, answer=''):
    from app.academic_long_answer import automatic_pdf
    if automatic_pdf(answer, retrieval):
        return True
    plan = getattr(understanding, 'plan', None)
    return bool(plan and getattr(plan, 'output_format', 'text') == 'pdf' and plan.operation != 'clarify'
                and retrieval.evidence_sufficient)


def pdf_filename(title):
    title = re.sub(r'[^\w\s-]', '', str(title), flags=re.UNICODE).strip()[:70]
    return (title or 'Ders notları') + '.pdf'


def pdf_artifact(course_id, message_id, title, *, automatic=False):
    return {'type': 'pdf', 'name': pdf_filename(title),
            'reason': 'long_answer' if automatic else 'requested',
            'url': f'/notes/courses/{int(course_id)}/ai/messages/{int(message_id)}/pdf'}


def _fonts():
    global _fonts_ready
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _font_lock:
        if not _fonts_ready:
            directory = Path(__file__).parent / 'assets' / 'fonts'
            pdfmetrics.registerFont(TTFont('DentalSans', str(directory / 'DejaVuSans.ttf')))
            pdfmetrics.registerFont(TTFont('DentalSans-Bold', str(directory / 'DejaVuSans-Bold.ttf')))
            pdfmetrics.registerFontFamily('DentalSans', normal='DentalSans', bold='DentalSans-Bold',
                                         italic='DentalSans', boldItalic='DentalSans-Bold')
            _fonts_ready = True


def _clean(value):
    value = re.sub(r'<!--ACADEMIC_(?:SOURCE_REQUEST:[A-Za-z0-9_=-]+|Q_CURSOR:\d+:\d+)-->', '', value)
    for word, symbol in {'circ':'°', 'rightarrow':'→', 'leftarrow':'←', 'times':'×',
                         'pm':'±', 'leq':'≤', 'geq':'≥', 'alpha':'α', 'beta':'β', 'gamma':'γ'}.items():
        value = re.sub(r'\^?\s*\\' + word + r'\b', symbol, value)
    value = re.sub(r'\\(?:text|mathrm|mathbf)\{([^{}]*)\}', r'\1', value)
    value = re.sub(r'\\[()[\]]', '', value)
    return re.sub(r'\$([^$\n]+)\$', r'\1', value).replace('\x00', '')


def _inline(value):
    value = html.escape(value, quote=False)
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', value)


def _cells(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith(r'\|'):
        line = line[:-1]
    return [item.strip().replace(r'\|', '|') for item in re.split(r'(?<!\\)\|', line)]


def render_pdf(title, answer):
    if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_PDF_TEXT:
        raise AcademicPDFError('PDF içeriği oluşturulabilecek uzunluğu aşıyor veya boş.')
    answer = _clean(answer)
    if not answer.strip():
        raise AcademicPDFError('PDF içeriği boş.')
    if not _render_slots.acquire(timeout=5):
        raise AcademicPDFError('PDF hazırlama kapasitesi şu anda dolu. Lütfen tekrar dene.')
    try:
        return _render(title, answer)
    finally:
        _render_slots.release()


def _render(title, answer):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
    _fonts()
    styles = {
        'body': ParagraphStyle('body', fontName='DentalSans', fontSize=10, leading=15, spaceAfter=7,
                               splitLongWords=True, alignment=TA_LEFT),
        'heading': ParagraphStyle('heading', fontName='DentalSans-Bold', fontSize=13, leading=18,
                                  spaceBefore=12, spaceAfter=8, keepWithNext=True),
        'title': ParagraphStyle('title', fontName='DentalSans-Bold', fontSize=20, leading=27, spaceAfter=18),
        'cell': ParagraphStyle('cell', fontName='DentalSans', fontSize=8.5, leading=12, splitLongWords=True),
        'bullet': ParagraphStyle('bullet', fontName='DentalSans', fontSize=10, leading=15, spaceAfter=6,
                                leftIndent=13, bulletIndent=1, bulletFontName='DentalSans'),
    }
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=38, leftMargin=38,
                                 topMargin=38, bottomMargin=40, title=str(title)[:200], author='Dental AI Akademik')
    story = [Paragraph(_inline(str(title)[:200]), styles['title'])]
    lines = answer.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if index+1 < len(lines) and '|' in line:
            separators = _cells(lines[index+1])
            header = _cells(line)
            if len(header) > 1 and len(header) == len(separators) and all(
                    re.fullmatch(r':?-{3,}:?', cell) for cell in separators):
                rows = [header]
                index += 2
                while index < len(lines) and lines[index].strip() and '|' in lines[index]:
                    row = _cells(lines[index])
                    if len(row) != len(header):
                        break
                    rows.append(row)
                    index += 1
                if len(header) <= 8:
                    width = A4[0]-76
                    widths = [width*.28, width*.72] if len(header) == 2 else [width/len(header)]*len(header)
                    cells = [[Paragraph(_inline(cell), styles['cell']) for cell in row] for row in rows]
                    table = LongTable(cells, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8edf4')),
                        ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#b6c2cf')),
                        ('VALIGN',(0,0),(-1,-1),'TOP'),
                        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
                    ]))
                    story.extend([table, Spacer(1,10)])
                else:
                    # Wide tables become readable records, retaining every cell.
                    for row in rows[1:]:
                        for label, cell in zip(header,row):
                            story.append(Paragraph(_inline(f'{label}: {cell}'),styles['body']))
                        story.append(Spacer(1,7))
                continue
        index += 1
        if not line:
            story.append(Spacer(1,5))
        elif line.startswith('```') or re.fullmatch(r'[-_]{3,}',line):
            continue
        elif re.match(r'^#{1,6}\s+',line):
            story.append(Paragraph(_inline(re.sub(r'^#{1,6}\s+','',line)),styles['heading']))
        elif re.match(r'^[-*•]\s+',line):
            story.append(Paragraph(_inline(re.sub(r'^[-*•]\s+','',line)),styles['bullet'],bulletText='•'))
        else:
            story.append(Paragraph(_inline(line),styles['body']))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('DentalSans',8)
        canvas.setFillColor(colors.HexColor('#596575'))
        canvas.drawString(38,22,'Dental AI Akademik')
        canvas.drawRightString(A4[0]-38,22,str(doc.page))
        canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    data = output.getvalue()
    if not data.startswith(b'%PDF-') or len(data) > 8*1024*1024:
        raise AcademicPDFError('PDF dosyası hazırlanamadı.')
    return data
