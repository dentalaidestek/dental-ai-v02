#!/usr/bin/env python3
"""Synthetic Turkish topic-routing checks; not diagnosis or clinical validation.

Default: validate held-out fixture data and print counts, with no model/network.
--live: explicitly use the production core._understand extractor and configured
Claude review provider. Expectations are scored locally, never sent to the model.
No real patient data belongs in this fixture or in this command's output.
"""
import argparse
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
        if not isinstance(turns, list) or not 2 <= len(turns) <= 6:
            raise ValueError('invalid_dialogue_length')
        for turn in turns:
            if not isinstance(turn, dict) or turn.get('speaker') not in {'Hasta', 'Hekim', 'Ebeveyn'} or not isinstance(turn.get('text'), str) or not turn['text'].strip():
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
            branches.update(topic.split('.')[0] for topic in group)
        if any(not isinstance(topic, str) or topic not in known for topic in forbidden):
            raise ValueError('invalid_forbidden_topic')
        if 'requires_uncertainty' in case and not isinstance(case['requires_uncertainty'], bool):
            raise ValueError('invalid_uncertainty_expectation')
    if not branches <= set(BRANCH_LABELS):
        raise ValueError('unknown_branch')
    return {'cases': len(cases), 'branches': len(branches), 'expected_topics': len(topics),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly call the production extractor (provider cost applies).')
    parser.add_argument('--limit', type=int, default=5, help='Maximum live cases; default 5.')
    parser.add_argument('--case', action='append', default=[], help='Select a case ID; repeat to select several.')
    args = parser.parse_args(argv)
    def emit(data):
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    try:
        cases = load_cases()
        inventory = validate_cases(cases)
    except (ValueError, TypeError, KeyError, OSError):
        emit({'failure_categories': ['invalid_fixture']})
        return 2
    if args.limit < 1:
        emit({'failure_categories': ['invalid_limit']})
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
    key = (os.environ.get('ANTHROPIC_API_KEY') or '').strip()
    # Require explicit configuration rather than silently assuming a model.
    model = (os.environ.get('VOICE_EXAM_CLAUDE_MODEL') or '').strip()
    if not key or not re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model):
        emit({'mode': 'live', 'failure_categories': ['missing_provider_configuration'], 'model_calls': 0})
        return 2
    from app import voice_exam_core as core
    reports = []
    # Provider errors and logging may contain details; output fixed categories only.
    logging.disable(logging.CRITICAL)
    for case in selected[:args.limit]:
        try:
            result = core._understand(dialogue_text(case), {})
            reports.append(score_case(case, result))
        except Exception:
            reports.append({'case_id': case['id'], 'passed': False,
                            'failure_categories': ['provider_or_extraction_failure']})
            break  # no retry, model/key lookup, or provider fallback
    emit({'mode': 'live', 'cases': len(reports), 'passed': sum(row['passed'] for row in reports),
          'results': reports})
    return 0 if all(row['passed'] for row in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
