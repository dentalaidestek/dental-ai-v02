#!/usr/bin/env python3
"""Score clinician-adjudicated alert IDs offline; never classify clinical prose.

Human reviewers map actual outputs to exhaustive, approved case labels. Approval
metadata is an audit declaration, not authentication of a reviewer's credentials.
Only aggregate counts are printed; no provider calls, case text or patient data.
"""
import argparse
import json
from pathlib import Path


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('invalid_review_record')
    return value


def _ids(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('invalid_alert_ids')
    result = {_name(item) for item in value}
    if len(result) != len(value):
        raise ValueError('duplicate_alert_id')
    return result


def score_review(data):
    if not isinstance(data, dict):
        raise ValueError('invalid_dataset')
    repeats = data.get('repeats', 5)
    cases, runs = data.get('cases'), data.get('runs')
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError('invalid_repeat')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000 or not isinstance(runs, list) or len(runs) > 10000:
        raise ValueError('invalid_dataset_size')
    labels = {}
    for case in cases:
        if not isinstance(case, dict) or case.get('approval_status') != 'approved' or case.get('labels_complete') is not True:
            raise ValueError('unapproved_or_incomplete_labels')
        ident = _name(case.get('id'))
        _name(case.get('approved_by')); _name(case.get('approved_at'))
        expected, critical = _ids(case.get('required_alert_ids')), _ids(case.get('critical_alert_ids', []))
        if ident in labels or not critical <= expected:
            raise ValueError('invalid_case_labels')
        labels[ident] = (expected, critical)
    tp = fp = reviewed_fn = failed_fn = critical_misses = reviewed = failed = unreviewed = 0
    negative_runs = negative_false_positive_runs = 0
    seen = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError('invalid_run')
        case_id, index = run.get('case_id'), run.get('repeat')
        if not isinstance(case_id, str) or case_id not in labels or type(index) is not int or not 1 <= index <= repeats:
            raise ValueError('unknown_case_or_repeat')
        key = (case_id, index)
        if key in seen:
            raise ValueError('duplicate_run')
        seen.add(key)
        expected, critical = labels[case_id]
        status = run.get('status')
        if status == 'failed':
            failed += 1
            failed_fn += len(expected)
            critical_misses += len(critical)
        elif status == 'unreviewed':
            unreviewed += 1  # unknown output is not a negative clinical result
        elif status == 'reviewed':
            _name(run.get('adjudicated_by')); _name(run.get('adjudicated_at'))
            observed = _ids(run.get('observed_alert_ids'))
            reviewed += 1
            tp += len(expected & observed)
            fp += len(observed - expected)
            reviewed_fn += len(expected - observed)
            critical_misses += len(critical - observed)
            if not expected:
                negative_runs += 1
                negative_false_positive_runs += bool(observed)
        else:
            raise ValueError('unknown_run_status')
    missing = len(labels) * repeats - len(seen)
    missed = reviewed_fn + failed_fn
    return {'cases': len(labels), 'required_repeats': repeats, 'recorded_runs': len(seen),
        'reviewed_runs': reviewed, 'failed_runs': failed, 'unreviewed_runs': unreviewed, 'unrecorded_runs': missing,
        'true_positive_alerts': tp, 'false_positive_alerts': fp,
        'missed_expected_alerts': missed, 'reviewed_missed_alerts': reviewed_fn,
        'provider_failure_missed_alerts': failed_fn, 'critical_misses': critical_misses,
        'end_to_end_sensitivity': tp / (tp + missed) if tp + missed and not (missing or unreviewed) else None,
        'reviewed_alert_recall': tp / (tp + reviewed_fn) if tp + reviewed_fn else None,
        'alert_precision': tp / (tp + fp) if tp + fp else None,
        'reviewed_negative_runs': negative_runs, 'negative_runs_with_false_alerts': negative_false_positive_runs,
        'negative_run_false_positive_rate': negative_false_positive_runs / negative_runs if negative_runs else None,
        'coverage_complete': not (missing or failed or unreviewed),
        'notice': 'Human-adjudicated IDs only; unreviewed/unrecorded outcomes excluded from ratios and reported separately. Not a clinical readiness certificate.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('dataset_too_large')
        report = score_review(json.loads(args.file.read_text(encoding='utf-8')))
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({'failure_categories': ['invalid_or_unapproved_review_dataset'], 'model_calls': 0}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report['coverage_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
