"""Concurrent bibliography auditing for BibTeX strings and structured citation lists."""

import asyncio
import re
from typing import Any
import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.citation_verifier import verify_citation_async


def parse_bibtex_string(bibtex_str: str) -> list[dict[str, Any]]:
    """Parse BibTeX string into a list of normalized citation dicts."""
    clean = bibtex_str.strip()
    try:
        import bibtexparser
        # Support bibtexparser v1 and v2
        if hasattr(bibtexparser, "parse_string"):
            library = bibtexparser.parse_string(clean)
            entries = []
            for entry in library.entries:
                fields = {f.key.lower(): str(f.value).strip("{}'\" ") for f in entry.fields}
                auth_str = fields.get("author", "")
                auths = [a.strip() for a in auth_str.split(" and ") if a.strip()]
                year_val = fields.get("year", "")
                entries.append({
                    "key": entry.key,
                    "title": fields.get("title", ""),
                    "authors": auths,
                    "year": int(year_val) if year_val.isdigit() else None,
                    "doi": fields.get("doi"),
                    "arxiv_id": fields.get("eprint") or fields.get("arxivid"),
                })
            if entries:
                return entries
    except Exception:
        pass

    # Fallback regex parser for BibTeX
    entry_pattern = r"@(\w+)\s*\{\s*([^,]+),([^@]*)\}"
    matches = re.findall(entry_pattern, clean, re.DOTALL)
    entries = []

    for entry_type, key, body in matches:
        title_m = re.search(r"title\s*=\s*[\"{](.*?)[\"}]", body, re.IGNORECASE)
        author_m = re.search(r"author\s*=\s*[\"{](.*?)[\"}]", body, re.IGNORECASE)
        year_m = re.search(r"year\s*=\s*[\"{]?(\d{4})[\"}]?", body, re.IGNORECASE)
        doi_m = re.search(r"doi\s*=\s*[\"{](.*?)[\"}]", body, re.IGNORECASE)
        arxiv_m = re.search(r"(?:eprint|arxivid)\s*=\s*[\"{](.*?)[\"}]", body, re.IGNORECASE)

        auths = [a.strip() for a in author_m.group(1).split(" and ")] if author_m else []
        entries.append({
            "key": key.strip(),
            "title": title_m.group(1).strip() if title_m else "",
            "authors": auths,
            "year": int(year_m.group(1)) if year_m else None,
            "doi": doi_m.group(1).strip() if doi_m else None,
            "arxiv_id": arxiv_m.group(1).strip() if arxiv_m else None,
        })

    return entries


async def audit_bibliography_async(
    entries: str | list[dict[str, Any]],
    concurrency_limit: int = config.DEFAULT_CONCURRENCY
) -> VerificationResult:
    """Audit a bibliography (BibTeX or list of dicts) concurrently with bounded rate limiting."""
    if isinstance(entries, str):
        parsed_entries = parse_bibtex_string(entries)
    elif isinstance(entries, list):
        parsed_entries = entries
    else:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Expected BibTeX string or list of citation dictionaries.",
            details={}
        )

    if not parsed_entries:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="No valid citation entries found to audit.",
            details={}
        )

    sem = asyncio.Semaphore(concurrency_limit)
    per_entry_reports: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=config.DEFAULT_HTTP_TIMEOUT) as client:
        async def check_one(item: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                res = await verify_citation_async(
                    title=item.get("title"),
                    authors=item.get("authors"),
                    year=item.get("year"),
                    doi=item.get("doi"),
                    arxiv_id=item.get("arxiv_id"),
                    client=client
                )
                return {
                    "entry_key": item.get("key") or item.get("title", "unknown"),
                    "status": res.status.value,
                    "summary": res.summary,
                    "confidence": res.details.get("confidence_score", 0.0),
                    "sources": res.sources,
                }

        tasks = [check_one(entry) for entry in parsed_entries]
        per_entry_reports = await asyncio.gather(*tasks)

    # Compute totals
    total = len(per_entry_reports)
    verified_cnt = sum(1 for r in per_entry_reports if r["status"] == "verified")
    partial_cnt = sum(1 for r in per_entry_reports if r["status"] == "partial_match")
    failed_cnt = sum(1 for r in per_entry_reports if r["status"] == "failed")
    error_cnt = sum(1 for r in per_entry_reports if r["status"] == "error")

    all_sources = []
    for r in per_entry_reports:
        all_sources.extend(r.get("sources", []))

    details = {
        "total_citations": total,
        "verified_count": verified_cnt,
        "partial_match_count": partial_cnt,
        "failed_count": failed_cnt,
        "error_count": error_cnt,
        "reports": per_entry_reports,
    }

    if failed_cnt > 0:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Bibliography audit flagged {failed_cnt} hallucinated/failed citation(s) "
                f"out of {total} total entries."
            ),
            details=details,
            sources=list(dict.fromkeys(all_sources)),
        )
    elif partial_cnt > 0:
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=(
                f"Bibliography audit passed with {partial_cnt} partial metadata match(es) "
                f"and {verified_cnt} fully verified entry/entries."
            ),
            details=details,
            sources=list(dict.fromkeys(all_sources)),
        )
    else:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary=f"All {total} citation(s) verified successfully against registry databases.",
            details=details,
            sources=list(dict.fromkeys(all_sources)),
        )


def audit_bibliography(entries: str | list[dict[str, Any]]) -> VerificationResult:
    """Synchronous entrypoint for audit_bibliography_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, audit_bibliography_async(entries)).result()
    else:
        return asyncio.run(audit_bibliography_async(entries))
