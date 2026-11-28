"""Unit tests for Phase 2 features and original-prompt gap closures."""

import time

import httpx
import pytest
import respx

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.core.security import ExecutionTimeoutError, run_with_timeout
from sci_verifier_mcp.literature.clients import LiteratureClient
from sci_verifier_mcp.materials.mlip_stub import relax_and_score_mlip
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art_async
from sci_verifier_mcp.materials.stability import check_elastic_and_phonon_stability
from sci_verifier_mcp.materials.structure import validate_crystal_structure
from sci_verifier_mcp.proofs.lean_runner import _extract_goal_states, verify_lean4_proof
from sci_verifier_mcp.proofs.premise_search import search_lean_premises_async
from sci_verifier_mcp.server import mcp

SAMPLE_POSCAR_SI = """Silicon Diamond
1.0
5.43 0.0 0.0
0.0 5.43 0.0
0.0 0.0 5.43
Si
8
Direct
0.00 0.00 0.00
0.00 0.50 0.50
0.50 0.00 0.50
0.50 0.50 0.00
0.25 0.25 0.25
0.25 0.75 0.75
0.75 0.25 0.75
0.75 0.75 0.25
"""

SAMPLE_LOW_DENSITY_CIF = """
data_void
_cell_length_a                   30.0
_cell_length_b                   30.0
_cell_length_c                   30.0
_cell_angle_alpha                90.0
_cell_angle_beta                 90.0
_cell_angle_gamma                90.0
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Li1 Li 0.0 0.0 0.0
"""


def test_run_with_timeout_guard():
    def slow():
        time.sleep(0.3)
        return 42

    with pytest.raises(ExecutionTimeoutError):
        run_with_timeout(slow, 0.05)


@pytest.mark.asyncio
@respx.mock
async def test_http_429_exponential_backoff():
    url = "https://api.crossref.org/works/10.5555/backoff-test-unique"
    route = respx.get(url).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0.01"}),
            httpx.Response(200, json={"message": {"title": ["Recovered After Backoff"]}}),
        ]
    )
    lit = LiteratureClient()
    data = await lit.get_cached_or_fetch(
        url, {}, {}, max_age_seconds=0.0, max_retries=2, backoff_base=0.01
    )
    assert route.call_count == 2
    assert data["message"]["title"][0] == "Recovered After Backoff"


def test_poscar_parsing_and_spglib_symmetry():
    res = validate_crystal_structure(SAMPLE_POSCAR_SI, format="poscar", claimed_spacegroup=227)
    assert res.status == VerificationStatus.VERIFIED
    assert res.details["computed_spacegroup_number"] == 227


def test_unphysical_low_density_rejection():
    res = validate_crystal_structure(SAMPLE_LOW_DENSITY_CIF, format="cif")
    assert res.status == VerificationStatus.FAILED
    assert "density" in res.summary.lower()


@pytest.mark.asyncio
@respx.mock
async def test_optimade_spacegroup_filtering():
    respx.get("https://optimade.materialsproject.org/v1/structures").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "mp-100",
                        "attributes": {
                            "chemical_formula_reduced": "TiO2",
                            "_mp_symmetry": {"number": 136},
                            "nsites": 6,
                        },
                    }
                ]
            },
        )
    )
    respx.get("https://www.crystallography.net/cod/optimade/v1/structures").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    # Searching for spacegroup 227 should ignore mp-100 (sg 136) -> novel for sg 227
    novel_sg = await check_novel_structure_prior_art_async("TiO2", spacegroup_number=227)
    assert novel_sg.status == VerificationStatus.VERIFIED

    # Searching for spacegroup 136 finds mp-100 -> prior art exists
    existing_sg = await check_novel_structure_prior_art_async("TiO2", spacegroup_number=136)
    assert existing_sg.status == VerificationStatus.FAILED


@pytest.mark.asyncio
@respx.mock
async def test_search_lean_premises_loogle():
    respx.get("https://loogle.lean-lang.org/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "name": "Nat.add_comm",
                        "type": "∀ (n m : ℕ), n + m = m + n",
                        "module": "Init.Data.Nat.Basic",
                        "doc": "Commutativity of addition.",
                    }
                ]
            },
        )
    )

    res = await search_lean_premises_async("Nat.add_comm", backend="loogle")
    assert res.status == VerificationStatus.VERIFIED
    assert res.details["premises"][0]["name"] == "Nat.add_comm"


def test_lean_goal_state_extraction_and_invalid_project_dir():
    goals = _extract_goal_states([
        {"line": 4, "column": 2, "severity": "error", "message": "unsolved goals\nx : Nat\n⊢ x + 0 = x"}
    ])
    assert len(goals) == 1
    assert "⊢ x + 0 = x" in goals[0]["goal_state"]

    res = verify_lean4_proof("theorem t : True := trivial", project_dir="nonexistent_lake_dir_xyz")
    assert res.status in (VerificationStatus.ERROR, VerificationStatus.UNAVAILABLE)


def test_born_elastic_and_phonon_stability():
    # Cubic Si-like elastic tensor (C11=166, C12=64, C44=80 GPa) -> Born stable
    c_valid = [
        [166.0, 64.0, 64.0, 0.0, 0.0, 0.0],
        [64.0, 166.0, 64.0, 0.0, 0.0, 0.0],
        [64.0, 64.0, 166.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 80.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 80.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 80.0],
    ]
    ok = check_elastic_and_phonon_stability(
        elastic_tensor_gpa=c_valid,
        phonon_frequencies_thz=[0.0, 4.2, 9.5, 15.1],
    )
    assert ok.status == VerificationStatus.VERIFIED
    assert ok.details["elastic"]["born_stable"] is True

    # Negative C44 -> Born unstable + imaginary phonon mode
    c_unstable = [row[:] for row in c_valid]
    c_unstable[3][3] = -15.0
    bad = check_elastic_and_phonon_stability(
        elastic_tensor_gpa=c_unstable,
        phonon_frequencies_thz=[-2.5, 4.0, 8.0],
    )
    assert bad.status == VerificationStatus.FAILED
    assert bad.details["elastic"]["born_stable"] is False
    assert bad.details["phonon"]["dynamically_stable"] is False


def test_mlip_graceful_fallback():
    res = relax_and_score_mlip(SAMPLE_POSCAR_SI, format="poscar", model="mace")
    assert res.status in (VerificationStatus.UNAVAILABLE, VerificationStatus.VERIFIED, VerificationStatus.PARTIAL_MATCH)


def test_streamable_http_app_builds():
    app = mcp.streamable_http_app()
    assert app is not None
