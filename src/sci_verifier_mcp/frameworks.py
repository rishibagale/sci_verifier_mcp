"""Python multi-agent framework adapters for LangGraph, CrewAI, AutoGen, and LlamaIndex."""

from collections.abc import Callable
from typing import Any

from sci_verifier_mcp.core.ledger import export_audit_certificate
from sci_verifier_mcp.equations.asymptotics import check_limiting_cases
from sci_verifier_mcp.equations.differential import verify_ode_pde_solution
from sci_verifier_mcp.equations.dimensional import check_dimensional_analysis
from sci_verifier_mcp.equations.equivalence import check_equation_equivalence
from sci_verifier_mcp.equations.invariants import verify_simulation_invariants
from sci_verifier_mcp.equations.smt import check_smt_claim
from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography
from sci_verifier_mcp.literature.citation_verifier import verify_citation
from sci_verifier_mcp.literature.claim_alignment import verify_claim_against_paper
from sci_verifier_mcp.literature.discovery_feed import track_recent_discoveries
from sci_verifier_mcp.literature.similarity import find_similar_papers
from sci_verifier_mcp.materials.mlip_stub import relax_and_score_mlip
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art
from sci_verifier_mcp.materials.properties import verify_material_properties
from sci_verifier_mcp.materials.stability import check_elastic_and_phonon_stability
from sci_verifier_mcp.materials.stoichiometry import check_stoichiometry_and_valence
from sci_verifier_mcp.materials.structure import validate_crystal_structure
from sci_verifier_mcp.proofs.lean_runner import verify_lean4_proof
from sci_verifier_mcp.proofs.premise_search import search_lean_premises
from sci_verifier_mcp.proofs.tensor_simplifier import simplify_tensor_expr


def get_all_tools() -> dict[str, Callable[..., dict[str, Any]]]:
    """Return dictionary of all 21 verification tools returning standardized dict responses."""
    return {
        "check_equation_equivalence": lambda **kwargs: check_equation_equivalence(**kwargs).to_dict(),
        "check_dimensional_analysis": lambda **kwargs: check_dimensional_analysis(**kwargs).to_dict(),
        "check_smt_claim": lambda **kwargs: check_smt_claim(**kwargs).to_dict(),
        "verify_ode_pde_solution": lambda **kwargs: verify_ode_pde_solution(**kwargs).to_dict(),
        "check_limiting_cases": lambda **kwargs: check_limiting_cases(**kwargs).to_dict(),
        "verify_simulation_invariants": lambda **kwargs: verify_simulation_invariants(**kwargs).to_dict(),
        "verify_lean4_proof": lambda **kwargs: verify_lean4_proof(**kwargs).to_dict(),
        "search_lean_premises": lambda **kwargs: search_lean_premises(**kwargs).to_dict(),
        "simplify_tensor_expr": lambda **kwargs: simplify_tensor_expr(**kwargs).to_dict(),
        "validate_crystal_structure": lambda **kwargs: validate_crystal_structure(**kwargs).to_dict(),
        "check_stoichiometry_and_valence": lambda **kwargs: check_stoichiometry_and_valence(**kwargs).to_dict(),
        "verify_material_properties": lambda **kwargs: verify_material_properties(**kwargs).to_dict(),
        "check_novel_structure_prior_art": lambda **kwargs: check_novel_structure_prior_art(**kwargs).to_dict(),
        "check_elastic_and_phonon_stability": lambda **kwargs: check_elastic_and_phonon_stability(**kwargs).to_dict(),
        "relax_and_score_mlip": lambda **kwargs: relax_and_score_mlip(**kwargs).to_dict(),
        "verify_citation": lambda **kwargs: verify_citation(**kwargs).to_dict(),
        "audit_bibliography": lambda **kwargs: audit_bibliography(**kwargs).to_dict(),
        "find_similar_papers": lambda **kwargs: find_similar_papers(**kwargs).to_dict(),
        "verify_claim_against_paper": lambda **kwargs: verify_claim_against_paper(**kwargs).to_dict(),
        "track_recent_discoveries": lambda **kwargs: track_recent_discoveries(**kwargs).to_dict(),
        "export_audit_certificate": lambda **kwargs: export_audit_certificate(**kwargs).to_dict(),
    }


def get_langchain_tools() -> list[Any]:
    """Export tools as LangChain StructuredTool instances for LangGraph, CrewAI, and AutoGen."""
    tools = []
    try:
        from langchain_core.tools import StructuredTool
        tool_map = get_all_tools()
        for name, fn in tool_map.items():
            st = StructuredTool.from_function(
                func=fn,
                name=name,
                description=f"SciVerifier scientific verification tool: {name}",
            )
            tools.append(st)
    except ImportError:
        return list(get_all_tools().values())
    return tools


def get_llamaindex_tools() -> list[Any]:
    """Export tools as LlamaIndex FunctionTool instances."""
    tools = []
    try:
        from llama_index.core.tools import FunctionTool
        tool_map = get_all_tools()
        for name, fn in tool_map.items():
            ft = FunctionTool.from_defaults(
                fn=fn,
                name=name,
                description=f"SciVerifier scientific verification tool: {name}",
            )
            tools.append(ft)
    except ImportError:
        return list(get_all_tools().values())
    return tools
