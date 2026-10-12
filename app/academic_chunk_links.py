"""Source-only chunk links across a published course; no inference/API calls.

Nodes are the metadata already persisted by the index worker, not concepts
inferred from the student's question. Links locate evidence, never prove facts.
"""
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
import json
import re
import threading
import time
import unicodedata


def _section_keys(section):
    parts = str(section or '').strip().casefold().split(' > ')
    return [' > '.join(parts[:i]) for i in range(1, len(parts) + 1) if parts[0]]


def _heading_terms(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    # Match a heading's Turkish plural spelling without dropping its parent
    # qualifiers. This is source lookup, not question interpretation.
    return {re.sub(r'(?<=\w)(?:lar|ler)(?:ı|i|u|ü)?$', '', term)
            for term in re.findall(r'[^\W_]+', value)}


def source_nodes(row):
    try:
        value = json.loads(row[14] or '{}').get('nodes', [])
    except (ValueError, TypeError, AttributeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(x for x in value if isinstance(x, str) and 0 < len(x) <= 120))[:32]


@dataclass
class CourseLinks:
    rows: dict
    by_node: dict
    by_section: dict

    def lookup_diagnostics(self, phrase):
        """Aggregate lookup shape only: never log headings or user text."""
        wanted = _heading_terms(phrase)
        suffixes = [_heading_terms(' > '.join(section.split(' > ')[start:]))
                    for _, section in self.by_section for start in range(len(section.split(' > ')))]
        overlaps = [(len(terms & wanted), len(terms - wanted)) for terms in suffixes if len(terms) >= 2]
        best = max(overlaps, key=lambda item:(item[0], -item[1]), default=(0,0))
        return {'headings':len(self.by_section),
                'nested':sum(' > ' in section for _,section in self.by_section),
                'empty_rows':sum(not row[1] for row in self.rows.values()),
                'matched_terms':best[0], 'missing_terms':best[1],
                'query_terms':len(wanted)}

    def focus_nodes(self, phrase):
        # Literal lookup within this course's indexed vocabulary only. Gemini
        # still interprets the request; this does not infer a task or a fact.
        from app.dental_knowledge_graph import exact_nodes_in_subset
        return frozenset(node.id for node in exact_nodes_in_subset(phrase, tuple(self.by_node)))

    def requested_sections(self, seeds, section_queries):
        query_terms = [_heading_terms(query) for query in section_queries]
        # A request naming a source heading asks for its contents, which may
        # legitimately contain different concepts. A single-concept lookup
        # must still retain the old concept isolation below.
        heading_sections = {(int(row[1]), key) for row in seeds for key in _section_keys(row[5])}
        requested_sections = {section for section in heading_sections
                              if len(_heading_terms(section[1])) >= 2 and
                              any(_heading_terms(section[1]) <= query for query in query_terms)}
        requested_sections = {section for section in requested_sections
                              if not any(other[0] == section[0] and
                                         other[1].startswith(section[1] + ' > ')
                                         for other in requested_sections)}
        return requested_sections

    def named_section_ids(self, phrase):
        """Match the most specific source path suffix and return all children.

        Outer document headings need not be repeated in a question. Parent
        qualifiers distinguish e.g. skin/single from bone/single sections.
        """
        wanted = _heading_terms(phrase)
        candidates = []
        for (material, section), ids in self.by_section.items():
            parts = section.split(' > ')
            score = max((len(terms) for start in range(len(parts))
                         if len(terms := _heading_terms(' > '.join(parts[start:]))) >= 2
                         and terms <= wanted), default=0)
            if score:
                candidates.append((score, material, section, ids))
        best = max((item[0] for item in candidates), default=0)
        selected = [(m,section,ids) for score,m,section,ids in candidates if score==best]
        selected = [(m,section,ids) for m,section,ids in selected if not any(
            other_m==m and other_section.startswith(section+' > ')
            for other_m,other_section,_ in selected)]
        ids = {cid for _,_,members in selected for cid in members}
        return sorted(ids, key=lambda cid: (self.rows[cid][0],self.rows[cid][3],self.rows[cid][4],cid))

    def related_ids(self, seeds, limit, *, section_queries=(), focus_nodes=()):
        nodes = {node for row in seeds for node in source_nodes(row)}
        if focus_nodes:
            nodes.intersection_update(focus_nodes)
        sections = {(int(row[1]), str(row[5]).strip().casefold()) for row in seeds
                    if row[5] and len(str(row[5]).strip()) >= 6}
        requested_sections = self.requested_sections(seeds, section_queries)
        focused_sections = set()
        if focus_nodes:
            from app.dental_knowledge_graph import exact_nodes_in_subset
            focused_sections = {section for section in sections if
                exact_nodes_in_subset(section[1], tuple(focus_nodes))}
        seed_ids = {int(row[0]) for row in seeds}
        candidates = set()
        for node in nodes:
            candidates.update(self.by_node.get(node, ()))
        # Section continuity helps text lacking a recognized catalog concept.
        # A heading is confined to its actual document, never an entire specialty.
        for section in sections | requested_sections:
            candidates.update(self.by_section.get(section, ()))
        buckets = defaultdict(list)
        for cid in candidates - seed_ids:
            material, section, kind, page, chunk, row_nodes = self.rows[cid]
            overlap = len(nodes.intersection(row_nodes))
            same_section = (material, section) in sections
            requested_section = any((material, key) in requested_sections for key in _section_keys(section))
            if requested_sections and not requested_section:
                continue
            if focus_nodes and not overlap and not requested_section and (material, section) not in focused_sections:
                continue
            # Do not link a different explicit concept merely because the
            # inherited heading happens to be the same.
            if nodes and row_nodes and not overlap and not requested_section:
                continue
            if not overlap and not same_section and not requested_section:
                continue
            buckets[(not requested_section, -overlap, not same_section, material, section, kind)].append((page, chunk, cid))
        pools = []
        for key in sorted(buckets):
            members = sorted(buckets[key])
            # Include distant pages before repeated early-page fragments.
            order = list(dict.fromkeys((0, len(members)//2, len(members)-1)))
            sampled = set(order)
            order.extend(i for i in range(len(members)) if i not in sampled)
            pools.append([members[i][2] for i in order])
        result = []
        for offset in range(max((len(p) for p in pools), default=0)):
            for pool in pools:
                if offset < len(pool):
                    result.append(pool[offset])
                    if len(result) >= limit:
                        return result
        return result


def build_course_links(pages):
    rows, by_node, by_section = {}, defaultdict(list), defaultdict(list)
    for page in pages:
        for row in page:
            if str(row[6]).upper() == 'QUESTION':
                continue
            cid, material = int(row[0]), int(row[1])
            section = str(row[5] or '').strip().casefold()
            nodes = source_nodes(row)
            rows[cid] = (material, section, str(row[6]), int(row[3]), int(row[13]), nodes)
            for node in nodes:
                by_node[node].append(cid)
            for key in _section_keys(section):
                if len(key) >= 6:
                    by_section[(material, key)].append(cid)
    return CourseLinks(rows, dict(by_node), dict(by_section))


_CACHE = OrderedDict()
_LOCK = threading.Lock()
_MAX_CACHED_ROWS = 20000


def get_course_links(session, *, owner_user_id, course_id):
    from app.study_retrieval_v2 import _course_index_fingerprint, _coverage_metadata_page
    fingerprint = _course_index_fingerprint(session, owner_user_id=owner_user_id, course_id=course_id)
    key = (owner_user_id, course_id, fingerprint)
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < 300:
            _CACHE.move_to_end(key)
            return hit[1]
    def pages():
        after = 0
        while True:
            page = _coverage_metadata_page(session, owner_user_id=owner_user_id,
                                          course_id=course_id, after_id=after, limit=400)
            if not page:
                return
            yield page
            after = int(page[-1][0])
            if len(page) < 400:
                return
    links = build_course_links(pages())
    with _LOCK:
        # Old generations are never reused after publish/delete/index changes.
        for old in list(_CACHE):
            if old[:2] == key[:2] or now - _CACHE[old][0] >= 300:
                del _CACHE[old]
        if len(links.rows) <= _MAX_CACHED_ROWS:
            while _CACHE and (len(_CACHE) >= 4 or
                    sum(len(v[1].rows) for v in _CACHE.values()) + len(links.rows) > _MAX_CACHED_ROWS):
                _CACHE.popitem(last=False)
            _CACHE[key] = (now, links)
    return links


def planner_source_outline(session, *, owner_user_id, course_id, query='', history=None):
    """Bounded, source-owned heading vocabulary, never raw facts or file IDs."""
    from app.academic_direct_request import previous_source_request
    if session.get_bind().dialect.name != 'postgresql':
        return {'sections': [], 'complete': False}
    links = get_course_links(session, owner_user_id=owner_user_id, course_id=course_id)
    previous = previous_source_request(history or [])
    terms = _heading_terms(query)
    if previous:
        terms |= set().union(*(_heading_terms(x) for x in previous.get('retrieval_queries', [])))
    headings = sorted({section for _,section in links.by_section},
                      key=lambda x: (-len(_heading_terms(x) & terms), x.count(' > '), x))
    selected, size = [], 0
    for heading in headings:
        length = len(heading.encode('utf-8')) + 8
        if len(selected) >= 96 or size + length > 8000:
            continue
        selected.append(heading); size += length
    return {'sections':selected,'complete':len(selected)==len(headings)}
