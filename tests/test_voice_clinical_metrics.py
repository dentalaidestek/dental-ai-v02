"""Synthetic adjudication records test arithmetic, not clinical truth."""
import copy
import pytest


def dataset():
    return {'repeats':2,'cases':[
      {'id':'positive','approval_status':'approved','approved_by':'synthetic-test-reviewer','approved_at':'2026-10-29',
       'labels_complete':True,'required_alert_ids':['risk_a'],'critical_alert_ids':['risk_a']},
      {'id':'negative','approval_status':'approved','approved_by':'synthetic-test-reviewer','approved_at':'2026-10-29',
       'labels_complete':True,'required_alert_ids':[],'critical_alert_ids':[]}],
      'runs':[
       {'case_id':'positive','repeat':1,'status':'reviewed','adjudicated_by':'synthetic-test-reviewer','adjudicated_at':'2026-10-29','observed_alert_ids':['risk_a','unrelated']},
       {'case_id':'positive','repeat':2,'status':'failed'},
       {'case_id':'negative','repeat':1,'status':'reviewed','adjudicated_by':'synthetic-test-reviewer','adjudicated_at':'2026-10-29','observed_alert_ids':[]},
       {'case_id':'negative','repeat':2,'status':'reviewed','adjudicated_by':'synthetic-test-reviewer','adjudicated_at':'2026-10-29','observed_alert_ids':['unrelated']}]}


def test_provider_failure_remains_end_to_end_miss_and_false_alarms_have_explicit_denominators():
    from scripts.score_voice_clinical_review import score_review
    report=score_review(dataset())
    assert (report['true_positive_alerts'],report['false_positive_alerts'],report['missed_expected_alerts'])==(1,2,1)
    assert report['end_to_end_sensitivity']==0.5
    assert report['reviewed_alert_recall']==1.0
    assert report['negative_run_false_positive_rate']==0.5
    assert report['reviewed_negative_runs']==2
    assert report['critical_misses']==1 and report['failed_runs']==1
    assert not report['coverage_complete']


def test_unreviewed_and_unrecorded_runs_are_not_treated_as_clean_negative_results():
    from scripts.score_voice_clinical_review import score_review
    data=dataset();data['runs']=data['runs'][:1]+[{'case_id':'negative','repeat':1,'status':'unreviewed'}]
    report=score_review(data)
    assert report['unreviewed_runs']==1 and report['unrecorded_runs']==2
    assert report['end_to_end_sensitivity'] is None
    assert report['reviewed_negative_runs']==0
    assert report['negative_run_false_positive_rate'] is None
    assert not report['coverage_complete']


def test_unapproved_case_labels_cannot_produce_a_clinical_score():
    from scripts.score_voice_clinical_review import score_review
    data=dataset();data['cases'][0]['approval_status']='draft'
    with pytest.raises(ValueError):score_review(data)


def test_duplicate_runs_cannot_inflate_clinical_performance():
    from scripts.score_voice_clinical_review import score_review
    data=dataset();data['runs'].append(copy.deepcopy(data['runs'][0]))
    with pytest.raises(ValueError):score_review(data)


def test_blank_review_identity_and_unreviewed_model_labels_cannot_count_as_adjudicated():
    from scripts.score_voice_clinical_review import score_review
    data=dataset();data['runs'][0]['adjudicated_by']='  '
    with pytest.raises(ValueError):score_review(data)
