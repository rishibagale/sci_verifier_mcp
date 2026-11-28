---
name: sci-verifier
description: Systematic multi-stage verification protocol for mathematical derivations, ODE/PDEs, simulation invariants, theoretical physics equations, formal proofs, materials science crystal structures/stability, and scientific literature citations.
---

# Scientific Verification Protocol (Math, Physics & Materials Science)

This skill encodes the rigor standards and verification checklists used by mathematicians, theoretical physicists, and materials scientists. Execute this systematic protocol using the `sci_verifier_mcp` tools (21 tools).

---

## 1. Golden Rules of Scientific Verification

1. **Never Accept Simplification or Limits by Eye**:
   - Check every algebraic step with `check_equation_equivalence` (symbolic + domain sampling).
   - Check differential equations and boundary/initial conditions with `verify_ode_pde_solution`.
   - Test asymptotic and boundary regimes ($0$, $\pm\infty$, $n=0,1$, $\hbar \to 0$, $c \to \infty$) with `check_limiting_cases`.
   - Audit numerical simulation trajectories, probability vectors, density/covariance matrices, and grid convergence orders with `verify_simulation_invariants`.

2. **Dimensions & Units First**:
   - Verify dimensional consistency using `check_dimensional_analysis` before multi-page algebra.
   - In natural units ($\hbar = c = 1$), verify all terms share the same net energy/mass exponent $D = [M] - [L] - [T] + [\Theta]$.

3. **Zero Tolerance for Formal Proof Cheats & Guessed Lemmas**:
   - Query Mathlib4 / `PhysLib` theorem names first via `search_lean_premises` (Loogle / LeanSearch).
   - Never accept proofs containing `sorry`, `admit`, or undeclared `axiom` assertions. Run `verify_lean4_proof` (`lake env lean` for Lake projects) and inspect line-numbered `goal_states`.

4. **Materials Science: Stability Does Not Equal Synthesizability**:
   - Reject unphysical crystal structures with `validate_crystal_structure`: atomic separations $< 0.7\text{ \AA}$, extreme density outliers ($< 0.3$ or $> 25.0\text{ g/cm}^3$), Bond Valence Sum (BVS) anomalies, or space-group mismatches.
   - Verify charge neutrality and reaction balance with `check_stoichiometry_and_valence`.
   - Verify **Born mechanical stability** ($6\times 6$ $C_{ij}$ eigenvalues $> 0$) and dynamical phonon stability (no imaginary modes $< -0.1\text{ THz}$) with `check_elastic_and_phonon_stability`.
   - Cross-check $E_{\text{hull}}$ / band gap against Materials Project (`verify_material_properties`), check MLIP forces (`relax_and_score_mlip`), and check OPTIMADE (`check_novel_structure_prior_art`) before claiming novelty.

5. **Zero Tolerance for Hallucinated, Retracted, or Paper-Washed Citations**:
   - Verify every DOI/arXiv ID with `verify_citation` or `audit_bibliography` (flags fake DOIs **and** retracted papers via Crossref `update-to` / OpenAlex `is_retracted`).
   - Run `verify_claim_against_paper` to ensure the cited abstract actually supports the stated claim and contains no LLM "tortured phrases".
   - Use `find_similar_papers` or `track_recent_discoveries` to stay aligned with recent preprints and prior art.

6. **Export Reproducible Provenance**:
   - End major verification passes by calling `export_audit_certificate` to produce a Markdown/JSON audit trail.
