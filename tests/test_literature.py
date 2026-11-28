"""Unit tests for literature citation verification, bibliography auditing, and similarity search."""

import httpx
import pytest
import respx

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography_async
from sci_verifier_mcp.literature.citation_verifier import verify_citation_async
from sci_verifier_mcp.literature.similarity import find_similar_papers_async

MOCK_CROSSREF_WORK = {
    "message": {
        "title": ["Attention Is All You Need"],
        "author": [
            {"given": "Ashish", "family": "Vaswani"},
            {"given": "Noam", "family": "Shazeer"},
        ],
        "issued": {"date-parts": [[2017, 6, 12]]},
        "DOI": "10.5555/3295222.3295349",
    }
}

MOCK_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v1</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>
"""


@pytest.mark.asyncio
@respx.mock
async def test_verify_citation_valid_doi():
    respx.get("https://api.crossref.org/works/10.5555/3295222.3295349").mock(
        return_value=httpx.Response(200, json=MOCK_CROSSREF_WORK)
    )

    res = await verify_citation_async(
        title="Attention Is All You Need",
        authors=["Vaswani", "Shazeer"],
        year=2017,
        doi="10.5555/3295222.3295349"
    )
    assert res.status == VerificationStatus.VERIFIED
    assert "verified via Crossref" in res.summary
    assert res.details["confidence_score"] >= 0.85
    assert len(res.sources) > 0


@pytest.mark.asyncio
@respx.mock
async def test_verify_citation_fake_doi():
    respx.get("https://api.crossref.org/works/10.1000/fake_doi_does_not_exist").mock(
        return_value=httpx.Response(404)
    )

    res = await verify_citation_async(doi="10.1000/fake_doi_does_not_exist")
    assert res.status == VerificationStatus.FAILED
    assert "Fabricated or nonexistent DOI" in res.summary
    assert res.details["confidence"] == 0.0


@pytest.mark.asyncio
@respx.mock
async def test_verify_citation_valid_arxiv():
    respx.get("http://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=MOCK_ARXIV_XML)
    )

    res = await verify_citation_async(
        title="Attention Is All You Need",
        arxiv_id="1706.03762"
    )
    assert res.status == VerificationStatus.VERIFIED
    assert "verified via arXiv" in res.summary


@pytest.mark.asyncio
@respx.mock
async def test_audit_bibliography_with_mixed_entries():
    # Mock Crossref for entry1 (valid)
    respx.get("https://api.crossref.org/works/10.5555/3295222.3295349").mock(
        return_value=httpx.Response(200, json=MOCK_CROSSREF_WORK)
    )
    # Mock Crossref 404 for entry2 (fake)
    respx.get("https://api.crossref.org/works/10.1234/fake_paper").mock(
        return_value=httpx.Response(404)
    )

    bibtex = """
    @article{vaswani2017,
      title = {Attention Is All You Need},
      author = {Vaswani, Ashish and Shazeer, Noam},
      year = {2017},
      doi = {10.5555/3295222.3295349}
    }
    @article{fakepaper2024,
      title = {Completely Made Up Paper by LLM},
      author = {Hallucinator, Alice},
      year = {2024},
      doi = {10.1234/fake_paper}
    }
    """

    res = await audit_bibliography_async(bibtex)
    assert res.status == VerificationStatus.FAILED
    assert "flagged 1 hallucinated/failed citation(s)" in res.summary
    assert res.details["verified_count"] == 1
    assert res.details["failed_count"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_find_similar_papers():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "Quantum Hall Effect in Graphene",
                        "authors": [{"name": "A. Geim"}, {"name": "K. Novoselov"}],
                        "year": 2005,
                        "citationCount": 4500,
                        "url": "https://doi.org/10.1038/nature04233",
                    }
                ]
            }
        )
    )
    respx.get("http://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="<feed></feed>")
    )

    res = await find_similar_papers_async("graphene quantum hall effect", domain="materials", limit=5)
    assert res.status == VerificationStatus.VERIFIED
    assert len(res.details["papers"]) >= 1
    assert res.details["papers"][0]["title"] == "Quantum Hall Effect in Graphene"
