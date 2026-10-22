import importlib.util
import json
from pathlib import Path

import pytest

from app import voice_exam_drugs as drugs


def importer():
    spec = importlib.util.spec_from_file_location('voice_drug_importer', 'scripts/import_voice_drug_labels.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


XML = b'''<document xmlns="urn:hl7-org:v3"><setId root="11111111-1111-1111-1111-111111111111"/>
<title>TEST TABLET</title><effectiveTime value="20261022"/><versionNumber value="2"/>
<component><manufacturedProduct><name>TESTDRUG</name></manufacturedProduct></component>
<component><section><code code="34073-7"/><title>DRUG INTERACTIONS</title><text>
<table><tbody><tr><td>OTHERDRUG</td><td>Requires clinician assessment.</td></tr></tbody></table>
</text></section></component></document>'''


def test_import_preserves_interaction_row_identity_version_and_source():
    record = importer().parse_spl(XML)
    assert record['jurisdiction'] == 'US' and record['version'] == '2'
    assert record['effective_date'] == '20261022'
    assert record['sections'][0]['paragraphs'] == ['OTHERDRUG Requires clinician assessment.']
    assert record['url'].startswith('https://dailymed.nlm.nih.gov/')


def test_import_rejects_entities():
    with pytest.raises(ValueError, match='Unsafe'):
        importer().parse_spl(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + XML)


def test_local_drug_matching_is_token_bound_and_does_not_send_patient_query(tmp_path, monkeypatch):
    record = importer().parse_spl(XML, ['testdrug'])
    path = tmp_path / 'corpus.jsonl'; path.write_text(json.dumps(record) + '\n')
    monkeypatch.setenv('VOICE_EXAM_DRUG_CORPUS', str(path))
    assert drugs.retrieve_drugs('testdrug ve klinik bağlam')[0]['matched_aliases']
    assert drugs.retrieve_drugs('notestdrugprefix') == []
    assert drugs.retrieve_drugs('tamamen bilinmeyen ilaç') == []


def test_operator_corpus_cannot_introduce_unapproved_source_url(tmp_path, monkeypatch):
    record = importer().parse_spl(XML); record['url'] = 'http://127.0.0.1/secrets'
    path = tmp_path / 'corpus.jsonl'; path.write_text(json.dumps(record) + '\n')
    monkeypatch.setenv('VOICE_EXAM_DRUG_CORPUS', str(path))
    with pytest.raises(ValueError, match='Unapproved'): drugs.retrieve_drugs('TESTDRUG')


def test_bundled_real_labels_have_source_version_and_actual_sections(monkeypatch):
    monkeypatch.delenv('VOICE_EXAM_DRUG_CORPUS', raising=False)
    records = [json.loads(line) for line in Path(drugs.DEFAULT_CORPUS).read_text().splitlines()]
    assert len(records) == 8
    for item in records:
        assert item['version'] and item['effective_date'] and item['sections']
        assert all(section['paragraphs'] for section in item['sections'])
    assert drugs.retrieve_drugs('amoksisilin')[0]['jurisdiction'] == 'US'
