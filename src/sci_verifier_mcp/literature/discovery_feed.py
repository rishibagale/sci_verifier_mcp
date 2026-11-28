"""Live frontier research feed across recent arXiv submissions and OpenAlex works."""

import asyncio
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.literature.clients import LiteratureClient

DOMAIN_TO_ARXIV_CAT = {
    "math": "math.*",
    "physics": "physics.*",
    "hep": "hep-th",
    "materials": "cond-mat.mtrl-sci",
    "ai_science": "cs.AI",
}


async def track_recent_discoveries_async(
    topic_or_domain: str,
    days: int = 7,
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
) -> VerificationResult:
    """Fetch recent discoveries and preprints from arXiv and OpenAlex with a 6-hour cache TTL."""
    clean_topic = topic_or_domain.strip()
    if not clean_topic:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty topic_or_domain provided.",
            details={}
        )

    lit = LiteratureClient()
    since_date = (datetime.now(UTC) - timedelta(days=max(1, days))).strftime("%Y-%m-%d")
    ttl_seconds = 6 * 3600.0

    lowered = clean_topic.lower()
    arxiv_cat = DOMAIN_TO_ARXIV_CAT.get(lowered)

    owns_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=config.DEFAULT_HTTP_TIMEOUT)
        owns_client = True

    items: list[dict[str, Any]] = []
    try:
        # 1. Query arXiv sorted by submittedDate descending
        search_q = f"cat:{arxiv_cat}" if arxiv_cat else f"all:{clean_topic}"
        ax_params = {
            "search_query": search_q,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(limit),
        }
        raw_xml = await lit.get_cached_or_fetch(
            "http://export.arxiv.org/api/query",
            ax_params,
            {"User-Agent": "sci-verifier-mcp/0.1.0"},
            client=client,
            max_age_seconds=ttl_seconds,
        )
        if raw_xml and isinstance(raw_xml, str):
            try:
                root = ET.fromstring(raw_xml)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns):
                    t_el = entry.find("atom:title", ns)
                    title = t_el.text.strip().replace("\n", " ") if t_el is not None and t_el.text else ""
                    if not title:
                        continue
                    p_el = entry.find("atom:published", ns)
                    pub_date = p_el.text[:10] if p_el is not None and p_el.text else ""
                    auths: list[str] = []
                    for a in entry.findall("atom:author", ns):
                        name_el = a.find("atom:name", ns)
                        if name_el is not None and name_el.text:
                            auths.append(name_el.text.strip())
                    s_el = entry.find("atom:summary", ns)
                    id_el = entry.find("atom:id", ns)
                    items.append({
                        "title": title,
                        "authors": auths[:5],
                        "publication_date": pub_date,
                        "abstract": (s_el.text.strip()[:400] if s_el is not None and s_el.text else ""),
                        "url": id_el.text.strip() if id_el is not None and id_el.text else "",
                        "source": "arXiv",
                    })
            except Exception:
                pass

        # 2. Query OpenAlex for recent works since `since_date`
        oa_query = clean_topic if not arxiv_cat else lowered.replace("_", " ")
        oa_items = await lit.search_openalex(
            query=oa_query,
            limit=limit,
            sort="publication_date:desc",
            from_publication_date=since_date,
            client=client,
            max_age_seconds=ttl_seconds,
        )
        for w in oa_items:
            items.append({
                "title": w.get("title", ""),
                "authors": (w.get("authors") or [])[:5],
                "publication_date": w.get("publication_date") or str(w.get("year") or ""),
                "abstract": (w.get("abstract") or "")[:400],
                "citation_count": w.get("citation_count", 0),
                "url": w.get("url", ""),
                "source": "OpenAlex",
            })
    finally:
        if owns_client:
            await client.aclose()

    # Deduplicate by normalized title
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        norm = " ".join(item.get("title", "").lower().split())
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(item)

    deduped.sort(key=lambda x: x.get("publication_date", ""), reverse=True)
    top = deduped[:limit]
    sources = [x["url"] for x in top if x.get("url")]

    return VerificationResult(
        status=VerificationStatus.VERIFIED if top else VerificationStatus.PARTIAL_MATCH,
        summary=f"Retrieved {len(top)} recent discovery/paper(s) for '{clean_topic}' (since {since_date}).",
        details={
            "topic_or_domain": clean_topic,
            "since_date": since_date,
            "total_results": len(top),
            "papers": top,
        },
        sources=sources,
    )


def track_recent_discoveries(
    topic_or_domain: str,
    days: int = 7,
    limit: int = 10,
) -> VerificationResult:
    """Synchronous entrypoint for track_recent_discoveries_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                track_recent_discoveries_async(topic_or_domain, days, limit),
            ).result()
    return asyncio.run(track_recent_discoveries_async(topic_or_domain, days, limit))
