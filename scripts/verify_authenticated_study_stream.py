"""Exercise the authenticated study UI, verifying real NDJSON answer completion.

Requires Playwright and an authorized browser storage-state file. Never prints
cookies/tokens. Writes a report containing prompts, timing and answer previews.
Existing chat history is preserved; these real requests append test messages.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright


FAILURE_TEXT = (
    'Bu bilgi yüklediğin ders notlarında bulunmuyor',
    'Bu soruyla ilişkilendirilebilecek ders notu bulunamadı',
    'yeterli not içeriğini henüz eşleştiremedim',
    'notların tümünden güvenilir içerik hazırlayamadım',
    'Hangi konuyu veya soruyu kastettiğini belirtir misin',
    'Hangi soruyu yanıtladığını belirtir misin',
    'Bahsettiğin soruyu son soru listesinde bulamadım',
    'Hangi konuyu kastettiğini netleştirelim',
    'yeterli kaynak bulamadım',
)


async def verify(args):
    report = {'scope': 'authenticated browser UI /ask-stream', 'steps': [], 'passed': False}
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, executable_path=args.chromium)
            context = await browser.new_context(storage_state=str(args.storage_state))
            page = await context.new_page()
            await page.add_init_script("""(() => {
              const original = window.fetch;
              window.studyStreamTimings = [];
              window.fetch = async (...args) => {
                const started = performance.now();
                const response = await original(...args);
                if (String(args[0]).endsWith('/ask-stream') && response.body) {
                  const record = {firstDeltaMs: null, doneMs: null};
                  window.studyStreamTimings.push(record);
                  (async () => {
                    const reader = response.clone().body.getReader();
                    const decoder = new TextDecoder(); let buffer = '';
                    while (true) {
                      const part = await reader.read();
                      buffer += decoder.decode(part.value || new Uint8Array(), {stream: !part.done});
                      const lines = buffer.split('\\n'); buffer = lines.pop();
                      for (const line of lines) {
                        if (!line.trim()) continue;
                        const event = JSON.parse(line);
                        if (event.type === 'delta' && record.firstDeltaMs === null)
                          record.firstDeltaMs = performance.now() - started;
                        if (event.type === 'done') record.doneMs = performance.now() - started;
                      }
                      if (part.done) break;
                    }
                  })().catch(() => {});
                }
                return response;
              };
            })();""")
            await page.goto(f'{args.origin.rstrip("/")}/notes/courses/{args.course_id}/ai',
                            wait_until='domcontentloaded')
            if '/login' in page.url or await page.locator('#studyChatInput').count() != 1:
                raise RuntimeError('Authorized login session is unavailable; no test requests sent.')
            await page.locator('#studySendButton').wait_for(state='visible')
            steps = [
                {'preset': 'Özetle'}, {'preset': 'Bana Öğret'},
                {'message': 'Bu çok yüzeysel her başlığı açıkla'},
                {'message': 'Diğer başlıklar nerede'},
                {'message': 'Hoca nerden sorabilir'},
                {'message': 'Bence burdan gelmez hocanın özellikle vurguladığı işaretli yerler var mı'},
                {'message': 'Her başlığı tek bir oaragrafla anlat'},
                {'message': 'Kral sen dalga mı geçiyorsun'},
                {'message': 'Başlıkları atlama, her başlığı tek bir paragrafla anlat'},
                {'preset': 'Soru Hazırla', 'question_count': 20, 'hide_answer_key': True},
                {'message': 'Bu notlardan sınava çalışalım, önemli yerleri mantığıyla anlat.'},
                {'message': 'Bana bu ders notlarından bir soru sor ve cevabımı bekle.'},
                {'message': 'Cevabım A'},
                {'message': 'Bir önceki soruyu neden öyle cevapladığımızı daha basit anlat.'},
                {'message': 'Ders notlarından iki soru hazırla; cevap anahtarını gösterme.'},
                {'message': 'Cevaplarım 1A, 2B'},
            ]
            if args.scenarios:
                steps = json.loads(args.scenarios.read_text())
            for step in steps:
                started = time.monotonic()
                async with page.expect_response(lambda response:
                        response.request.method == 'POST' and response.url.endswith('/ask-stream'),
                        timeout=args.timeout_ms) as pending:
                    if 'preset' in step:
                        await page.get_by_role('button', name=step['preset'], exact=True).click()
                    else:
                        await page.locator('#studyChatInput').fill(step['message'])
                        await page.locator('#studySendButton').click()
                response = await pending.value
                await asyncio.wait_for(response.finished(), args.timeout_ms / 1000)
                if response.status != 200:
                    raise RuntimeError(f'/ask-stream HTTP {response.status}')
                events = [json.loads(line) for line in (await response.body()).decode().splitlines()
                          if line.strip()]
                answer = ''.join(event.get('text', '') for event in events if event.get('type') == 'delta')
                errors = [event.get('error') for event in events if event.get('type') == 'error']
                done = any(event.get('type') == 'done' for event in events)
                clarification = any(message.casefold() in answer.casefold() for message in FAILURE_TEXT)
                success = done and bool(answer.strip()) and not errors and (
                    not clarification or bool(step.get('allow_clarification')))
                required = step.get('answer_contains', [])
                success = success and all(term.casefold() in answer.casefold() for term in required)
                question_numbers = [int(number) for number in re.findall(
                    r'(?im)^\s*(?:\*\*)?Soru\s+(\d+)\b', answer)]
                if step.get('question_count'):
                    success = success and question_numbers == list(range(1, int(step['question_count']) + 1))
                answer_key_visible = bool(re.search(
                    r'(?im)^\s*(?:#+\s*|\*\*)?(?:cevap|yanıt|yanit)\s+anahtar(?:ı|i)\s*[:\n]'
                    r'|^\s*(?:[-*]\s*)?(?:doğru\s+cevap|dogru\s+cevap|cevap|yanıt|yanit)\s*:\s*[A-E]\b', answer))
                if step.get('hide_answer_key'):
                    success = success and not answer_key_visible
                await page.wait_for_function('!document.querySelector("#studySendButton").disabled',
                                             timeout=args.timeout_ms)
                visible_text = await page.locator('.study-chat-message.assistant').all_inner_texts()
                marker_visible = any('ACADEMIC_Q_CURSOR' in text for text in visible_text)
                success = success and not marker_visible
                timings = await page.evaluate('window.studyStreamTimings')
                report['steps'].append({**step, 'http_status': response.status, 'done': done,
                    'delta_count': sum(event.get('type') == 'delta' for event in events),
                    'elapsed_ms': round((time.monotonic() - started) * 1000),
                    'stream_timing': timings[-1] if timings else None,
                    'answer_preview': answer[:1200], 'errors': errors,
                    'internal_marker_visible': marker_visible,
                    'question_numbers': question_numbers,
                    'answer_key_visible': answer_key_visible, 'passed': success})
                if not success:
                    raise RuntimeError('Stream did not complete with an answer; see step report.')
            report['passed'] = True
            await browser.close()
    except Exception as error:
        report['failure'] = f'{type(error).__name__}: {error}'
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://dentalai.tr')
    parser.add_argument('--course-id', type=int, required=True)
    parser.add_argument('--storage-state', type=Path, required=True)
    parser.add_argument('--chromium', default=None)
    parser.add_argument('--scenarios', type=Path)
    parser.add_argument('--timeout-ms', type=int, default=180000)
    parser.add_argument('--report', type=Path, default=Path('artifacts/browser-study-stream.json'))
    args = parser.parse_args()
    if not args.storage_state.is_file():
        parser.error('An authorized storage-state file is required.')
    raise SystemExit(0 if asyncio.run(verify(args)) else 1)


if __name__ == '__main__':
    main()
