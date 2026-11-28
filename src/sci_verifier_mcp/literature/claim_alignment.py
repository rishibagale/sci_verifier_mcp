"""Claim-to-abstract semantic alignment and tortured-phrase detection to prevent paper-washing."""

import asyncio
import re
from typing import Any

import httpx

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.clients import LiteratureClient

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "their", "these", "those",
    "which", "where", "when", "what", "have", "has", "been", "were", "was", "are", "is",
    "can", "could", "would", "should", "may", "might", "also", "such", "than", "then",
    "paper", "study", "shows", "show", "demonstrate", "demonstrates", "proves", "prove",
    "using", "based", "between", "through", "about", "under", "over", "onto",
}

# Known LLM/paraphrase "tortured phrases" documented by Problematic Paper Screener
TORTURED_PHRASES = [
    "bosom peril",
    "counterfeit consciousness",
    "profound neural organization",
    "irregular woodland",
    "irregular backwoods",
    "colossal information",
    "cloud figuring",
    "gullible bayes",
    "support vector apparatus",
    "flagrant error",
    "flimsy AI",
]


def _extract_content_tokens(text: str) -> set[str]:
    """Extract normalized domain tokens (length >= 3, excluding stopwords)."""
    words = re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _detect_tortured_phrases(text: str) -> list[str]:
    """Check text for known paraphrased 'tortured phrases' indicative of junk/LLM-laundered papers."""
    lowered = text.lower()
    return [phrase for phrase in TORTURED_PHRASES if phrase in lowered]


async def verify_claim_against_paper_async(
    claim: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> VerificationResult:
    """Verify whether a scientific claim actually aligns with the cited paper's title and abstract."""
    clean_claim = claim.strip()
    if not clean_claim:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty claim provided.",
            details={}
        )
    if not any([doi, arxiv_id, title]):
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="At least one of 'doi', 'arxiv_id', or 'title' must be provided.",
            details={}
        )

    lit = LiteratureClient()
    paper_meta: dict[str, Any] | None = None
    sources: list[str] = []

    if doi:
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        paper_meta = await lit.lookup_openalex_doi(clean_doi, client=client)
        if not paper_meta:
            cr = await lit.lookup_crossref_doi(clean_doi, client=client)
            if cr:
                paper_meta = {
                    "title": (cr.get("title") or [""])[0],
                    "abstract": re.sub(r"<[^>]+>", " ", cr.get("abstract") or "").strip(),
                    "is_retracted": False,
                    "url": f"https://doi.org/{cr.get('DOI')}",
                    "source": "Crossref",
                }
    elif arxiv_id:
        ax = await lit.lookup_arxiv_id(arxiv_id, client=client)
        if ax:
            paper_meta = {
                "title": ax.get("title", ""),
                "abstract": ax.get("summary", ""),
                "is_retracted": False,
                "url": ax.get("url", f"https://arxiv.org/abs/{arxiv_id}"),
                "source": "arXiv",
            }
    elif title:
        oa_items = await lit.search_openalex(title, limit=1, client=client)
        if oa_items:
            paper_meta = oa_items[0]
        else:
            s2_items = await lit.search_semantic_scholar(title, limit=1, client=client)
            if s2_items:
                paper_meta = s2_items[0]
            else:
                ax_items = await lit.search_arxiv(title, limit=1, client=client)
                if ax_items:
                    paper_meta = ax_items[0]

    if not paper_meta:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Could not resolve cited paper to verify claim alignment.",
            details={"claim": clean_claim, "doi": doi, "arxiv_id": arxiv_id, "title": title},
            sources=[]
        )

    if paper_meta.get("url"):
        sources.append(paper_meta["url"])

    if paper_meta.get("is_retracted"):
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"RETRACTED PAPER: '{paper_meta.get('title')}' cannot be used to support claims.",
            details={"claim": clean_claim, "paper": paper_meta},
            sources=sources,
        )

    ref_title = paper_meta.get("title", "")
    ref_abstract = paper_meta.get("abstract", "")
    combined_text = f"{ref_title} {ref_abstract}".strip()

    tortured_found = _detect_tortured_phrases(f"{clean_claim} {combined_text}")
    if tortured_found:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Detected suspicious 'tortured phrases' ({', '.join(tortured_found)}) indicative of LLM-laundered text.",
            details={"tortured_phrases": tortured_found, "paper_title": ref_title},
            sources=sources,
        )

    claim_tokens = _extract_content_tokens(clean_claim)
    paper_tokens = _extract_content_tokens(combined_text)

    if not claim_tokens:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Claim contains no significant domain keywords to align.",
            details={"claim": clean_claim},
            sources=sources,
        )

    matched_tokens = sorted(claim_tokens & paper_tokens)
    missing_tokens = sorted(claim_tokens - paper_tokens)
    recall = round(len(matched_tokens) / len(claim_tokens), 3)

    details = {
        "claim": clean_claim,
        "paper_title": ref_title,
        "has_abstract": bool(ref_abstract),
        "concept_overlap_score": recall,
        "matched_concepts": matched_tokens,
        "unmatched_concepts": missing_tokens,
        "source_registry": paper_meta.get("source", "unknown"),
    }

    if not ref_abstract and recall < 0.45:
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=(
                f"Abstract unavailable from registry; title-only overlap with '{ref_title}' "
                f"is {recall:.2f}. Manual check recommended."
            ),
            details=details,
            sources=sources,
        )

    if recall >= 0.45:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary=f"Claim aligns with '{ref_title}' (concept coverage {recall:.2f}).",
            details=details,
            sources=sources,
        )
    elif recall >= 0.20:
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=(
                f"Weak alignment with '{ref_title}' (concept coverage {recall:.2f}). "
                f"Verify whether the paper actually supports the specific claim."
            ),
            details=details,
            sources=sources,
        )
    else:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Potential paper-washing mismatch: cited paper '{ref_title}' shares almost no key "
                f"concepts with the claim (coverage {recall:.2f})."
            ),
            details=details,
            sources=sources,
        )


def verify_claim_against_paper(
    claim: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
) -> VerificationResult:
    """Synchronous entrypoint for verify_claim_against_paper_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                verify_claim_against_paper_async(claim, doi, arxiv_id, title),
            ).result()
    return asyncio.run(verify_claim_against_paper_async(claim, doi, arxiv_id, title))
