"""Long-answer recovery regressions; no live provider or paid calls."""
import ast
from io import BytesIO
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.academic_long_answer import (
    AUTO_PDF_CHARS, MAX_ANSWER_CHARS, MAX_CONTINUATIONS, LONG_PDF_NOTICE,
    LongAnswerError, automatic_pdf, stream_complete_answer,
)
from app.academic_pdf import pdf_artifact, pdf_requested, render_pdf


def retrieval(**task):
    return SimpleNamespace(evidence_sufficient=True, study_task=task)


class Provider:
    def __init__(self, *segments):
        self.segments = iter(segments)
        self.calls = []

    def generate_stream(self, **options):
        self.calls.append(options)
        chunks, finish = next(self.segments)
        yield from chunks
        self.last_finish_reason = finish


def run(provider, result, **kwargs):
    return ''.join(stream_complete_answer(provider, dict(
        prompt='Kaynak: hastalık ve risk iletişimi, s. 1-4', model='test',
        system_prompt='Yalnız kaynaklardan cevapla.', attachments=[{'label': 'kaynak'}],
        history=[], max_output_tokens=7000), result, **kwargs))


class LongAnswerTests(unittest.TestCase):
    def test_short_response_keeps_one_call_and_text(self):
        p = Provider((['Kısa ', 'cevap.'], 'STOP'))
        r = retrieval()
        self.assertEqual(run(p, r), 'Kısa cevap.')
        self.assertEqual(len(p.calls), 1)
        self.assertFalse(automatic_pdf('Kısa cevap.', r))

    def test_screenshot_midword_resumes_with_identical_sources(self):
        p = Provider((['## Multimorbidite\nAçıklama.\n## PERİODONTAL HAST'], 'MAX_TOKENS'),
                     (['ALIK\nRisk iletişimi. [Not s. 4]'], 'STOP'))
        r = retrieval()
        answer = run(p, r)
        self.assertIn('PERİODONTAL HASTALIK', answer)
        self.assertTrue(answer.endswith('[Not s. 4]'))
        self.assertTrue(automatic_pdf(answer, r))
        self.assertEqual(p.calls[0]['attachments'], p.calls[1]['attachments'])
        self.assertIn(p.calls[0]['prompt'], p.calls[1]['prompt'])
        self.assertEqual(p.calls[1]['max_output_tokens'], 16000)

    def test_thinking_only_stop_gets_bounded_larger_budget(self):
        p = Provider(([], 'MAX_TOKENS'), (['Tamamlanan cevap.'], 'STOP'))
        self.assertEqual(run(p, retrieval()), 'Tamamlanan cevap.')

    def test_exact_repeated_tail_not_duplicated(self):
        tail = 'Risk iletişimi hasta odaklı yapılmalıdır.\n'
        p = Provider((['## Başlangıç\n' + tail], 'MAX_TOKENS'),
                     ([tail[:10], tail[10:] + '## Son başlık\nTamamlandı.'], 'STOP'))
        answer = run(p, retrieval())
        self.assertEqual(answer.count(tail), 1)
        self.assertTrue(answer.endswith('Tamamlandı.'))

    def test_repeated_truncation_is_bounded_and_never_succeeds(self):
        p = Provider(*[([str(i)], 'MAX_TOKENS') for i in range(MAX_CONTINUATIONS + 1)])
        with self.assertRaisesRegex(LongAnswerError, 'eksik PDF kaydedilmedi'):
            run(p, retrieval())
        self.assertEqual(len(p.calls), MAX_CONTINUATIONS + 1)

    def test_empty_continuation_is_failure(self):
        p = Provider((['Başlangıç'], 'MAX_TOKENS'), ([], 'STOP'))
        with self.assertRaises(LongAnswerError):
            run(p, retrieval())

    def test_structured_json_is_never_concatenated(self):
        p = Provider((['{"questions": ['], 'MAX_TOKENS'))
        with self.assertRaises(LongAnswerError):
            run(p, retrieval(), allow_continuation=False)
        self.assertEqual(len(p.calls), 1)

    def test_oversized_response_is_not_silently_clipped(self):
        p = Provider((['x' * (MAX_ANSWER_CHARS + 1)], 'STOP'))
        with self.assertRaisesRegex(LongAnswerError, 'eksik PDF kaydedilmedi'):
            run(p, retrieval())

    def test_long_complete_answer_automatically_uses_pdf(self):
        r = retrieval()
        self.assertTrue(pdf_requested(None, r, 'x' * AUTO_PDF_CHARS))
        self.assertFalse(pdf_requested(None, r, 'x' * (AUTO_PDF_CHARS - 1)))
        r.evidence_sufficient = False
        self.assertFalse(pdf_requested(None, r, 'x' * AUTO_PDF_CHARS))

    def test_explicit_pdf_request_still_works(self):
        plan = SimpleNamespace(output_format='pdf', operation='answer')
        self.assertTrue(pdf_requested(SimpleNamespace(plan=plan), retrieval(), 'Kısa cevap'))

    def test_owned_pdf_link_carries_reason(self):
        artifact = pdf_artifact(3, 42, 'Perio didem', automatic=True)
        self.assertEqual(artifact['url'], '/notes/courses/3/ai/messages/42/pdf')
        self.assertEqual(artifact['reason'], 'long_answer')
        self.assertEqual(pdf_artifact(3, 42, 'Perio')['reason'], 'requested')

    def test_rendering_failure_is_not_reported_as_ready(self):
        # Exercise the actual endpoint preparation function without importing
        # production database startup or connecting to external services.
        tree = ast.parse(Path('app/main.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == '_prepare_study_pdf')
        scope = {'logger': logging.getLogger('test'), 'StudyAIError': ValueError}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<prepare-pdf>', 'exec'), scope)
        with patch('app.academic_pdf.render_pdf', side_effect=RuntimeError('render failure')):
            with self.assertRaisesRegex(ValueError, 'PDF hazırlanamadı'):
                scope['_prepare_study_pdf']('Perio', 'x' * AUTO_PDF_CHARS, None, retrieval())

    def test_notice_survives_reload(self):
        from jinja2 import Template
        html = Path('app/templates/notes_ai.html').read_text()
        start = html.index("{% if msg.role == 'ASSISTANT' and msg.mode and msg.mode.endswith('_PDF') %}")
        end = html.index('{% endif %}', start) + len('{% endif %}')
        rendered = Template(html[start:end]).render(
            msg=SimpleNamespace(role='ASSISTANT', mode='RAG_V2_HYBRID_STREAM_LONG_PDF',
                                id=42, content='long hidden prose'),
            course=SimpleNamespace(id=3, title='Perio didem'))
        self.assertIn(LONG_PDF_NOTICE, rendered)
        self.assertIn('/messages/42/pdf', rendered)
        self.assertNotIn('long hidden prose', rendered)

    def test_pdf_contains_first_and_last_sections_with_turkish(self):
        from pypdf import PdfReader
        answer = ('## İlk başlık: şeker hastalığı\n'
                  + ('Periodontal hastalık ve risk iletişimi. [Not s. 4]\n' * 260)
                  + '\n## Son başlık: öğrencinin özeti\nBütün başlıklar tamamlandı.')
        data = render_pdf('Perio didem', answer)
        reader = PdfReader(BytesIO(data))
        self.assertGreater(len(reader.pages), 1)
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('İlk başlık: şeker hastalığı', text)
        self.assertIn('Son başlık: öğrencinin özeti', text)
        self.assertIn('Bütün başlıklar tamamlandı.', text)
        self.assertEqual(text.count('[Not s. 4]'), 260)


if __name__ == '__main__':
    unittest.main()
