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

    def related_ids(self, seeds, limit, *, section_queries=()):
        nodes = {node for row in seeds for node in source_nodes(row)}
        sections = {(int(row[1]), str(row[5]).strip().casefold()) for row in seeds
                    if row[5] and len(str(row[5]).strip()) >= 6}
        requested_sections = self.requested_sections(seeds, section_queries)
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
