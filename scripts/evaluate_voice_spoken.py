#!/usr/bin/env python3
"""Synthetic Turkish topic-routing checks; not diagnosis or clinical validation.

Default: validate held-out fixture data and print counts, with no model/network.
--live: explicitly use the production core._understand extractor and configured
Claude review provider. Expectations are scored locally, never sent to the model.
No real patient data belongs in this fixture or in this command's output.
"""
import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import re
import sys

# Support direct invocation without installation or a modified PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.voice_exam_literature import TOPICS
from app.voice_exam_taxonomy import BRANCH_LABELS

FIXTURE_PATH = ROOT / 'tests' / 'fixtures' / 'voice_spoken_cases.json'


def known_topic_ids():
    return {topic for topic, _ in TOPICS}


def load_cases(path=FIXTURE_PATH):
    fixture = json.loads(Path(path).read_text(encoding='utf-8'))
    if fixture.get('synthetic') is not True or not isinstance(fixture.get('cases'), list):
        raise ValueError('invalid_synthetic_fixture')
    return fixture['cases']


def validate_cases(cases):
    known = known_topic_ids()
    seen, branches, topics = set(), set(), set()
    for case in cases:
        ident = case.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z0-9_-]+', ident) or ident in seen:
            raise ValueError('invalid_case_id')
        seen.add(ident)
        turns = case.get('dialogue')
        if not isinstance(turns, list) or not 2 <= len(turns) <= 12:
            raise ValueError('invalid_dialogue_length')
        for turn in turns:
            if not isinstance(turn, dict) or turn.get('speaker') not in {'Hasta', 'Hekim', 'Asistan', 'Ebeveyn'} or not isinstance(turn.get('text'), str) or not turn['text'].strip():
                raise ValueError('invalid_dialogue_turn')
        groups = case.get('required_any')
        forbidden = case.get('forbidden')
        if not isinstance(groups, list) or not isinstance(forbidden, list):
            raise ValueError('invalid_expectations')
        for group in groups:
            if not isinstance(group, list) or not group or any(not isinstance(topic, str) or topic not in known for topic in group):
                raise ValueError('invalid_required_topic')
            if set(group) <= set(forbidden):
                raise ValueError('contradictory_expectations')
            topics.update(group)
            # Supported legacy IDs are public phrases, not branch prefixes.
            branches.update(topic.split('.')[0] for topic in group if '.' in topic)
        if any(not isinstance(topic, str) or topic not in known for topic in forbidden):
            raise ValueError('invalid_forbidden_topic')
        for key in ('required_clinician_quotes', 'forbidden_clinician_quotes'):
            quotes = case.get(key, [])
            if not isinstance(quotes, list) or any(not isinstance(q, str) or not q.strip() or q not in dialogue_text(case) for q in quotes):
                raise ValueError('invalid_clinician_expectation')
        if set(case.get('required_clinician_quotes', [])) & set(case.get('forbidden_clinician_quotes', [])):
            raise ValueError('contradictory_clinician_expectations')
        if 'requires_uncertainty' in case and not isinstance(case['requires_uncertainty'], bool):
            raise ValueError('invalid_uncertainty_expectation')
    if not branches <= set(BRANCH_LABELS):
        raise ValueError('unknown_branch')
    return {'cases': len(cases), 'branches': len(branches), 'expected_topics': len(topics),
            'legacy_expected_topics': sum('.' not in topic for topic in topics),
            'required_groups': sum(len(case['required_any']) for case in cases),
            'uncertainty_cases': sum(bool(case.get('requires_uncertainty')) for case in cases)}


def dialogue_text(case):
    return '\n'.join(f"{turn['speaker']}: {turn['text']}" for turn in case['dialogue'])


def score_case(case, result):
    """Exact ID scoring of returned routes; quote checks do not prove relevance.

    Required groups are satisfied only by known IDs with a nonempty, contiguous
    verbatim quote from the supplied transcript. This is grounding, not clinical entailment.
    """
    known = known_topic_ids()
    grounded, selected = set(), set()
    valid, invalid, unknown = 0, 0, 0
    failures = set()
    if not isinstance(result, dict):
        result = {}
        failures.add('invalid_result')
    rows = result.get('literature_topics', [])
    if not isinstance(rows, list):
        rows = []
        failures.add('invalid_result')
    transcript = dialogue_text(case)
    def anchored(quote):
        return isinstance(quote, str) and bool(quote.strip()) and quote in transcript
    for row in rows:
        if not isinstance(row, dict):
            failures.add('invalid_result')
            continue
        topic = row.get('topic')
        if not isinstance(topic, str) or topic not in known:
            unknown += 1
        else:
            selected.add(topic)
        if anchored(row.get('quote')):
            valid += 1
            if isinstance(topic, str) and topic in known:
                grounded.add(topic)
        else:
            invalid += 1
    groups = case['required_any']
    matched = sum(bool(grounded.intersection(group)) for group in groups)
    forbidden = len(selected.intersection(case['forbidden']))
    # Generic uncertainty/normalizer warnings do not prove ambiguity recognition.
    uncertainty = False
    questions = result.get('follow_up_questions', [])
    if isinstance(questions, list):
        uncertainty |= any(isinstance(row, dict) and anchored(row.get('quote')) and
                           isinstance(row.get('question'), str) and bool(row['question'].strip()) and
                           row.get('priority') == 'CLARIFY_NOW' for row in questions)
    clinician_quotes = set()
    for item in result.get('communication', []) if isinstance(result.get('communication', []), list) else []:
        if isinstance(item, dict) and item.get('category') == 'CLINICAL_STATEMENT':
            if anchored(item.get('quote')):
                clinician_quotes.add(item['quote'])
            else:
                failures.add('invalid_clinician_quote')
    if set(case.get('required_clinician_quotes', [])) - clinician_quotes:
        failures.add('missing_clinician_statement')
    if any(quote in forbidden or forbidden in quote for quote in clinician_quotes
           for forbidden in case.get('forbidden_clinician_quotes', [])):
        failures.add('forbidden_clinician_statement')
    if matched != len(groups):
        failures.add('missing_required_group')
    if forbidden:
        failures.add('forbidden_topic')
    if invalid:
        failures.add('invalid_quote_anchor')
    if unknown:
        failures.add('unknown_topic_id')
    if case.get('requires_uncertainty') and not uncertainty:
        failures.add('missing_uncertainty')
    return {'case_id': case['id'], 'passed': not failures,
            'topic_group_recall': matched / len(groups) if groups else 1.0,
            'matched_groups': matched, 'required_groups': len(groups),
            'forbidden_hits': forbidden,
            'unscored_extra_topics': len(selected - {topic for group in groups for topic in group} - set(case['forbidden'])),
            'valid_quote_anchors': valid,
            'invalid_quote_anchors': invalid, 'unknown_ids': unknown,
            'failure_categories': sorted(failures)}



