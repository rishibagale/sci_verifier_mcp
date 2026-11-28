"""Unit tests for materials science structure, stoichiometry, and property tools."""

import httpx
import pytest
import respx

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art_async
from sci_verifier_mcp.materials.properties import verify_material_properties_async
from sci_verifier_mcp.materials.stoichiometry import check_stoichiometry_and_valence
from sci_verifier_mcp.materials.structure import validate_crystal_structure

SAMPLE_VALID_CIF = """
data_Si
_cell_length_a                   5.43
_cell_length_b                   5.43
_cell_length_c                   5.43
_cell_angle_alpha                90.00
_cell_angle_beta                 90.00
_cell_angle_gamma                90.00
_symmetry_space_group_name_H-M   'F d -3 m'
_space_group_IT_number           227

loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Si1 Si 0.00000 0.00000 0.00000
Si2 Si 0.00000 0.50000 0.50000
Si3 Si 0.50000 0.00000 0.50000
Si4 Si 0.50000 0.50000 0.00000
Si5 Si 0.25000 0.25000 0.25000
Si6 Si 0.25000 0.75000 0.75000
Si7 Si 0.75000 0.25000 0.75000
Si8 Si 0.75000 0.75000 0.25000
"""

SAMPLE_MISMATCH_SG_CIF = """
data_Si_incomplete
_cell_length_a                   5.43
_cell_length_b                   5.43
_cell_length_c                   5.43
_cell_angle_alpha                90.00
_cell_angle_beta                 90.00
_cell_angle_gamma                90.00

loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Si1 Si 0.00000 0.00000 0.00000
Si2 Si 0.25000 0.25000 0.25000
"""

SAMPLE_OVERLAPPING_CIF = """
data_broken
_cell_length_a                   4.00
_cell_length_b                   4.00
_cell_length_c                   4.00
_cell_angle_alpha                90.00
_cell_angle_beta                 90.00
_cell_angle_gamma                90.00

loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.00000 0.00000 0.00000
C2 C 0.01000 0.00000 0.00000
"""


def test_valid_crystal_structure():
    res = validate_crystal_structure(SAMPLE_VALID_CIF, format="cif", claimed_spacegroup=227)
    assert res.status == VerificationStatus.VERIFIED
    assert "Crystal structure valid" in res.summary
    assert res.details["computed_spacegroup_number"] == 227


def test_spacegroup_mismatch_rejection():
    # Incomplete 2-atom cubic cell has R3m (#160), not Fd-3m (#227)
    res = validate_crystal_structure(SAMPLE_MISMATCH_SG_CIF, format="cif", claimed_spacegroup=227)
    assert res.status == VerificationStatus.FAILED
    assert "symmetry mismatch" in res.summary.lower()


def test_overlapping_atoms_rejection():
    # Distance between (0, 0, 0) and (0.01*4, 0, 0) is 0.04 Angstroms (< 0.7 A)
    res = validate_crystal_structure(SAMPLE_OVERLAPPING_CIF, format="cif")
    assert res.status == VerificationStatus.FAILED
    assert "overlapping atoms" in res.summary.lower()
    assert res.details["min_interatomic_distance_angstrom"] < 0.7


def test_stoichiometry_perovskite():
    res = check_stoichiometry_and_valence("BaTiO3")
    assert res.status == VerificationStatus.VERIFIED
    assert "plausible charge neutrality" in res.summary


def test_stoichiometry_charge_violation():
    # Na2Cl has no neutral combination with common oxidation states (Na=+1, Cl=-1)
    res = check_stoichiometry_and_valence("Na2Cl")
    assert res.status == VerificationStatus.FAILED
    assert "violates charge neutrality" in res.summary


def test_reaction_mass_balance_valid():
    res = check_stoichiometry_and_valence("2 H2 + O2 -> 2 H2O")
    assert res.status == VerificationStatus.VERIFIED
    assert "balanced" in res.summary.lower()


def test_reaction_mass_balance_unbalanced():
    # Unbalanced: H2 + O2 -> H2O (missing 1 O)
    res = check_stoichiometry_and_valence("H2 + O2 -> H2O")
    assert res.status == VerificationStatus.FAILED
    assert "unbalanced" in res.summary.lower()
    assert "O" in res.details["unbalanced_elements"]


@pytest.mark.asyncio
async def test_verify_material_properties_missing_api_key():
    res = await verify_material_properties_async("mp-149", api_key="")
    assert res.status == VerificationStatus.UNAVAILABLE
    assert "MP_API_KEY" in res.summary


@pytest.mark.asyncio
@respx.mock
async def test_verify_material_properties_matched():
    # Mock Materials Project API response for mp-149
    respx.get("https://api.materialsproject.org/materials/summary/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "material_id": "mp-149",
                        "formula_pretty": "Si",
                        "band_gap": 1.14,
                        "formation_energy_per_atom": 0.0,
                        "energy_above_hull": 0.0,
                        "is_stable": True,
                        "symmetry": {"number": 227, "symbol": "Fd-3m"},
                    }
                ]
            }
        )
    )

    claimed = {
        "band_gap": 1.15,
        "is_stable": True,
        "spacegroup_number": 227,
    }
    res = await verify_material_properties_async("mp-149", claimed_properties=claimed, api_key="test_key")
    assert res.status == VerificationStatus.VERIFIED
    assert "verified against Materials Project" in res.summary


@pytest.mark.asyncio
@respx.mock
async def test_verify_material_properties_discrepancy():
    respx.get("https://api.materialsproject.org/materials/summary/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "material_id": "mp-149",
                        "formula_pretty": "Si",
                        "band_gap": 1.14,
                        "formation_energy_per_atom": 0.0,
                        "energy_above_hull": 0.0,
                        "is_stable": True,
                        "symmetry": {"number": 227, "symbol": "Fd-3m"},
                    }
                ]
            }
        )
    )

    # Claim wide band gap 3.5 eV for Silicon (discrepancy!)
    claimed = {"band_gap": 3.5}
    res = await verify_material_properties_async("mp-149", claimed_properties=claimed, api_key="test_key")
    assert res.status == VerificationStatus.FAILED
    assert "disagree with Materials Project" in res.summary
    assert "band_gap" in res.details["discrepancies"]


@pytest.mark.asyncio
@respx.mock
async def test_optimade_novelty_check():
    # Mock OPTIMADE endpoints returning 0 matches
    respx.get("https://optimade.materialsproject.org/v1/structures").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get("https://www.crystallography.net/cod/optimade/v1/structures").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    res = await check_novel_structure_prior_art_async("Zr3Fe5Si2")
    assert res.status == VerificationStatus.VERIFIED
    assert "Novelty claim is supported" in res.summary
