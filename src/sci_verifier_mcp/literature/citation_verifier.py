"""Verification and hallucination detection for academic citations across Crossref, arXiv, and INSPIRE-HEP."""

import re
from typing import Any

import httpx

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.clients import LiteratureClient


def normalize_title(title: str) -> str:
    """Normalize a title string for robust fuzzy comparison."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


def extract_surname(author_str: str) -> str:
    """Extract surname from either 'Last, First' or 'First Last' formatting."""
    s = author_str.strip()
    if not s:
        return ""
    if "," in s:
        return s.split(",")[0].strip().lower()
    return s.split()[-1].strip().lower()


def detect_crossref_retraction(crossref_data: dict[str, Any]) -> str | None:
    """Detect retraction or withdrawal notices in Crossref work metadata."""
    for upd in crossref_data.get("update-to") or []:
        upd_type = str(upd.get("type", "")).lower()
        if any(tok in upd_type for tok in ("retract", "withdraw")):
            return f"Crossref update-to notice: {upd.get('type')} (DOI: {upd.get('DOI', 'unknown')})"

    relation = crossref_data.get("relation") or {}
    if relation.get("is-retracted-by"):
        return f"Crossref relation is-retracted-by: {relation['is-retracted-by']}"

    titles = crossref_data.get("title") or []
    if titles and re.match(r"^\s*(RETRACTED|WITHDRAWN)\s*:", str(titles[0]), re.IGNORECASE):
        return f"Title marked as retracted/withdrawn: '{titles[0]}'"

    return None


def compute_string_similarity(s1: str, s2: str) -> float:
    """Compute token Jaccard and word overlap similarity between two strings."""
    n1 = normalize_title(s1)
    n2 = normalize_title(s2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    words1 = set(n1.split())
    words2 = set(n2.split())
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


async def verify_citation_async(
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    client: httpx.AsyncClient | None = None
) -> VerificationResult:
    """Cross-check citation against Crossref and arXiv to detect hallucinated papers or mismatched metadata."""
    if not any([title, doi, arxiv_id]):
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="At least one of 'title', 'doi', or 'arxiv_id' must be provided for citation verification.",
            details={}
        )

    lit = LiteratureClient()
    canonical_meta: dict[str, Any] | None = None
    sources: list[str] = []
    source_db = ""

    retraction_reason: str | None = None

    # 1. DOI Lookup (Crossref + OpenAlex cross-check / retraction check)
    if doi:
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        crossref_data = await lit.lookup_crossref_doi(clean_doi, client=client)
        openalex_data = await lit.lookup_openalex_doi(clean_doi, client=client)

        if crossref_data is not None:
            retraction_reason = detect_crossref_retraction(crossref_data)
            if not retraction_reason and openalex_data and openalex_data.get("is_retracted"):
                retraction_reason = "Flagged as retracted in OpenAlex (is_retracted=True)."

            canonical_meta = {
                "title": (crossref_data.get("title") or [""])[0],
                "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in crossref_data.get("author", [])],
                "year": (crossref_data.get("issued", {}).get("date-parts") or [[None]])[0][0],
                "doi": crossref_data.get("DOI"),
                "url": f"https://doi.org/{crossref_data.get('DOI')}",
                "is_retracted": bool(retraction_reason),
            }
            sources.append(canonical_meta["url"])
            source_db = "Crossref"
        elif openalex_data is not None:
            if openalex_data.get("is_retracted"):
                retraction_reason = "Flagged as retracted in OpenAlex (is_retracted=True)."
            canonical_meta = openalex_data
            sources.append(openalex_data.get("url") or f"https://doi.org/{clean_doi}")
            source_db = "OpenAlex"
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=f"Fabricated or nonexistent DOI '{doi}'. Not found in Crossref or OpenAlex.",
                details={"doi": doi, "confidence": 0.0},
                sources=[]
            )

    # 2. arXiv ID Lookup
    elif arxiv_id:
        arxiv_data = await lit.lookup_arxiv_id(arxiv_id, client=client)
        if arxiv_data is None:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=f"Nonexistent arXiv ID '{arxiv_id}'. Not found in arXiv repository.",
                details={"arxiv_id": arxiv_id, "confidence": 0.0},
                sources=[]
            )
        canonical_meta = arxiv_data
        sources.append(arxiv_data.get("url", f"https://arxiv.org/abs/{arxiv_id}"))
        source_db = "arXiv"

    # 3. Title/Author Search (Crossref -> OpenAlex -> arXiv)
    elif title:
        search_items = await lit.search_crossref_bibliographic(
            title,
            author=authors[0] if authors else None,
            rows=1,
            client=client
        )
        if search_items:
            item = search_items[0]
            retraction_reason = detect_crossref_retraction(item)
            canonical_meta = {
                "title": (item.get("title") or [""])[0],
                "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])],
                "year": (item.get("issued", {}).get("date-parts") or [[None]])[0][0],
                "doi": item.get("DOI"),
                "url": f"https://doi.org/{item.get('DOI')}",
                "is_retracted": bool(retraction_reason),
            }
            sources.append(canonical_meta["url"])
            source_db = "Crossref"
        else:
            oa_items = await lit.search_openalex(title, limit=1, client=client)
            if oa_items:
                canonical_meta = oa_items[0]
                if canonical_meta.get("is_retracted"):
                    retraction_reason = "Flagged as retracted in OpenAlex (is_retracted=True)."
                sources.append(canonical_meta.get("url", ""))
                source_db = "OpenAlex"
            else:
                arxiv_items = await lit.search_arxiv(title, limit=1, client=client)
                if arxiv_items:
                    canonical_meta = arxiv_items[0]
                    sources.append(canonical_meta.get("url", ""))
                    source_db = "arXiv"

    if canonical_meta is None:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"No matching publication found for title '{title}'. Possible hallucinated reference.",
            details={"claimed_title": title, "claimed_authors": authors, "claimed_year": year},
            sources=[]
        )

    # Cross-check metadata discrepancies
    ref_title = canonical_meta.get("title", "")
    ref_authors = canonical_meta.get("authors", [])
    ref_year = canonical_meta.get("year")

    # Title score
    title_sim = compute_string_similarity(title or "", ref_title) if title else 1.0

    # Author score
    author_match = True
    if authors and ref_authors:
        claimed_surnames = {extract_surname(a) for a in authors if a.strip()}
        ref_surnames = {extract_surname(a) for a in ref_authors if a.strip()}
        overlap = claimed_surnames & ref_surnames
        author_match = len(overlap) > 0

    # Year score
    year_diff = 0
    if year and ref_year:
        year_diff = abs(int(year) - int(ref_year))

    # Calculate overall confidence
    confidence = title_sim
    if not author_match:
        confidence *= 0.6
    if year_diff > 2:
        confidence *= 0.7
    elif year_diff > 0:
        confidence *= 0.9

    confidence = round(min(1.0, max(0.0, confidence)), 3)

    details = {
        "source_registry": source_db,
        "confidence_score": confidence,
        "title_similarity": round(title_sim, 3),
        "retracted": bool(retraction_reason),
        "retraction_reason": retraction_reason,
        "claimed_metadata": {"title": title, "authors": authors, "year": year, "doi": doi, "arxiv_id": arxiv_id},
        "canonical_metadata": canonical_meta,
    }

    if retraction_reason:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"RETRACTED PAPER ({source_db}): '{ref_title}'. {retraction_reason}",
            details=details,
            sources=sources,
        )

    if confidence >= 0.85:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary=f"Citation verified via {source_db} (confidence {confidence:.2f}): '{ref_title}'.",
            details=details,
            sources=sources,
        )
    elif confidence >= 0.50:
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=f"Partial metadata match found in {source_db} (confidence {confidence:.2f}). Discrepancies detected.",
            details=details,
            sources=sources,
        )
    else:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Citation rejected: severe discrepancy or hallucination (confidence {confidence:.2f}).",
            details=details,
            sources=sources,
        )


def verify_citation(
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None
) -> VerificationResult:
    """Synchronous entrypoint for verify_citation_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                verify_citation_async(title, authors, year, doi, arxiv_id)
            ).result()
    else:
        return asyncio.run(verify_citation_async(title, authors, year, doi, arxiv_id))
