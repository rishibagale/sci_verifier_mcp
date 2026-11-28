"""Lean 4 / Mathlib4 / PhysLib premise search via Loogle and LeanSearch APIs."""

import asyncio
from typing import Any

import httpx

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.clients import LiteratureClient

LOOGLE_ENDPOINT = "https://loogle.lean-lang.org/json"
LEANSEARCH_ENDPOINT = "https://leansearch.net/api/search"


async def search_lean_premises_async(
    query: str,
    backend: str = "loogle",
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
) -> VerificationResult:
    """Search Mathlib4 and PhysLib theorems/lemmas by type pattern (Loogle) or natural language (LeanSearch)."""
    clean_query = query.strip()
    if not clean_query:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty premise search query provided.",
            details={}
        )

    b = backend.strip().lower()
    if b not in ("loogle", "leansearch"):
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Unsupported premise backend '{backend}'. Choose 'loogle' or 'leansearch'.",
            details={}
        )

    lit = LiteratureClient()
    premises: list[dict[str, Any]] = []
    sources: list[str] = []

    if b == "loogle":
        res = await lit.get_cached_or_fetch(
            LOOGLE_ENDPOINT,
            {"q": clean_query},
            {"User-Agent": "sci-verifier-mcp/0.1.0", "Accept": "application/json"},
            client=client,
        )
        if not res or not isinstance(res, dict):
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                summary="Loogle premise search API did not respond or returned invalid data.",
                details={"query": clean_query, "backend": b},
                sources=[LOOGLE_ENDPOINT],
            )
        if res.get("error"):
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Loogle query error: {res['error']}",
                details={"query": clean_query, "error": res["error"]},
                sources=[LOOGLE_ENDPOINT],
            )
        for hit in (res.get("hits") or [])[:limit]:
            premises.append({
                "name": hit.get("name", ""),
                "type": hit.get("type", ""),
                "module": hit.get("module", ""),
                "doc": (hit.get("doc") or "")[:300],
            })
        sources.append(LOOGLE_ENDPOINT)

    else:  # leansearch
        res = await lit.get_cached_or_fetch(
            LEANSEARCH_ENDPOINT,
            {"query": clean_query, "num_results": str(limit)},
            {"User-Agent": "sci-verifier-mcp/0.1.0", "Accept": "application/json"},
            client=client,
        )
        if not res:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                summary="LeanSearch premise search API did not respond.",
                details={"query": clean_query, "backend": b},
                sources=[LEANSEARCH_ENDPOINT],
            )
        raw_hits = res if isinstance(res, list) else res.get("results", [])
        for hit in raw_hits[:limit]:
            result_obj = hit.get("result", hit) if isinstance(hit, dict) else {}
            premises.append({
                "name": ".".join(result_obj.get("name", [])) if isinstance(result_obj.get("name"), list) else str(result_obj.get("name", "")),
                "type": result_obj.get("type", ""),
                "module": result_obj.get("module_name", result_obj.get("module", "")),
                "doc": str(result_obj.get("docstring") or "")[:300],
            })
        sources.append(LEANSEARCH_ENDPOINT)

    if not premises:
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=f"No matching Lean 4 / Mathlib4 premises found via {b} for '{clean_query}'.",
            details={"query": clean_query, "backend": b, "premises": []},
            sources=sources,
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=f"Found {len(premises)} Lean 4 premise(s) via {b} for '{clean_query}'.",
        details={"query": clean_query, "backend": b, "premises": premises},
        sources=sources,
    )


def search_lean_premises(
    query: str,
    backend: str = "loogle",
    limit: int = 10,
) -> VerificationResult:
    """Synchronous entrypoint for search_lean_premises_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                search_lean_premises_async(query, backend, limit),
            ).result()
    return asyncio.run(search_lean_premises_async(query, backend, limit))
