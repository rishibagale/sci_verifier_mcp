"""Materials science crystal structure, stoichiometry, stability, property, and prior-art verification."""

from sci_verifier_mcp.materials.mlip_stub import relax_and_score_mlip
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art
from sci_verifier_mcp.materials.properties import verify_material_properties
from sci_verifier_mcp.materials.stability import check_elastic_and_phonon_stability
from sci_verifier_mcp.materials.stoichiometry import check_stoichiometry_and_valence
from sci_verifier_mcp.materials.structure import validate_crystal_structure

__all__ = [
    "validate_crystal_structure",
    "check_stoichiometry_and_valence",
    "verify_material_properties",
    "check_novel_structure_prior_art",
    "check_elastic_and_phonon_stability",
    "relax_and_score_mlip",
]
