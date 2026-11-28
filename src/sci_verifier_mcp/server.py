"""FastMCP server entrypoint registering all 21 scientific verification tools, prompts, and transports."""

import argparse
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore[no-redef]

from sci_verifier_mcp.core.ledger import audit_ledger
from sci_verifier_mcp.core.ledger import export_audit_certificate as _export_cert
from sci_verifier_mcp.equations.asymptotics import check_limiting_cases as _lim_cases
from sci_verifier_mcp.equations.differential import verify_ode_pde_solution as _ode_pde
from sci_verifier_mcp.equations.dimensional import check_dimensional_analysis as _dim_analysis
from sci_verifier_mcp.equations.equivalence import check_equation_equivalence as _eq_equiv
from sci_verifier_mcp.equations.invariants import verify_simulation_invariants as _sim_invariants
from sci_verifier_mcp.equations.smt import check_smt_claim as _smt_claim
from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography as _bib_audit
from sci_verifier_mcp.literature.citation_verifier import verify_citation as _cite_val
from sci_verifier_mcp.literature.claim_alignment import verify_claim_against_paper as _claim_align
from sci_verifier_mcp.literature.discovery_feed import track_recent_discoveries as _discoveries
from sci_verifier_mcp.literature.similarity import find_similar_papers as _sim_papers
from sci_verifier_mcp.materials.mlip_stub import relax_and_score_mlip as _mlip_relax
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art as _optimade_val
from sci_verifier_mcp.materials.properties import verify_material_properties as _prop_val
from sci_verifier_mcp.materials.stability import check_elastic_and_phonon_stability as _mat_stab
from sci_verifier_mcp.materials.stoichiometry import check_stoichiometry_and_valence as _stoich_val
from sci_verifier_mcp.materials.structure import validate_crystal_structure as _cryst_val
from sci_verifier_mcp.proofs.lean_runner import verify_lean4_proof as _lean_proof
from sci_verifier_mcp.proofs.premise_search import search_lean_premises as _lean_premises
from sci_verifier_mcp.proofs.tensor_simplifier import simplify_tensor_expr as _tensor_simp

mcp = FastMCP("sci_verifier_mcp")


def _recorded(tool_name: str, inputs: dict[str, Any], result_obj: Any) -> dict[str, Any]:
    """Serialize VerificationResult and append entry to the session audit ledger."""
    data = result_obj.to_dict()
    audit_ledger.record(tool_name, inputs, data)
    return data


# ============================================================================
# A. Equations, Units, Differential Equations & Simulation Invariants
# ============================================================================

