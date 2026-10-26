"""Opt-in read-only literature catalogue. Atomic offline snapshots; no patient data."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def publish(path, references):
    """Replace a whole snapshot, so removed/retracted records cannot survive a rebuild.

    Caller must finish all topic fetches successfully before publishing. Never use
    this as a per-request cache or to store clinical conversations.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.literature-', suffix='.sqlite', dir=path.parent)
    os.close(handle)
    try:
        with sqlite3.connect(temporary) as con:
            con.executescript('''
                CREATE TABLE docs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, priority INTEGER, year INTEGER);
                CREATE TABLE topics(id TEXT NOT NULL, topic TEXT NOT NULL, PRIMARY KEY(id, topic));
                CREATE INDEX by_topic ON topics(topic);
                CREATE VIRTUAL TABLE docs_fts USING fts5(id UNINDEXED, title, abstract);
                PRAGMA user_version=1;
            ''')
            ranks = {'guideline': 0, 'meta_analysis': 1, 'systematic_review': 2}
            for ref in references:
                # IDs and links are reconstructed from validated PubMed identities.
                ident = ref.get('id', '')
                if not ident.startswith('pubmed-') or not ident[7:].isdigit():
                    raise ValueError('Invalid literature identity')
                if not ref.get('excerpts'):
                    continue
                clean = dict(ref, url='https://pubmed.ncbi.nlm.nih.gov/' + ident[7:] + '/')
                con.execute('INSERT INTO docs VALUES(?,?,?,?)', (ident, json.dumps(clean, ensure_ascii=False),
                    ranks.get(ref.get('evidence_level'), 3), int(ref.get('publication_year') or 0)))
                con.execute('INSERT INTO docs_fts VALUES(?,?,?)', (ident, ref.get('title', ''), '\n'.join(ref['excerpts'])))
                con.executemany('INSERT OR IGNORE INTO topics VALUES(?,?)', [(ident, t) for t in ref.get('matched_topics', [])])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def retrieve(topics):
    from app.voice_exam_literature import TOPICS
    allowed = {topic for topic, _ in TOPICS}
    selected = list(dict.fromkeys(i.get('topic') for i in topics or [] if isinstance(i, dict)))
    missing = ['literature-topic-unsupported'] if any(t not in allowed for t in selected) else []
    selected = [t for t in selected if t in allowed][:6]
    path = os.getenv('VOICE_LITERATURE_DB', '')
    if not path or not Path(path).is_file():
        return [], ['literature-index-unavailable']
    references = {}
    try:
        con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            if con.execute('PRAGMA user_version').fetchone()[0] != 1:
                return [], ['literature-index-version']
            for topic in selected:
                # Topic membership was established by a fixed PubMed query offline.
                # Do not require exact synonym phrases again: that would lose recalls.
                rows = con.execute('''SELECT d.payload FROM docs d JOIN topics t ON t.id=d.id
                    WHERE t.topic=? ORDER BY d.priority, d.year DESC, d.id LIMIT 6''', (topic,)).fetchall()
                if not rows:
                    missing.append('literature:' + topic)
                for row in rows:
                    ref = json.loads(row[0])
                    references[ref['id']] = ref
                if rows and not any(json.loads(row[0]).get('clinical_use') for row in rows):
                    missing.append('literature-no-clinical-evidence:' + topic)
        finally:
            con.close()
    except (sqlite3.Error, ValueError, OSError, KeyError):
        return [], ['literature-index-unavailable']
    return list(references.values()), missing
