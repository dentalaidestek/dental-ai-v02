"""Offline contract tests for the fixed multidisciplinary professional library."""
from urllib.parse import urlsplit


def test_fixed_documents_have_safe_unique_urls_and_clinical_terms():
    from app.voice_exam_professional import DOCUMENTS
    assert 20 <= len(DOCUMENTS) <= 35
    assert len({d[0] for d in DOCUMENTS}) == len(DOCUMENTS)
    assert len({d[3] for d in DOCUMENTS}) == len(DOCUMENTS)
    for ident, institution, title, url, triggers, terms in DOCUMENTS:
        parsed = urlsplit(url)
        assert parsed.scheme == 'https' and parsed.hostname
        assert not parsed.query and not parsed.fragment and not url.lower().endswith('.pdf')
        assert institution and title and ident
        assert isinstance(triggers, tuple) and triggers
        assert isinstance(terms, tuple) and len(terms) >= 2
        assert all(term == term.casefold() and len(term) >= 3 for term in terms)
    assert len({d[1] for d in DOCUMENTS}) >= 5


def test_every_new_specialty_topic_has_only_known_documents():
    from app.voice_exam_professional import DOCUMENTS, TOPIC_DOCUMENTS
    expected = {
        'prosth': 'general fixed removable occlusion cementation materials zirconia glass_ceramic metal_ceramic veneers',
        'ortho': 'general appliances retention resorption',
        'perio': 'general surgery peri_implant regeneration',
        'pediatric': 'general pulp trauma behavior occlusion development',
        'surgery': 'general third_molar bleeding nerve sinus',
        'oral_medicine': 'general cancer saliva infection',
        'restorative': 'general adhesion wear hypersensitivity esthetics materials',
        'prevention': 'general diet', 'imaging': 'general',
        'anesthesia': 'general sedation', 'emergencies': 'general',
        'special_care': 'general', 'implant': 'general prosthesis components', 'endo': 'general cracked_tooth post_core irrigation obturation', 'orofacial_pain': 'sleep',
    }
    assert set(TOPIC_DOCUMENTS) == {f'{branch}.{topic}' for branch, topics in expected.items() for topic in topics.split()} | {'oral mucosal lesion diagnosis'}
    ids = {d[0] for d in DOCUMENTS}
    for topic, documents in TOPIC_DOCUMENTS.items():
        assert isinstance(documents, tuple) and documents, topic
        assert set(documents) <= ids
        assert len(set(documents)) == len(documents)


def test_specialty_documents_are_selected_for_their_actual_subject():
    from app.voice_exam_professional import DOCUMENTS, TOPIC_DOCUMENTS
    docs = {d[0]: d for d in DOCUMENTS}
    # Prevent accidental coverage by generic pages about unrelated prescribing.
    cases = {'prosth.removable': 'denture', 'prosth.cementation': 'indirect',
             'ortho.retention': 'orthodont', 'ortho.resorption': 'orthodont',
             'perio.peri_implant': 'implant', 'pediatric.pulp': 'pulp',
             'pediatric.behavior': 'behavior', 'surgery.sinus': 'surgical',
             'oral_medicine.saliva': 'xerostomia', 'restorative.adhesion': 'restoration',
             'imaging.general': 'radiograph', 'endo.general': 'root canal'}
    for topic, word in cases.items():
        assert any(word in (docs[ident][2] + ' ' + ' '.join(docs[ident][5])).casefold()
                   for ident in TOPIC_DOCUMENTS[topic]), topic
