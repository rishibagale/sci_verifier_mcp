"""FastMCP server entrypoint registering all scientific verification tools and prompts."""

from typing import Any
try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

from sci_verifier_mcp.equations.equivalence import check_equation_equivalence as _eq_equiv
from sci_verifier_mcp.equations.dimensional import check_dimensional_analysis as _dim_analysis
from sci_verifier_mcp.equations.smt import check_smt_claim as _smt_claim
from sci_verifier_mcp.proofs.lean_runner import verify_lean4_proof as _lean_proof
from sci_verifier_mcp.proofs.tensor_simplifier import simplify_tensor_expr as _tensor_simp
from sci_verifier_mcp.materials.structure import validate_crystal_structure as _cryst_val
from sci_verifier_mcp.materials.stoichiometry import check_stoichiometry_and_valence as _stoich_val
from sci_verifier_mcp.materials.properties import verify_material_properties as _prop_val
from sci_verifier_mcp.materials.optimade_client import check_novel_structure_prior_art as _optimade_val
from sci_verifier_mcp.literature.citation_verifier import verify_citation as _cite_val
from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography as _bib_audit
from sci_verifier_mcp.literature.similarity import find_similar_papers as _sim_papers

# Initialize FastMCP server
mcp = FastMCP("sci_verifier_mcp")


# ============================================================================
# A. Equations, Units & Symbolic/Numerical Checks (Math, Physics & Materials)
# ============================================================================