@mcp.tool()
def check_equation_equivalence(
    lhs: str,
    rhs: str,
    format: str = "latex",
    assumptions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify equivalence between two mathematical expressions symbolically and numerically.

    Uses wall-clock guarded SymPy simplification and randomized domain-point sampling to detect
    sign errors or missing factors. Returns a concrete numerical counterexample on failure.
    """
    res = _eq_equiv(lhs=lhs, rhs=rhs, format=format, assumptions=assumptions)
    return _recorded("check_equation_equivalence", {"lhs": lhs, "rhs": rhs, "format": format}, res)


@mcp.tool()
def check_dimensional_analysis(
    equation: str,
    symbol_units: dict[str, str],
    unit_system: str = "SI"
) -> dict[str, Any]:
    """Verify dimensional consistency across additive terms and sides using Pint.

    Supports SI units, natural units (hbar = c = 1), and materials-science units
    (eV, eV/atom, kJ/mol, angstrom, GPa, S/cm, K).
    """
    res = _dim_analysis(equation=equation, symbol_units=symbol_units, unit_system=unit_system)
    return _recorded("check_dimensional_analysis", {"equation": equation, "unit_system": unit_system}, res)


@mcp.tool()
def check_smt_claim(
    claim: dict[str, Any],
    variables: dict[str, str],
    timeout_ms: int = 5000
) -> dict[str, Any]:
    """Prove or refute inequalities, algebraic constraints, and logical claims using Z3."""
    res = _smt_claim(claim=claim, variables=variables, timeout_ms=timeout_ms)
    return _recorded("check_smt_claim", {"variables": variables, "timeout_ms": timeout_ms}, res)


@mcp.tool()
def verify_ode_pde_solution(
    equation: str,
    candidate_solution: str,
    dependent_var: str = "y",
    independent_vars: list[str] | None = None,
    boundary_conditions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify whether a candidate expression satisfies an ODE or PDE and boundary/initial conditions."""
    res = _ode_pde(
        equation=equation,
        candidate_solution=candidate_solution,
        dependent_var=dependent_var,
        independent_vars=independent_vars,
        boundary_conditions=boundary_conditions,
    )
    return _recorded("verify_ode_pde_solution", {"equation": equation, "candidate_solution": candidate_solution}, res)


@mcp.tool()
def check_limiting_cases(
    expr: str,
    limits: dict[str, str | float | int],
    expected: dict[str, str | float | int] | None = None,
    format: str = "sympy",
    assumptions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate symbolic asymptotic/boundary limits and compare against expected physical scaling."""
    res = _lim_cases(expr=expr, limits=limits, expected=expected, format=format, assumptions=assumptions)
    return _recorded("check_limiting_cases", {"expr": expr, "limits": limits}, res)


@mcp.tool()
def verify_simulation_invariants(
    data: dict[str, Any] | list[Any],
    checks: list[str],
    tolerance: float = 1e-6
) -> dict[str, Any]:
    """Audit numerical simulation outputs for conservation laws, normalization, PSD/unitarity, or convergence."""
    res = _sim_invariants(data=data, checks=checks, tolerance=tolerance)
    return _recorded("verify_simulation_invariants", {"checks": checks, "tolerance": tolerance}, res)


# ============================================================================
# B. Formal Proof, Premise Lookup & Tensor Verification
# ============================================================================

@mcp.tool()
def verify_lean4_proof(
    lean_code: str,
    timeout_seconds: int = 30,
    allow_axioms: bool = False,
    project_dir: str | None = None,
) -> dict[str, Any]:
    """Verify formal Lean 4 proofs via lake env lean (if Lake project) or isolated lean subprocess.

    Rejects cheat tactics ('sorry', 'admit', undeclared 'axiom'), extracts tactic goal states,
    and returns 'unavailable' gracefully if Lean 4 is not installed.
    """
    res = _lean_proof(
        lean_code=lean_code,
        timeout_seconds=timeout_seconds,
        allow_axioms=allow_axioms,
        project_dir=project_dir,
    )
    return _recorded("verify_lean4_proof", {"project_dir": project_dir, "timeout_seconds": timeout_seconds}, res)


@mcp.tool()
def search_lean_premises(
    query: str,
    backend: str = "loogle",
    limit: int = 10,
) -> dict[str, Any]:
    """Search Mathlib4 and PhysLib theorems/lemmas via Loogle (type patterns) or LeanSearch (natural language)."""
    res = _lean_premises(query=query, backend=backend, limit=limit)
    return _recorded("search_lean_premises", {"query": query, "backend": backend}, res)


@mcp.tool()
def simplify_tensor_expr(
    expr: str,
    rules: list[str] | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """Simplify tensor expressions for QFT and General Relativity via Cadabra2 (graceful unavailable fallback)."""
    res = _tensor_simp(expr=expr, rules=rules, timeout_seconds=timeout_seconds)
    return _recorded("simplify_tensor_expr", {"expr": expr}, res)


# ============================================================================
# C. Materials Science Verification
# ============================================================================

@mcp.tool()
def validate_crystal_structure(
    structure_text: str,
    format: str = "cif",
    claimed_spacegroup: str | int | None = None,
    min_interatomic_distance_angstrom: float = 0.7,
    check_bvs: bool = True,
) -> dict[str, Any]:
    """Validate crystal structures (CIF/POSCAR via pymatgen/ASE/fallback), distance, density, BVS, and symmetry."""
    res = _cryst_val(
        structure_text=structure_text,
        format=format,
        claimed_spacegroup=claimed_spacegroup,
        min_interatomic_distance_angstrom=min_interatomic_distance_angstrom,
        check_bvs=check_bvs,
    )
    return _recorded("validate_crystal_structure", {"format": format, "claimed_spacegroup": claimed_spacegroup}, res)


@mcp.tool()
def check_stoichiometry_and_valence(formula_or_reaction: str) -> dict[str, Any]:
    """Verify chemical formula charge neutrality, oxidation states, and reaction elemental balance."""
    res = _stoich_val(formula_or_reaction=formula_or_reaction)
    return _recorded("check_stoichiometry_and_valence", {"formula_or_reaction": formula_or_reaction}, res)


@mcp.tool()
def verify_material_properties(
    formula_or_mp_id: str,
    claimed_properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify claimed material properties against the Materials Project computed database."""
    res = _prop_val(formula_or_mp_id=formula_or_mp_id, claimed_properties=claimed_properties)
    return _recorded("verify_material_properties", {"formula_or_mp_id": formula_or_mp_id}, res)


@mcp.tool()
def check_novel_structure_prior_art(
    formula: str,
    spacegroup_number: int | None = None,
    elements: list[str] | None = None,
    limit: int = 10
) -> dict[str, Any]:
    """Query federated crystal databases via OPTIMADE (with optional spacegroup filtering) to test novelty."""
    res = _optimade_val(formula=formula, spacegroup_number=spacegroup_number, elements=elements, limit=limit)
    return _recorded(
        "check_novel_structure_prior_art",
        {"formula": formula, "spacegroup_number": spacegroup_number, "elements": elements},
        res,
    )


@mcp.tool()
def check_elastic_and_phonon_stability(
    elastic_tensor_gpa: list[list[float]] | None = None,
    phonon_frequencies_thz: list[float] | None = None,
    imaginary_threshold_thz: float = -0.1,
) -> dict[str, Any]:
    """Verify Born mechanical stability criteria (6x6 Voigt C_ij eigenvalues) and phonon stability."""
    res = _mat_stab(
        elastic_tensor_gpa=elastic_tensor_gpa,
        phonon_frequencies_thz=phonon_frequencies_thz,
        imaginary_threshold_thz=imaginary_threshold_thz,
    )
    return _recorded("check_elastic_and_phonon_stability", {"has_elastic": elastic_tensor_gpa is not None, "has_phonon": phonon_frequencies_thz is not None}, res)


@mcp.tool()
def relax_and_score_mlip(
    structure_text: str,
    format: str = "cif",
    model: str = "mace",
    fmax: float = 0.05,
    max_steps: int = 50,
) -> dict[str, Any]:
    """Relax and evaluate atomic forces/energy delta via MACE or CHGNet (graceful unavailable fallback)."""
    res = _mlip_relax(structure_text=structure_text, format=format, model=model, fmax=fmax, max_steps=max_steps)
    return _recorded("relax_and_score_mlip", {"format": format, "model": model, "fmax": fmax}, res)


# ============================================================================
# D. Citation Audit, Retraction Screening, Claim Alignment & Discovery Feeds
# ============================================================================

@mcp.tool()
def verify_citation(
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None
) -> dict[str, Any]:
    """Cross-check citation against Crossref, OpenAlex, and arXiv, flagging fabricated or retracted papers."""
    res = _cite_val(title=title, authors=authors, year=year, doi=doi, arxiv_id=arxiv_id)
    return _recorded("verify_citation", {"title": title, "doi": doi, "arxiv_id": arxiv_id}, res)


@mcp.tool()
def audit_bibliography(entries: str | list[dict[str, Any]]) -> dict[str, Any]:
    """Concurrently audit a bibliography (BibTeX string or list of dicts) with bounded rate limiting."""
    res = _bib_audit(entries=entries)
    return _recorded("audit_bibliography", {"entries_type": type(entries).__name__}, res)


@mcp.tool()
def find_similar_papers(
    query: str,
    domain: str = "general",
    limit: int = 10
) -> dict[str, Any]:
    """Surface related papers, existing proofs, or materials studies across Semantic Scholar, arXiv, and INSPIRE-HEP."""
    res = _sim_papers(query=query, domain=domain, limit=limit)
    return _recorded("find_similar_papers", {"query": query, "domain": domain}, res)


@mcp.tool()
def verify_claim_against_paper(
    claim: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None
) -> dict[str, Any]:
    """Verify whether an AI-stated claim aligns with the cited paper's abstract and screen for tortured phrases."""
    res = _claim_align(claim=claim, doi=doi, arxiv_id=arxiv_id, title=title)
    return _recorded("verify_claim_against_paper", {"claim": claim, "doi": doi, "arxiv_id": arxiv_id}, res)


@mcp.tool()
def track_recent_discoveries(
    topic_or_domain: str,
    days: int = 7,
    limit: int = 10
) -> dict[str, Any]:
    """Fetch recent preprints and discoveries from arXiv and OpenAlex to stay current with SOTA."""
    res = _discoveries(topic_or_domain=topic_or_domain, days=days, limit=limit)
    return _recorded("track_recent_discoveries", {"topic_or_domain": topic_or_domain, "days": days}, res)


# ============================================================================
# E. Session Provenance Certificate & Verification Prompt
# ============================================================================

@mcp.tool()
def export_audit_certificate(
    title: str = "SciVerifier Audit Report",
    format: str = "markdown",
    clear_after_export: bool = False,
) -> dict[str, Any]:
    """Export a peer-reviewable provenance certificate of all verification checks run in this session."""
    res = _export_cert(title=title, format=format, clear_after_export=clear_after_export)
    return res.to_dict()


@mcp.prompt("audit_derivation")
def audit_derivation_prompt(
    derivation_text: str,
    domain: str = "physics"
) -> str:
    """Prompt template guiding clients through a complete multi-stage verification audit pass."""
    return f"""You are acting as an expert peer reviewer and formal verification assistant in {domain}.
Execute a rigorous multi-stage audit of the following scientific claim / derivation:

```text
{derivation_text}
```

Follow this strict verification procedure using the available SciVerifier MCP tools:
1. **Dimensional & Physical Sanity Check**:
   - Call `check_dimensional_analysis` on all governing equations.
   - Verify asymptotic behavior with `check_limiting_cases` and numerical code trajectories with `verify_simulation_invariants`.
2. **Step-by-Step Symbolic, Differential & SMT Checks**:
   - Check algebraic steps via `check_equation_equivalence` and differential equation ansatzes via `verify_ode_pde_solution`.
   - Prove or refute inequality bounds with `check_smt_claim`.
3. **Formal Proofs (Lean 4)**:
   - Use `search_lean_premises` (Loogle/LeanSearch) before writing Lean 4 lemmas, then verify via `verify_lean4_proof` (reject `sorry`/`admit`/unvetted axioms).
4. **Materials Science Validation (if applicable)**:
   - Check stoichiometry/electroneutrality (`check_stoichiometry_and_valence`), CIF/POSCAR distances/density/BVS/spacegroup (`validate_crystal_structure`), mechanical/phonon stability (`check_elastic_and_phonon_stability`), Materials Project properties (`verify_material_properties`), and OPTIMADE novelty (`check_novel_structure_prior_art`).
5. **Literature, Retraction & Claim-Alignment Audit**:
   - Audit citations with `verify_citation` or `audit_bibliography` (catches fake DOIs AND retracted papers).
   - Verify cited papers actually support claimed statements via `verify_claim_against_paper`, and search prior art / recent work via `find_similar_papers` or `track_recent_discoveries`.
6. **Provenance Certificate**:
   - Call `export_audit_certificate` to produce a reproducible Markdown/JSON audit trail alongside your peer review verdict.
"""


def main(argv: list[str] | None = None) -> None:
    """Run FastMCP server over stdio or Streamable HTTP, or invoke installer/config CLI."""
    args_list = list(sys.argv[1:] if argv is None else argv)

    if args_list and args_list[0] in ("install", "--install", "config", "--config"):
        from sci_verifier_mcp.installer import run_installer_cli
        cmd = args_list[0]
        sub_args = args_list[1:]
        if "config" in cmd and "--print" not in sub_args:
            sub_args = ["--print"] + sub_args
        sys.exit(run_installer_cli(sub_args))

    parser = argparse.ArgumentParser(
        prog="sci-verifier-mcp",
        description="SciVerifier MCP server (Math, Theoretical Physics, Materials Science, and Literature).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for streamable-http transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for streamable-http transport (default: 8000).",
    )
    parsed = parser.parse_args(args_list)

    if parsed.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=parsed.host, port=parsed.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
