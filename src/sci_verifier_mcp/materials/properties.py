"""Materials Project API client for verifying computed properties (band gap, stability, energy above hull)."""

from typing import Any
import httpx

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


async def verify_material_properties_async(
    formula_or_mp_id: str,
    claimed_properties: dict[str, Any] | None = None,
    api_key: str | None = None
) -> VerificationResult:
    """Query Materials Project API to verify claimed material properties against computed references."""
    key = api_key or config.MP_API_KEY
    if not key:
        return VerificationResult(
            status=VerificationStatus.UNAVAILABLE,
            summary=(
                "Materials Project API key is not configured. "
                "Set the MP_API_KEY environment variable to verify material properties."
            ),
            details={
                "help": "Obtain a free Materials Project API key at https://next-gen.materialsproject.org/api",
                "input": formula_or_mp_id,
            }
        )

    clean_id = formula_or_mp_id.strip()
    headers = {"X-API-KEY": key, "Accept": "application/json"}
    base_url = "https://api.materialsproject.org/materials/summary/"

    params: dict[str, str] = {
        "_fields": "material_id,formula_pretty,band_gap,formation_energy_per_atom,energy_above_hull,is_stable,symmetry,ordering",
        "_limit": "5",
    }

    if clean_id.lower().startswith("mp-") or clean_id.lower().startswith("mvc-"):
        params["material_ids"] = clean_id
    else:
        params["formula"] = clean_id

    try:
        async with httpx.AsyncClient(timeout=config.DEFAULT_HTTP_TIMEOUT) as client:
            resp = await client.get(base_url, params=params, headers=headers)
            if resp.status_code == 403 or resp.status_code == 401:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary="Materials Project API key is invalid or unauthorized.",
                    details={"status_code": resp.status_code}
                )
            elif resp.status_code != 200:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Materials Project API returned error status {resp.status_code}.",
                    details={"response": resp.text[:300]}
                )

            data = resp.json()
            entries = data.get("data", [])

    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Network error while querying Materials Project: {e}",
            details={"error": str(e)}
        )

    if not entries:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"No matching materials found in Materials Project for '{clean_id}'.",
            details={"query": clean_id}
        )

    entry = entries[0]
    mp_id = entry.get("material_id", "")
    sources = [f"https://next-gen.materialsproject.org/materials/{mp_id}"] if mp_id else []

    # If no claimed properties specified, return canonical properties
    if not claimed_properties:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary=f"Retrieved reference properties for {entry.get('formula_pretty')} ({mp_id}).",
            details={"reference_data": entry},
            sources=sources,
        )

    # Compare claimed properties with reference values
    discrepancies: dict[str, Any] = {}
    tolerances = {
        "band_gap": 0.15,  # eV
        "formation_energy_per_atom": 0.05,  # eV/atom
        "energy_above_hull": 0.02,  # eV/atom
    }

    for prop, claimed_val in claimed_properties.items():
        prop_key = prop.lower()
        if prop_key in entry:
            ref_val = entry[prop_key]
            if isinstance(claimed_val, (int, float)) and isinstance(ref_val, (int, float)):
                diff = abs(float(claimed_val) - float(ref_val))
                tol = tolerances.get(prop_key, 0.05)
                if diff > tol:
                    discrepancies[prop] = {
                        "claimed": claimed_val,
                        "reference": ref_val,
                        "difference": diff,
                        "tolerance": tol,
                    }
            elif isinstance(claimed_val, bool) and isinstance(ref_val, bool):
                if claimed_val != ref_val:
                    discrepancies[prop] = {"claimed": claimed_val, "reference": ref_val}
            elif str(claimed_val).strip().lower() != str(ref_val).strip().lower():
                discrepancies[prop] = {"claimed": claimed_val, "reference": ref_val}

        elif prop_key in ("spacegroup", "space_group", "spacegroup_number"):
            sym = entry.get("symmetry", {})
            ref_num = sym.get("number")
            ref_sym = sym.get("symbol")
            claimed_str = str(claimed_val).strip().lower()
            if claimed_str != str(ref_num) and claimed_str != str(ref_sym).lower():
                discrepancies[prop] = {
                    "claimed": claimed_val,
                    "reference": f"{ref_sym} (#{ref_num})",
                }

    if discrepancies:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Claimed properties disagree with Materials Project reference data for {mp_id}.",
            details={
                "discrepancies": discrepancies,
                "reference_data": entry,
                "claimed_properties": claimed_properties,
            },
            sources=sources,
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=f"Claimed properties verified against Materials Project ({mp_id}).",
        details={
            "matched_properties": claimed_properties,
            "reference_entry": entry,
        },
        sources=sources,
    )


def verify_material_properties(
    formula_or_mp_id: str,
    claimed_properties: dict[str, Any] | None = None,
    api_key: str | None = None
) -> VerificationResult:
    """Synchronous wrapper for verify_material_properties_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an active event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                verify_material_properties_async(formula_or_mp_id, claimed_properties, api_key)
            ).result()
    else:
        return asyncio.run(
            verify_material_properties_async(formula_or_mp_id, claimed_properties, api_key)
        )
