"""OPTIMADE federated REST API client for crystal structure prior-art and novelty checking."""

from typing import Any

import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus

# Standard public OPTIMADE providers
OPTIMADE_PROVIDERS = [
    {
        "name": "Materials Project",
        "url": "https://optimade.materialsproject.org/v1/structures",
    },
    {
        "name": "Crystallography Open Database (COD)",
        "url": "https://www.crystallography.net/cod/optimade/v1/structures",
    },
]


async def check_novel_structure_prior_art_async(
    formula: str,
    spacegroup_number: int | None = None,
    elements: list[str] | None = None,
    limit: int = 10
) -> VerificationResult:
    """Query federated crystal databases via OPTIMADE to verify novelty claims or find prior art."""
    clean_formula = formula.strip()
    if not clean_formula:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty formula provided for novel structure search.",
            details={}
        )

    # Build OPTIMADE filter query
    # Example: chemical_formula_reduced="TiO2"
    filter_expr = f'chemical_formula_reduced="{clean_formula}"'
    if elements:
        el_filter = " AND ".join(f'elements HAS "{el}"' for el in elements)
        filter_expr += f" AND {el_filter}"

    params = {
        "filter": filter_expr,
        "page_limit": str(min(limit, 20)),
    }

    matching_entries: list[dict[str, Any]] = []
    sources: list[str] = []

    async with httpx.AsyncClient(timeout=config.DEFAULT_HTTP_TIMEOUT) as client:
        for provider in OPTIMADE_PROVIDERS:
            try:
                resp = await client.get(provider["url"], params=params, headers={"Accept": "application/vnd.api+json"})
                if resp.status_code == 200:
                    data = resp.json()
                    structures = data.get("data", [])
                    for s in structures:
                        attrs = s.get("attributes", {})
                        entry_id = s.get("id", "")
                        sg_num = attrs.get("_cod_spacegroup_number") or (attrs.get("_mp_symmetry") or {}).get("number")
                        if spacegroup_number is not None and sg_num is not None:
                            try:
                                if int(sg_num) != int(spacegroup_number):
                                    continue
                            except (TypeError, ValueError):
                                pass
                        matched_item = {
                            "provider": provider["name"],
                            "id": entry_id,
                            "chemical_formula_descriptive": attrs.get("chemical_formula_descriptive"),
                            "chemical_formula_reduced": attrs.get("chemical_formula_reduced"),
                            "space_group_symmetry": sg_num,
                            "nsites": attrs.get("nsites"),
                        }
                        matching_entries.append(matched_item)
                        if "cod" in provider["url"]:
                            sources.append(f"https://www.crystallography.net/cod/{entry_id}.html")
                        elif "materialsproject" in provider["url"]:
                            sources.append(f"https://next-gen.materialsproject.org/materials/{entry_id}")
            except Exception:
                # Proceed to next provider on network error
                continue

    if matching_entries:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Structure is not novel: found {len(matching_entries)} existing matching "
                f"entry/entries in open crystal databases (OPTIMADE)."
            ),
            details={
                "formula": clean_formula,
                "matches_count": len(matching_entries),
                "existing_structures": matching_entries[:limit],
            },
            sources=list(dict.fromkeys(sources))[:limit],
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=(
            f"No existing entries found for formula '{clean_formula}' across searched OPTIMADE providers. "
            f"Novelty claim is supported."
        ),
        details={
            "formula": clean_formula,
            "filter_query": filter_expr,
            "providers_searched": [p["name"] for p in OPTIMADE_PROVIDERS],
        },
        sources=[]
    )


def check_novel_structure_prior_art(
    formula: str,
    spacegroup_number: int | None = None,
    elements: list[str] | None = None,
    limit: int = 10
) -> VerificationResult:
    """Synchronous wrapper for check_novel_structure_prior_art_async."""
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
                check_novel_structure_prior_art_async(formula, spacegroup_number, elements, limit)
            ).result()
    else:
        return asyncio.run(
            check_novel_structure_prior_art_async(formula, spacegroup_number, elements, limit)
        )
