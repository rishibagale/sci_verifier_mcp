"""Opt-in live integration tests hitting real public APIs (run with: pytest -m live -v)."""

import pytest

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.literature.citation_verifier import verify_citation_async
from sci_verifier_mcp.literature.discovery_feed import track_recent_discoveries_async
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art_async
from sci_verifier_mcp.proofs.premise_search import search_lean_premises_async


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_crossref_and_arxiv_citation():
    res = await verify_citation_async(
        title="Attention Is All You Need",
        arxiv_id="1706.03762",
    )
    assert res.status == VerificationStatus.VERIFIED


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_loogle_premise_search():
    res = await search_lean_premises_async("Nat.add_comm", backend="loogle", limit=3)
    assert res.status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIAL_MATCH)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_optimade_silicon():
    res = await check_novel_structure_prior_art_async("Si", spacegroup_number=227, limit=3)
    assert res.status in (VerificationStatus.FAILED, VerificationStatus.VERIFIED)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_recent_discoveries():
    res = await track_recent_discoveries_async("math", days=14, limit=3)
    assert res.status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIAL_MATCH)