def evaluate_repeated(cases, extract, *, repeat=1):
    """Measure grounded routing repeatability, not clinical safety or entailment."""
    if type(repeat) is not int or not 1 <= repeat <= 10:
        raise ValueError('invalid_repeat')
    reports, calls = [], 0
    stop = False
    for case in cases:
        scores, routes = [], []
        for attempt in range(repeat):
            calls += 1
            try:
                result = extract(dialogue_text(case), {})
                scores.append(score_case(case, result))
                transcript = dialogue_text(case)
                routes.append(tuple(sorted({row['topic'] for row in result.get('literature_topics', [])
                    if isinstance(row, dict) and row.get('topic') in known_topic_ids()
                    and isinstance(row.get('quote'), str) and row['quote'].strip() and row['quote'] in transcript})))
            except Exception:
                scores.append({'passed': False, 'failure_categories': ['provider_or_extraction_failure']})
                stop = True
                break  # no automatic retry after a provider/extraction failure
        successful = [row for row in scores if 'topic_group_recall' in row]
        counts = Counter(routes)
        reports.append({'case_id': case['id'], 'attempts': len(scores),
            'passed_attempts': sum(row['passed'] for row in scores),
            'all_attempts_passed': len(scores) == repeat and all(row['passed'] for row in scores),
            'completed_all_repeats': len(scores) == repeat and not stop,
            'distinct_grounded_routes': len(counts),
            'route_consistency': max(counts.values()) / len(routes) if routes else None,
            'required_group_recall': sum(row['matched_groups'] for row in successful) / sum(row['required_groups'] for row in successful)
                if successful and sum(row['required_groups'] for row in successful) else None,
            'forbidden_hits': sum(row['forbidden_hits'] for row in successful),
            'runs': scores})
        if stop:
            break
    return {'model_calls': calls, 'cases': len(reports), 'repeat': repeat,
            'all_cases_passed': len(reports) == len(cases) and all(row['all_attempts_passed'] for row in reports),
            'results': reports}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=FIXTURE_PATH, help='Synthetic case JSON; default is the original spoken fixture.')
    parser.add_argument('--live', action='store_true', help='Explicitly call the production extractor (provider cost applies).')
    parser.add_argument('--limit', type=int, default=5, help='Maximum live cases; default 5.')
    parser.add_argument('--case', action='append', default=[], help='Select a case ID; repeat to select several.')
    parser.add_argument('--repeat', type=int, default=1, help='Independent calls per case (1-10); not retries.')
    parser.add_argument('--max-calls', type=int, default=25, help='Explicit live-call budget (1-500), default 25.')
    args = parser.parse_args(argv)
    def emit(data):
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    try:
        cases = load_cases(args.fixture)
        inventory = validate_cases(cases)
    except (ValueError, TypeError, KeyError, OSError):
        emit({'failure_categories': ['invalid_fixture']})
        return 2
    if args.limit < 1:
        emit({'failure_categories': ['invalid_limit']})
        return 2
    if not 1 <= args.repeat <= 10 or not 1 <= args.max_calls <= 500:
        emit({'failure_categories': ['invalid_repeat_or_budget'], 'model_calls': 0})
        return 2
    selectors = set(args.case)
    if selectors - {case['id'] for case in cases}:
        emit({'failure_categories': ['unknown_case_selector']})
        return 2
    selected = [case for case in cases if not selectors or case['id'] in selectors]
    if not args.live:
        emit({'mode': 'offline_inventory', **inventory, 'selected_cases': len(selected),
              'model_calls': 0})
        return 0
    if len(selected[:args.limit]) * args.repeat > args.max_calls:
        emit({'failure_categories': ['call_budget_exceeded'], 'model_calls': 0})
        return 2
    key = (os.environ.get('ANTHROPIC_API_KEY') or '').strip()
    # Require explicit configuration rather than silently assuming a model.
    model = (os.environ.get('VOICE_EXAM_CLAUDE_MODEL') or '').strip()
    if not key or not re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model):
        emit({'mode': 'live', 'failure_categories': ['missing_provider_configuration'], 'model_calls': 0})
        return 2
    from app import voice_exam_core as core
    # Never output raw dialogues/provider bodies; restore caller logging state.
    previous_logging = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        report = evaluate_repeated(selected[:args.limit], core._understand, repeat=args.repeat)
    finally:
        logging.disable(previous_logging)
    emit({'mode': 'live', **report})
    return 0 if report['all_cases_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
