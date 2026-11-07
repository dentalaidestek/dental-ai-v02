"""Opt-in live public metadata test; no writes to a production account."""

import asyncio
import os
import pytest
from app import expert_publications as bibliography


@pytest.mark.skipif(
    os.getenv("TEST_LIVE_ORCID") != "1",
    reason="Set TEST_LIVE_ORCID=1 for public API integration",
)
def test_aziz_sancar_public_works_live():
    rows = asyncio.run(bibliography.orcid_works("0000-0001-6469-4900"))
    assert len(rows) > 0
    assert any(
        "circadian" in row["title"].lower() or "repair" in row["title"].lower()
        for row in rows
    )
    assert len({(r["doi"] or r["source_key"]) for r in rows}) == len(rows)


def test_metadata_transport_rejects_non_registry_hosts():
    with pytest.raises(ValueError):
        bibliography._registry_url("https://127.0.0.1/private")


@pytest.mark.skipif(
    os.getenv("TEST_LIVE_ORCID") != "1",
    reason="Set TEST_LIVE_ORCID=1 for public publisher integration",
)
def test_pubmed_preview_live():
    from app.expert_social_safety import preview

    data = asyncio.run(preview("https://pubmed.ncbi.nlm.nih.gov/35217627/"))
    assert "repair" in data["title"].lower()
    assert data["domain"] == "pubmed.ncbi.nlm.nih.gov"


@pytest.mark.skipif(
    os.getenv("TEST_LIVE_ORCID") != "1",
    reason="Set TEST_LIVE_ORCID=1 for live Crossref integration",
)
def test_live_crossref_registry_match():
    record = asyncio.run(bibliography.crossref("10.1038/nphys1170"))
    assert record["doi"] == "10.1038/nphys1170" and record["title"]
