"""Public bibliographic metadata. An ORCID number does not prove account ownership."""

import json
import asyncio
import aiohttp
import os
import ssl
from urllib.parse import urlsplit
import re
import hashlib
from urllib.parse import quote
from app.expert_social_safety import safe_url


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


def _registry_url(url):
    """Only fixed official registries may use the configured outbound proxy."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in {
            "pub.orcid.org",
            "api.crossref.org",
            "pubmed.ncbi.nlm.nih.gov",
            "dergipark.org.tr",
            "eutils.ncbi.nlm.nih.gov",
        }
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Bibliyografik kaynak adresi geçersiz.")
    return url


async def registry_bytes(url, *, limit, accept, timeout):
    # Pasted web URLs use the other, DNS-pinned SSRF client. Here the only
    # destinations are official registries and redirects are always rejected.
    url = _registry_url(url)
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=cafile))
    async with aiohttp.ClientSession(
        trust_env=True,
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout + 8),
        auto_decompress=False,
    ) as client:
        async with client.get(
            url,
            headers={
                "Accept": accept,
                "User-Agent": "DentalAI-Profile/1.0",
                "Accept-Encoding": "identity",
            },
            allow_redirects=False,
        ) as response:
            if response.status != 200 or response.headers.get(
                "Content-Encoding", "identity"
            ).lower() not in ("", "identity"):
                raise ValueError("Bibliyografik kaynağa erişilemedi.")
            if response.content_length and response.content_length > limit:
                raise ValueError("Kaynak boyut sınırını aşıyor.")
            data = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Kaynak boyut sınırını aşıyor.")
            return bytes(data)


async def orcid_works(orcid):
    orcid = normalize_orcid(orcid)
    raw = await registry_bytes(
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
    raw = await registry_bytes(
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


async def pubmed_preview(pmid):
    if not re.fullmatch(r"\d{1,10}", pmid):
        raise ValueError("PubMed kaydı geçersiz.")
    raw = await registry_bytes(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id="
        + pmid
        + "&retmode=json",
        limit=256 * 1024,
        accept="application/json",
        timeout=4,
    )
    record = (json.loads(raw).get("result") or {}).get(pmid) or {}
    if not record.get("title"):
        raise ValueError("PubMed kaydı bulunamadı.")
    import html

    return {
        "url": "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/",
        "domain": "pubmed.ncbi.nlm.nih.gov",
        "site_name": "PubMed",
        "title": html.unescape(re.sub(r"<[^>]+>", "", record["title"]))[:300],
        "description": " · ".join(
            filter(
                None,
                [
                    record.get("fulljournalname") or record.get("source"),
                    record.get("pubdate"),
                ],
            )
        )[:500],
        "image_url": None,
    }
