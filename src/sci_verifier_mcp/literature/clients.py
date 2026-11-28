"""Async HTTP clients for Crossref, OpenAlex, Semantic Scholar, arXiv, and INSPIRE-HEP."""

import asyncio
import hashlib
import json
import random
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.cache import cache

RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class _HostRateLimiter:
    """Polite per-host minimum-interval rate limiter for external scholarly APIs."""

    def __init__(self, min_interval_seconds: float = config.DEFAULT_RATE_LIMIT_INTERVAL):
        self.min_interval = min_interval_seconds
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, url: str) -> None:
        if self.min_interval <= 0:
            return
        host = urllib.parse.urlparse(url).netloc or "default"
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last_request.get(host, 0.0)
            elapsed = now - last
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request[host] = time.monotonic()


_host_limiter = _HostRateLimiter()


def make_cache_key(endpoint: str, params: dict[str, Any]) -> str:
    """Generate SHA256 cache key from endpoint and parameters."""
    raw = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LiteratureClient:
    """Multi-source literature metadata client with persistent SQLite caching."""

    def __init__(self, timeout: float = config.DEFAULT_HTTP_TIMEOUT):
        self.timeout = timeout

    async def get_cached_or_fetch(
        self,
        endpoint: str,
        params: dict[str, Any],
        headers: dict[str, str],
        client: httpx.AsyncClient | None = None,
        max_age_seconds: float = 7 * 86400.0,
        max_retries: int = config.DEFAULT_MAX_RETRIES,
        backoff_base: float = 0.5,
    ) -> Any | None:
        """Fetch from SQLite cache or make polite rate-limited HTTP GET with exponential backoff."""
        ckey = make_cache_key(endpoint, params)
        cached = cache.get(ckey, max_age_seconds=max_age_seconds)
        if cached is not None:
            return cached

        owns_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            owns_client = True

        try:
            for attempt in range(max_retries + 1):
                await _host_limiter.wait(endpoint)
                try:
                    resp = await client.get(endpoint, params=params, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError):
                    if attempt >= max_retries:
                        return None
                    delay = backoff_base * (2 ** attempt) + random.uniform(0.0, 0.2)
                    await asyncio.sleep(delay)
                    continue
                except Exception:
                    return None

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        data = resp.text
                    cache.set(ckey, endpoint, data)
                    return data
                elif resp.status_code == 404:
                    return None
                elif resp.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.replace(".", "", 1).isdigit():
                        delay = min(float(retry_after), 5.0)
                    else:
                        delay = backoff_base * (2 ** attempt) + random.uniform(0.0, 0.2)
                    await asyncio.sleep(delay)
                    continue
                else:
                    return None
        finally:
            if owns_client:
                await client.aclose()
        return None

    async def lookup_crossref_doi(self, doi: str, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        """Fetch work metadata by DOI from Crossref."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        endpoint = f"https://api.crossref.org/works/{clean_doi}"
        headers = {
            "User-Agent": f"sci-verifier-mcp/0.1.0 (mailto:{config.CROSSREF_MAILTO})",
            "Accept": "application/json",
        }
        res = await self.get_cached_or_fetch(endpoint, {}, headers, client=client)
        if res and isinstance(res, dict) and "message" in res:
            return res["message"]
        return None

    async def search_crossref_bibliographic(
        self,
        title: str,
        author: str | None = None,
        rows: int = 3,
        client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        """Search Crossref for matching works by title and author."""
        endpoint = "https://api.crossref.org/works"
        headers = {
            "User-Agent": f"sci-verifier-mcp/0.1.0 (mailto:{config.CROSSREF_MAILTO})",
            "Accept": "application/json",
        }
        params: dict[str, Any] = {"query.title": title, "rows": str(rows)}
        if author:
            params["query.author"] = author

        res = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if res and isinstance(res, dict) and "message" in res:
            return res["message"].get("items", [])
        return []

    async def lookup_arxiv_id(self, arxiv_id: str, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        """Fetch arXiv paper metadata by arXiv ID."""
        clean_id = arxiv_id.strip().removeprefix("arxiv:").removeprefix("arXiv:")
        endpoint = "http://export.arxiv.org/api/query"
        params = {"id_list": clean_id, "max_results": "1"}
        headers = {"User-Agent": "sci-verifier-mcp/0.1.0"}

        raw_xml = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if not raw_xml or not isinstance(raw_xml, str):
            return None

        return self._parse_arxiv_xml_entry(raw_xml)

    def _parse_arxiv_xml_entry(self, xml_text: str) -> dict[str, Any] | None:
        """Parse Atom XML response from arXiv."""
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return None

            title_elem = entry.find("atom:title", ns)
            title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""
            if not title or title.lower() == "error":
                return None

            summary_elem = entry.find("atom:summary", ns)
            summary = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""

            published_elem = entry.find("atom:published", ns)
            published = published_elem.text if published_elem is not None else ""
            year = int(published[:4]) if published and len(published) >= 4 and published[:4].isdigit() else None

            authors = []
            for a in entry.findall("atom:author", ns):
                name_elem = a.find("atom:name", ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())

            id_elem = entry.find("atom:id", ns)
            url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""

            return {
                "title": title,
                "summary": summary,
                "year": year,
                "authors": authors,
                "url": url,
            }
        except Exception:
            return None

    async def search_arxiv(
        self,
        query: str,
        category: str | None = None,
        limit: int = 5,
        client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        """Search arXiv by query string and optional category filter."""
        endpoint = "http://export.arxiv.org/api/query"
        search_q = f"all:{query}"
        if category:
            search_q += f" AND cat:{category}"

        params = {"search_query": search_q, "max_results": str(limit)}
        headers = {"User-Agent": "sci-verifier-mcp/0.1.0"}

        raw_xml = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if not raw_xml or not isinstance(raw_xml, str):
            return []

        results = []
        try:
            root = ET.fromstring(raw_xml)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                t_el = entry.find("atom:title", ns)
                title = t_el.text.strip().replace("\n", " ") if t_el is not None and t_el.text else ""
                if not title:
                    continue

                p_el = entry.find("atom:published", ns)
                year = int(p_el.text[:4]) if p_el is not None and p_el.text and p_el.text[:4].isdigit() else None

                auths: list[str] = []
                for a in entry.findall("atom:author", ns):
                    name_el = a.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        auths.append(name_el.text.strip())
                s_el = entry.find("atom:summary", ns)
                id_el = entry.find("atom:id", ns)

                results.append({
                    "title": title,
                    "authors": auths,
                    "year": year,
                    "abstract": s_el.text.strip() if s_el is not None and s_el.text else "",
                    "url": id_el.text.strip() if id_el is not None and id_el.text else "",
                    "source": "arXiv",
                })
        except Exception:
            pass
        return results

    async def search_semantic_scholar(
        self,
        query: str,
        limit: int = 5,
        client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        """Search papers via Semantic Scholar Graph API."""
        endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": str(limit),
            "fields": "title,authors,year,abstract,tldr,citationCount,url,externalIds",
        }
        headers = {"User-Agent": "sci-verifier-mcp/0.1.0"}
        if config.SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = config.SEMANTIC_SCHOLAR_API_KEY

        res = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if res and isinstance(res, dict) and "data" in res:
            items = []
            for paper in res.get("data", []):
                items.append({
                    "title": paper.get("title", ""),
                    "authors": [a.get("name", "") for a in paper.get("authors", [])],
                    "year": paper.get("year"),
                    "abstract": (paper.get("tldr") or {}).get("text") or paper.get("abstract", ""),
                    "citation_count": paper.get("citationCount", 0),
                    "url": paper.get("url") or f"https://doi.org/{paper.get('externalIds', {}).get('DOI', '')}",
                    "source": "Semantic Scholar",
                })
            return items
        return []

    async def search_inspire_hep(
        self,
        query: str,
        limit: int = 5,
        client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        """Search High Energy Physics and Theoretical Physics literature via INSPIRE-HEP."""
        endpoint = "https://inspirehep.net/api/literature"
        params = {"q": query, "size": str(limit)}
        headers = {"User-Agent": "sci-verifier-mcp/0.1.0", "Accept": "application/json"}

        res = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if res and isinstance(res, dict) and "hits" in res:
            hits = res.get("hits", {}).get("hits", [])
            items = []
            for h in hits:
                meta = h.get("metadata", {})
                titles = meta.get("titles", [{}])
                title = titles[0].get("title", "") if titles else ""
                auths = [a.get("full_name", "") for a in meta.get("authors", [])]
                year = meta.get("earliest_date", "")[:4]
                year_int = int(year) if year.isdigit() else None
                rec_id = h.get("id", "")
                items.append({
                    "title": title,
                    "authors": auths,
                    "year": year_int,
                    "abstract": (meta.get("abstracts", [{}])[0].get("value", "") if meta.get("abstracts") else ""),
                    "citation_count": meta.get("citation_count", 0),
                    "url": f"https://inspirehep.net/literature/{rec_id}" if rec_id else "",
                    "source": "INSPIRE-HEP",
                })
            return items
        return []

    @staticmethod
    def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
        """Reconstruct plain-text abstract from OpenAlex inverted index format."""
        if not inverted_index or not isinstance(inverted_index, dict):
            return ""
        positions: list[tuple[int, str]] = []
        for word, idxs in inverted_index.items():
            for idx in idxs:
                positions.append((idx, word))
        positions.sort(key=lambda pair: pair[0])
        return " ".join(word for _, word in positions)

    def _normalize_openalex_work(self, work: dict[str, Any]) -> dict[str, Any]:
        """Normalize an OpenAlex work record into canonical metadata."""
        authorships = work.get("authorships") or []
        authors = [
            (a.get("author") or {}).get("display_name", "").strip()
            for a in authorships
            if (a.get("author") or {}).get("display_name")
        ]
        doi_url = work.get("doi") or ""
        primary_loc = work.get("primary_location") or {}
        landing_url = primary_loc.get("landing_page_url") or doi_url or work.get("id", "")
        abstract = self.reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        return {
            "title": (work.get("title") or work.get("display_name") or "").strip(),
            "authors": authors,
            "year": work.get("publication_year"),
            "publication_date": work.get("publication_date"),
            "doi": doi_url.removeprefix("https://doi.org/").removeprefix("http://doi.org/") if doi_url else None,
            "is_retracted": bool(work.get("is_retracted", False)),
            "citation_count": work.get("cited_by_count", 0),
            "abstract": abstract,
            "url": landing_url,
            "source": "OpenAlex",
        }

    async def lookup_openalex_doi(self, doi: str, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        """Fetch work metadata and retraction status by DOI from OpenAlex."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        endpoint = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
        params: dict[str, Any] = {}
        if config.OPENALEX_API_KEY:
            params["api_key"] = config.OPENALEX_API_KEY
        elif config.CROSSREF_MAILTO:
            params["mailto"] = config.CROSSREF_MAILTO
        headers = {"User-Agent": f"sci-verifier-mcp/0.1.0 (mailto:{config.CROSSREF_MAILTO})", "Accept": "application/json"}

        res = await self.get_cached_or_fetch(endpoint, params, headers, client=client)
        if res and isinstance(res, dict) and (res.get("id") or res.get("title")):
            return self._normalize_openalex_work(res)
        return None

    async def search_openalex(
        self,
        query: str,
        limit: int = 5,
        sort: str | None = None,
        from_publication_date: str | None = None,
        client: httpx.AsyncClient | None = None,
        max_age_seconds: float = 7 * 86400.0,
    ) -> list[dict[str, Any]]:
        """Search works via OpenAlex REST API."""
        endpoint = "https://api.openalex.org/works"
        params: dict[str, Any] = {"search": query, "per-page": str(limit)}
        if sort:
            params["sort"] = sort
        if from_publication_date:
            params["filter"] = f"from_publication_date:{from_publication_date}"
        if config.OPENALEX_API_KEY:
            params["api_key"] = config.OPENALEX_API_KEY
        elif config.CROSSREF_MAILTO:
            params["mailto"] = config.CROSSREF_MAILTO

        headers = {"User-Agent": f"sci-verifier-mcp/0.1.0 (mailto:{config.CROSSREF_MAILTO})", "Accept": "application/json"}
        res = await self.get_cached_or_fetch(
            endpoint, params, headers, client=client, max_age_seconds=max_age_seconds
        )
        if res and isinstance(res, dict) and "results" in res:
            return [self._normalize_openalex_work(w) for w in res.get("results", [])]
        return []
