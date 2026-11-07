"""Public bibliographic metadata. An ORCID number does not prove account ownership."""

import json
import re
import hashlib
from urllib.parse import quote
from app.expert_social_safety import fetch_bytes, safe_url


def normalize_orcid(raw):
    raw = re.sub(r"^https?://(?:www\.)?orcid\.org/", "", raw.strip(), flags=re.I).strip(
        "/"
    )
    compact = raw.replace("-", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", compact):
        raise ValueError("ORCID iD geçersiz.")
    total = 0
    for digit in compact[:15]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    if compact[-1] != ("X" if check == 10 else str(check)):
        raise ValueError("ORCID kontrol hanesi geçersiz.")
    return "-".join(compact[i : i + 4] for i in range(0, 16, 4))


def normalize_doi(raw):
    raw = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", raw.strip(), flags=re.I
    ).lower()
    if raw and (len(raw) > 255 or not re.fullmatch(r"10\.\d{4,9}/[^\s<>]+", raw)):
        raise ValueError("DOI geçersiz.")
    return raw or None


def fingerprint(title, year, doi):
    return (
        ("doi:" + doi)
        if doi
        else "title:"
        + hashlib.sha256(
            (
                re.sub(r"\s+", " ", title).strip().casefold() + "|" + str(year or "")
            ).encode()
        ).hexdigest()
    )


def parse_orcid(data):
    rows = []
    seen = set()
    for group in data.get("group", []):
        summaries = group.get("work-summary") or []
        summary = next(
            (w for w in summaries if w.get("visibility", "public") == "public"), None
        )
        if not summary:
            continue
        title = ((summary.get("title") or {}).get("title") or {}).get("value", "")
        if not title:
            continue
        doi = None
        for item in (summary.get("external-ids") or {}).get("external-id", []):
            if (
                item.get("external-id-type", "").lower() == "doi"
                and item.get("external-id-relationship", "self") == "self"
            ):
                try:
                    doi = normalize_doi(item.get("external-id-value", ""))
                except ValueError:
                    pass
        year = ((summary.get("publication-date") or {}).get("year") or {}).get("value")
        year = int(year) if str(year).isdigit() and 1000 <= int(year) <= 2200 else None
        key = fingerprint(title, year, doi)
        if key in seen:
            continue
        seen.add(key)
        raw_url = (summary.get("url") or {}).get("value")
        try:
            url = safe_url(raw_url) if raw_url else None
        except ValueError:
            url = None
        rows.append(
            dict(
                title=title[:500],
                authors="",
                year=year,
                journal=((summary.get("journal-title") or {}).get("value") or "")[:300],
                doi=doi,
                url=url or ("https://doi.org/" + doi if doi else None),
                source="ORCID",
                source_key=str(summary.get("put-code") or key),
                description="",
            )
        )
    return rows


async def orcid_works(orcid):
    orcid = normalize_orcid(orcid)
    raw, _, _ = await fetch_bytes(
        "https://pub.orcid.org/v3.0/" + orcid + "/works",
        limit=2 * 1024 * 1024,
        accept="application/vnd.orcid+json",
        timeout=10,
    )
    return parse_orcid(json.loads(raw))


async def crossref(doi):
    doi = normalize_doi(doi)
    if not doi:
        raise ValueError("DOI girin.")
    raw, _, _ = await fetch_bytes(
        "https://api.crossref.org/works/" + quote(doi, safe=""),
        limit=512 * 1024,
        accept="application/json",
        timeout=6,
    )
    m = json.loads(raw).get("message") or {}
    if normalize_doi(m.get("DOI", "")) != doi:
        raise ValueError("DOI eşleştirilemedi.")
    dates = (m.get("published") or {}).get("date-parts") or []
    return dict(
        title=(m.get("title") or [""])[0][:500],
        journal=(m.get("container-title") or [""])[0][:300],
        year=dates[0][0] if dates and dates[0] else None,
        authors=", ".join(
            " ".join(filter(None, (a.get("given"), a.get("family"))))
            for a in m.get("author", [])
        )[:2000],
        doi=doi,
        url="https://doi.org/" + doi,
    )
