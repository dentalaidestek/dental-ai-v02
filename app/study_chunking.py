"""Deterministic, structure-aware chunking for Academic AI V2.

The indexer deliberately keeps this module provider and database independent.
That makes a generation reproducible after a crash and lets retrieval evolve
without changing the source-page checkpoints.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_BULLET_RE = re.compile(r"^\s*(?:[-*•◦▪] |\d+[.)]\s+|[A-ZÇĞİÖŞÜ][.)]\s+)")
_TABLE_GAP_RE = re.compile(r"\S\s{2,}\S")
_MCQ_STEM_RE = re.compile(r"^\s*(?:soru\s*)?\d{1,3}[.)]\s+", re.I)
_MCQ_OPTION_RE = re.compile(r"^\s*[A-E][.)]\s+", re.I)
_DENTAL_HEADING_RE = re.compile(
    r"\b(?:tanı|tanım|etyoloji|patogenez|sınıflama|klinik|radyografik|"
    r"endikasyon|kontrendikasyon|tedavi|komplikasyon|prognoz|ayırıcı tanı|"
    r"histoloji|bulgu|semptom|teşhis|korunma|materyal|teknik|faz|evre|derece)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DentalChunk:
    text: str
    section_title: str | None
    content_kind: str


def normalize_extracted_text(value: str | None) -> str:
    """Normalize PDF text while preserving lines used by headings and tables."""
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    # Tabs are expanded, but repeated spaces stay intact because they are the
    # only table-column signal many PDF extractors preserve.
    lines = [line.expandtabs(4).strip() for line in value.split("\n")]
    compact: list[str] = []
    blank = False
    for line in lines:
        if line:
            compact.append(line)
            blank = False
        elif compact and not blank:
            compact.append("")
            blank = True
    return "\n".join(compact).strip()


def _is_heading(line: str) -> bool:
    raw = line.strip()
    stripped = raw.rstrip(":")
    if not stripped or len(stripped) > 110 or _BULLET_RE.match(line):
        return False
    words = stripped.split()
    if len(words) > 12:
        return False
    letters = [ch for ch in stripped if ch.isalpha()]
    uppercase_ratio = sum(ch.isupper() for ch in letters) / max(1, len(letters))
    title_shape = raw.endswith(":") or uppercase_ratio >= 0.72
    return title_shape or bool(_DENTAL_HEADING_RE.search(stripped) and len(words) <= 8)


def _content_kind(lines: list[str]) -> str:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return "TEXT"
    table_rows = sum(bool(_TABLE_GAP_RE.search(line)) or line.count("|") >= 2 for line in nonempty)
    bullets = sum(bool(_BULLET_RE.match(line)) for line in nonempty)
    figure_terms = sum(bool(re.search(r"\b(?:şekil|resim|grafik|diagram|tablo)\s*\d*", line, re.I)) for line in nonempty)
    if table_rows >= 2 or (table_rows and len(nonempty) <= 5):
        return "TABLE"
    if figure_terms and len(nonempty) <= 10:
        return "VISUAL"
    if bullets >= max(2, len(nonempty) // 2):
        return "LIST"
    return "TEXT"


def _split_mcq_blocks(lines: list[str]) -> list[list[str]]:
    """Keep a question stem and its A-E choices in the same structural block."""
    blocks: list[list[str]] = []
    current: list[str] = []
    seen_option = False
    for line in lines:
        is_stem = bool(_MCQ_STEM_RE.match(line))
        is_option = bool(_MCQ_OPTION_RE.match(line))
        if is_stem and current:
            blocks.append(current)
            current = [line]
            seen_option = False
            continue
        if is_option:
            seen_option = True
        current.append(line)
    if current:
        blocks.append(current)
    # Only claim MCQ structure when at least one block actually has options.
    return blocks if any(any(_MCQ_OPTION_RE.match(x) for x in block) for block in blocks) else []


def _split_long_block(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            overlap = current[-overlap_chars:].lstrip() if overlap_chars else ""
            current = (overlap + " " + sentence).strip()
        else:
            current = (current + " " + sentence).strip()
    if current:
        pieces.append(current)
    # A PDF extraction can contain a single punctuation-free run.
    if len(pieces) == 1 and len(pieces[0]) > max_chars:
        raw = pieces[0]
        pieces = []
        start = 0
        while start < len(raw):
            end = min(len(raw), start + max_chars)
            pieces.append(raw[start:end].strip())
            if end == len(raw):
                break
            start = max(start + 1, end - overlap_chars)
    return [piece for piece in pieces if piece]


def chunk_dental_page(
    text: str,
    *,
    max_chars: int = 1800,
    min_chars: int = 180,
    overlap_chars: int = 180,
) -> list[DentalChunk]:
    """Split one page without separating a heading from its dental content.

    Page-local chunks keep citations exact. Retrieval expands neighboring pages
    when cross-page context is useful.
    """
    normalized = normalize_extracted_text(text)
    if not normalized:
        return []
    lines = normalized.splitlines()
    sections: list[tuple[str | None, list[str]]] = []
    title: str | None = None
    body: list[str] = []
    for line in lines:
        if _is_heading(line):
            if body:
                sections.append((title, body))
            title = line.strip().rstrip(":")
            body = []
        else:
            body.append(line)
    if body or title:
        sections.append((title, body))

    # Merge tiny fragments into the previous section unless doing so would
    # erase a useful heading boundary.
    merged: list[tuple[str | None, list[str]]] = []
    for section_title, section_lines in sections:
        section_text = "\n".join(section_lines).strip()
        if merged and len(section_text) < min_chars and section_title is None:
            merged[-1][1].extend(["", *section_lines])
        else:
            merged.append((section_title, list(section_lines)))

    chunks: list[DentalChunk] = []
    for section_title, section_lines in merged:
        mcq_blocks = _split_mcq_blocks(section_lines)
        if mcq_blocks:
            for block in mcq_blocks:
                block_text = "\n".join(block).strip()
                if not block_text:
                    continue
                # Never split choices away from their stem merely to satisfy the
                # normal prose chunk size; question blocks are bounded upstream
                # by one source page.
                chunks.append(DentalChunk(block_text, section_title, "QUESTION"))
            continue
        body_text = "\n".join(section_lines).strip()
        complete = f"{section_title}\n{body_text}".strip() if section_title else body_text
        if not complete:
            continue
        kind = _content_kind(section_lines)
        for piece in _split_long_block(complete, max_chars, overlap_chars):
            chunks.append(DentalChunk(piece, section_title, kind))
    return chunks or [DentalChunk(normalized, None, _content_kind(lines))]
