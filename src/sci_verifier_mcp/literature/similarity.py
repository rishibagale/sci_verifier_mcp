"""Multi-database prior-art and literature similarity search across math, physics, hep, and materials."""

import re
from typing import Any
import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.clients import LiteratureClient


async def find_similar_papers_async(
    query: str,
    domain: str = "general",
    limit: int = 10
) -> VerificationResult:
    """Surface related papers, existing proofs, or overlapping derivations across multiple registries."""
    clean_query = query.strip()
    if not clean_query:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty search query provided.",
            details={}
        )

    lit = LiteratureClient()
    domain_clean = domain.lower().strip()
    all_papers: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=config.DEFAULT_HTTP_TIMEOUT) as client:
        # 1. Semantic Scholar (General, Math, Physics, Materials)
        s2_items = await lit.search_semantic_scholar(clean_query, limit=limit, client=client)
        all_papers.extend(s2_items)

        # 2. arXiv with domain category filtering
        arxiv_cat = None
        if domain_clean in ("materials", "materials_science", "cond-mat"):
            arxiv_cat = "cond-mat.mtrl-sci"
        elif domain_clean in ("math", "mathematics"):
            arxiv_cat = "math.*"
        elif domain_clean in ("hep", "high_energy_physics"):
            arxiv_cat = "hep-th"

        arxiv_items = await lit.search_arxiv(clean_query, category=arxiv_cat, limit=limit, client=client)
        all_papers.extend(arxiv_items)

        # 3. INSPIRE-HEP (for HEP and Theoretical Physics)
        if domain_clean in ("hep", "physics", "theoretical_physics", "general"):
            inspire_items = await lit.search_inspire_hep(clean_query, limit=limit, client=client)
            all_papers.extend(inspire_items)

    # Deduplicate by normalized title
    seen_titles = set()
    deduped_papers = []
    for p in all_papers:
        norm = " ".join(re.sub(r"[^\w\s]", "", p.get("title", "").lower()).split()) if "re" in globals() else p.get("title", "").lower()
        if norm and norm not in seen_titles:
            seen_titles.add(norm)
            deduped_papers.append(p)

    # Sort by citation count if available
    deduped_papers.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
    top_papers = deduped_papers[:limit]

    sources = [p["url"] for p in top_papers if p.get("url")]

    return VerificationResult(
        status=VerificationStatus.VERIFIED if top_papers else VerificationStatus.PARTIAL_MATCH,
        summary=(
            f"Found {len(top_papers)} relevant paper(s) for query '{clean_query}' "
            f"in domain '{domain_clean}'."
        ),
        details={
            "query": clean_query,
            "domain": domain_clean,
            "total_matches": len(top_papers),
            "papers": top_papers,
        },
        sources=sources,
    )


def find_similar_papers(
    query: str,
    domain: str = "general",
    limit: int = 10
) -> VerificationResult:
    """Synchronous entrypoint for find_similar_papers_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, find_similar_papers_async(query, domain, limit)).result()
    else:
        return asyncio.run(find_similar_papers_async(query, domain, limit))
