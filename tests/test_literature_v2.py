"""Unit tests for OpenAlex integration, retraction detection, claim alignment, and discovery feeds."""

import httpx
import pytest
import respx

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.literature.citation_verifier import verify_citation_async
from sci_verifier_mcp.literature.claim_alignment import verify_claim_against_paper_async
from sci_verifier_mcp.literature.discovery_feed import track_recent_discoveries_async

MOCK_OPENALEX_VALID = {
    "id": "https://openalex.org/W2963403868",
    "title": "Attention Is All You Need",
    "publication_year": 2017,
    "publication_date": "2017-06-12",
    "doi": "https://doi.org/10.5555/oa-valid-test",
    "is_retracted": False,
    "cited_by_count": 90000,
    "authorships": [
        {"author": {"display_name": "Ashish Vaswani"}},
        {"author": {"display_name": "Noam Shazeer"}},
    ],
    "primary_location": {"landing_page_url": "https://doi.org/10.5555/oa-valid-test"},
    "abstract_inverted_index": {
        "We": [0],
        "propose": [1],
        "the": [2],
        "Transformer": [3],
        "architecture": [4],
        "based": [5],
        "solely": [6],
        "on": [7],
        "attention": [8],
        "mechanisms": [9],
        "for": [10],
        "sequence": [11],
        "transduction": [12],
    },
}

MOCK_OPENALEX_RETRACTED = {
    "id": "https://openalex.org/W99999999",
    "title": "Room-Temperature Ambient-Pressure Superconductor Claim",
    "publication_year": 2023,
    "doi": "https://doi.org/10.1038/retracted-test-doi",
    "is_retracted": True,
    "cited_by_count": 12,
    "authorships": [{"author": {"display_name": "Jane Doe"}}],
    "abstract_inverted_index": {"Superconductor": [0], "claim": [1]},
}


@pytest.mark.asyncio
@respx.mock
async def test_verify_citation_detects_crossref_retraction():
    doi = "10.1000/crossref-retracted-v2"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "title": ["Faulty Material Synthesis Study"],
                    "author": [{"given": "John", "family": "Smith"}],
                    "issued": {"date-parts": [[2022, 1, 1]]},
                    "DOI": doi,
                    "update-to": [{"type": "retraction", "DOI": "10.1000/retraction-notice"}],
                }
            },
        )
    )

    res = await verify_citation_async(title="Faulty Material Synthesis Study", doi=doi)
    assert res.status == VerificationStatus.FAILED
    assert "RETRACTED PAPER" in res.summary
    assert res.details["retracted"] is True


@pytest.mark.asyncio
@respx.mock
async def test_verify_citation_detects_openalex_retraction():
    doi = "10.1038/retracted-test-doi"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    respx.get(f"https://api.openalex.org/works/https://doi.org/{doi}").mock(
        return_value=httpx.Response(200, json=MOCK_OPENALEX_RETRACTED)
    )

    res = await verify_citation_async(
        title="Room-Temperature Ambient-Pressure Superconductor Claim",
        doi=doi,
    )
    assert res.status == VerificationStatus.FAILED
    assert "RETRACTED PAPER" in res.summary
    assert res.details["retracted"] is True


@pytest.mark.asyncio
@respx.mock
async def test_claim_alignment_verified_and_paper_washing():
    doi = "10.5555/oa-valid-test"
    respx.get(f"https://api.openalex.org/works/https://doi.org/{doi}").mock(
        return_value=httpx.Response(200, json=MOCK_OPENALEX_VALID)
    )

    # Aligned claim
    ok = await verify_claim_against_paper_async(
        claim="The Transformer architecture uses attention mechanisms for sequence transduction.",
        doi=doi,
    )
    assert ok.status == VerificationStatus.VERIFIED
    assert ok.details["concept_overlap_score"] >= 0.45

    # Unrelated "paper-washing" claim attached to real DOI
    mismatch = await verify_claim_against_paper_async(
        claim="Perovskite lithium lanthanum zirconate exhibits high ionic conductivity at 300 Kelvin.",
        doi=doi,
    )
    assert mismatch.status == VerificationStatus.FAILED
    assert "paper-washing" in mismatch.summary.lower()


@pytest.mark.asyncio
@respx.mock
async def test_claim_alignment_flags_tortured_phrases():
    doi = "10.5555/oa-tortured-test"
    respx.get(f"https://api.openalex.org/works/https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "https://openalex.org/W1234",
                "title": "Bosom peril classification via counterfeit consciousness",
                "publication_year": 2024,
                "doi": f"https://doi.org/{doi}",
                "is_retracted": False,
                "abstract_inverted_index": {"bosom": [0], "peril": [1], "detection": [2]},
            },
        )
    )

    res = await verify_claim_against_paper_async(
        claim="Bosom peril detection performance",
        doi=doi,
    )
    assert res.status == VerificationStatus.FAILED
    assert "tortured phrases" in res.summary.lower()


@pytest.mark.asyncio
@respx.mock
async def test_track_recent_discoveries():
    respx.get("http://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(
            200,
            text="""<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <id>http://arxiv.org/abs/2611.00001v1</id>
                <published>2026-11-26T12:00:00Z</published>
                <title>Formalizing Quantum Mechanics in Lean 4</title>
                <summary>We present PhysLib extensions for quantum operators.</summary>
                <author><name>A. Researcher</name></author>
              </entry>
            </feed>""",
        )
    )
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W7777",
                        "title": "Machine Learning Interatomic Potentials Review",
                        "publication_year": 2026,
                        "publication_date": "2026-11-25",
                        "cited_by_count": 3,
                        "authorships": [{"author": {"display_name": "B. Scientist"}}],
                        "primary_location": {"landing_page_url": "https://example.org/paper"},
                    }
                ]
            },
        )
    )

    res = await track_recent_discoveries_async("Lean 4 quantum mechanics", days=7, limit=5)
    assert res.status == VerificationStatus.VERIFIED
    assert res.details["total_results"] == 2
    assert len(res.sources) == 2