@mcp.tool()
def check_equation_equivalence(
    lhs: str,
    rhs: str,
    format: str = "latex",
    assumptions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify equivalence between two mathematical expressions symbolically and numerically.

    Uses SymPy simplification and randomized domain-point sampling to detect sign errors
    or missing factors. If expressions are not equivalent, extracts a concrete numerical counterexample.

    Args:
        lhs: Left-hand side expression (LaTeX or SymPy string).
        rhs: Right-hand side expression.
        format: 'latex' (default) or 'sympy'.
        assumptions: Optional variable assumptions (e.g. {'x': 'positive', 'n': 'integer'}).
    """
    res = _eq_equiv(lhs=lhs, rhs=rhs, format=format, assumptions=assumptions)
    return res.to_dict()


@mcp.tool()
def check_dimensional_analysis(
    equation: str,
    symbol_units: dict[str, str],
    unit_system: str = "SI"
) -> dict[str, Any]:
    """Verify dimensional consistency across additive terms and sides using Pint.

    Supports standard SI units, natural units (hbar = c = 1), and materials-science units
    (eV, eV/atom, kJ/mol, angstrom, GPa, S/cm, K).

    Args:
        equation: Equation string with '=' dividing LHS and RHS (e.g. 'E = m * c**2').
        symbol_units: Mapping of variable names to units (e.g. {'E': 'joule', 'm': 'kg', 'c': 'm/s'}).
        unit_system: 'SI' (default) or 'natural'.
    """
    res = _dim_analysis(equation=equation, symbol_units=symbol_units, unit_system=unit_system)
    return res.to_dict()


@mcp.tool()
def check_smt_claim(
    claim: dict[str, Any],
    variables: dict[str, str],
    timeout_ms: int = 5000
) -> dict[str, Any]:
    """Prove or refute inequalities, algebraic constraints, and logical claims using Z3.

    Translates structured JSON ASTs into Z3 propositions safely (no code execution).
    Returns 'verified' if universally valid (unsat negation) or 'failed' with a concrete counterexample model.

    Args:
        claim: Structured dictionary representing the formula (e.g. {'op': 'implies', 'premise': ..., 'conclusion': ...}).
        variables: Dictionary mapping variable names to types ('real', 'int', 'bool').
        timeout_ms: Solver timeout in milliseconds.
    """
    res = _smt_claim(claim=claim, variables=variables, timeout_ms=timeout_ms)
    return res.to_dict()


# ============================================================================
# B. Formal Proof & Tensor Verification (Graceful Degradation)
# ============================================================================

@mcp.tool()
def verify_lean4_proof(
    lean_code: str,
    timeout_seconds: int = 30
) -> dict[str, Any]:
    """Verify formal Lean 4 proofs in a sandboxed temporary directory.

    Scans and rejects cheat tactics ('sorry', 'admit', and undeclared 'axiom' assertions).
    Returns line-numbered compiler diagnostics. If Lean 4 is uninstalled, returns 'unavailable'
    gracefully with setup instructions without crashing.

    Args:
        lean_code: Complete Lean 4 source code containing theorems and proofs.
        timeout_seconds: Subprocess execution timeout in seconds.
    """
    res = _lean_proof(lean_code=lean_code, timeout_seconds=timeout_seconds)
    return res.to_dict()


@mcp.tool()
def simplify_tensor_expr(
    expr: str,
    rules: list[str] | None = None
) -> dict[str, Any]:
    """Simplify tensor expressions for QFT and General Relativity via Cadabra2.

    Returns status 'unavailable' gracefully if Cadabra2 is not installed.

    Args:
        expr: Index notation tensor expression (e.g. 'R_{a b c d} R^{a b c d}').
        rules: Optional tensor symmetry or reduction rules.
    """
    res = _tensor_simp(expr=expr, rules=rules)
    return res.to_dict()


# ============================================================================
# C. Materials Science Verification
# ============================================================================

@mcp.tool()
def validate_crystal_structure(
    structure_text: str,
    format: str = "cif",
    claimed_spacegroup: str | int | None = None,
    min_interatomic_distance_angstrom: float = 0.7
) -> dict[str, Any]:
    """Validate crystal structures (CIF/POSCAR), checking interatomic distances and symmetry.

    Detects unphysical overlapping atoms (< min_interatomic_distance_angstrom),
    computes lattice parameters and volume, and analyzes space group symmetry. Flags
    mismatches if claimed_spacegroup disagrees with computed symmetry.

    Args:
        structure_text: Raw CIF or POSCAR text.
        format: 'cif' (default) or 'poscar'.
        claimed_spacegroup: Claimed space group number or Hermann-Mauguin symbol.
        min_interatomic_distance_angstrom: Minimum allowed interatomic separation (default 0.7 A).
    """
    res = _cryst_val(
        structure_text=structure_text,
        format=format,
        claimed_spacegroup=claimed_spacegroup,
        min_interatomic_distance_angstrom=min_interatomic_distance_angstrom
    )
    return res.to_dict()


@mcp.tool()
def check_stoichiometry_and_valence(
    formula_or_reaction: str
) -> dict[str, Any]:
    """Verify stoichiometry, charge neutrality, oxidation states, and reaction mass balance.

    Accepts single chemical formulas (e.g. 'BaTiO3') or chemical reactions (e.g. '2 H2 + O2 -> 2 H2O').
    Verifies electroneutrality with plausible oxidation states or conservation of atoms across reaction sides.

    Args:
        formula_or_reaction: Formula (e.g. 'Fe2O3') or reaction (e.g. 'CH4 + 2 O2 -> CO2 + 2 H2O').
    """
    res = _stoich_val(formula_or_reaction=formula_or_reaction)
    return res.to_dict()


@mcp.tool()
def verify_material_properties(
    formula_or_mp_id: str,
    claimed_properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify claimed material properties against the Materials Project computed database.

    Cross-checks band gap, energy above hull, formation energy, stability, and space group.
    Requires MP_API_KEY environment variable; returns 'unavailable' gracefully if unset.

    Args:
        formula_or_mp_id: Chemical formula (e.g. 'TiO2') or Materials Project ID (e.g. 'mp-149').
        claimed_properties: Dictionary of properties to verify (e.g. {'band_gap': 1.14, 'is_stable': True}).
    """
    res = _prop_val(formula_or_mp_id=formula_or_mp_id, claimed_properties=claimed_properties)
    return res.to_dict()


@mcp.tool()
def check_novel_structure_prior_art(
    formula: str,
    spacegroup_number: int | None = None,
    elements: list[str] | None = None,
    limit: int = 10
) -> dict[str, Any]:
    """Query federated crystal databases via OPTIMADE to verify novelty claims.

    Searches Materials Project, COD, and AFLOW to test whether an AI-proposed "novel" crystal
    or polymorph already exists in open databases.

    Args:
        formula: Reduced chemical formula (e.g. 'SrTiO3').
        spacegroup_number: Optional space group number.
        elements: Optional list of constituent elements.
        limit: Maximum results to retrieve.
    """
    res = _optimade_val(formula=formula, spacegroup_number=spacegroup_number, elements=elements, limit=limit)
    return res.to_dict()


# ============================================================================
# D. Citation Audit & Prior Art / Similar Ideas
# ============================================================================

@mcp.tool()
def verify_citation(
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None
) -> dict[str, Any]:
    """Cross-check citation against Crossref and arXiv to detect hallucinations and mismatched metadata.

    Catches fabricated DOIs, nonexistent arXiv IDs, and mismatched author/year/title combinations.
    Returns canonical metadata, direct links, and a match confidence score.

    Args:
        title: Claimed paper title.
        authors: List of author names or surnames.
        year: Claimed publication year.
        doi: DOI string (e.g. '10.1038/nature04233').
        arxiv_id: arXiv identifier (e.g. '1706.03762').
    """
    res = _cite_val(title=title, authors=authors, year=year, doi=doi, arxiv_id=arxiv_id)
    return res.to_dict()


@mcp.tool()
def audit_bibliography(
    entries: str | list[dict[str, Any]]
) -> dict[str, Any]:
    """Concurrently audit a bibliography (BibTeX string or list of dicts) with bounded rate limiting.

    Returns a comprehensive verification report flagging fabricated, mismatched, or verified references.

    Args:
        entries: Raw BibTeX string or list of citation dictionaries.
    """
    res = _bib_audit(entries=entries)
    return res.to_dict()


@mcp.tool()
def find_similar_papers(
    query: str,
    domain: str = "general",
    limit: int = 10
) -> dict[str, Any]:
    """Surface related papers, existing proofs, or materials studies across open literature databases.

    Queries Semantic Scholar, arXiv, and INSPIRE-HEP. In 'materials' mode, filters arXiv 'cond-mat.mtrl-sci'.

    Args:
        query: Conceptual query, theorem title, or derivation keywords.
        domain: 'general' (default), 'math', 'physics', 'hep', or 'materials'.
        limit: Maximum papers to return (default 10).
    """
    res = _sim_papers(query=query, domain=domain, limit=limit)
    return res.to_dict()


# ============================================================================
# E. Verification Orchestration Prompt
# ============================================================================

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
   - For materials science, verify stoichiometry with `check_stoichiometry_and_valence` and crystal structures with `validate_crystal_structure`.
2. **Step-by-Step Symbolic & Numerical Equivalence**:
   - Check every non-trivial algebraic step or identity using `check_equation_equivalence`.
   - Never trust simplification by eye; check sign conventions, factors of 2/pi, and randomized numerical counterexamples.
3. **Inequalities, Domain Constraints & Formal Proofs**:
   - If inequalities, bounds, or domain conditions are asserted, prove or refute them using `check_smt_claim`.
   - If formal code is provided, verify it with `verify_lean4_proof` (reject any proofs with `sorry` or `admit`).
4. **Literature & Citation Audit**:
   - Audit all cited papers with `verify_citation` or `audit_bibliography` to eliminate AI-hallucinated DOIs and nonexistent papers.
   - Run `find_similar_papers` with domain="{domain}" to check whether the derivation or proof is already known in the literature.
5. **Synthesis & Report**:
   - Provide an itemized verdict: Verified Steps, Discrepancies / Counterexamples, Flagged Citations, and Prior Art references.
"""


def main():
    """Run FastMCP server over standard I/O (stdio)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
