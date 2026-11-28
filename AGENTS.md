# Multi-Agent Verification Protocol (OpenCode, Aider & Agent Frameworks)

This repository provides the `sci-verifier` MCP server (21 tools) for formal and empirical scientific verification across Mathematics, Theoretical Physics, and Materials Science.

## Core Directives for Autonomous Agents
1. **Equations, ODEs & Simulations**:
   - Verify algebraic steps via `check_equation_equivalence`, differential ansatzes + boundary conditions via `verify_ode_pde_solution`, and asymptotic regimes via `check_limiting_cases`.
   - Audit numerical trajectories, probability norms, PSD/unitary matrices, and convergence orders via `verify_simulation_invariants`.
2. **Dimensions & Units**: Always run `check_dimensional_analysis` before evaluating physical equations.
3. **Materials Science**:
   - Never trust AI-generated CIF/POSCAR files without checking `validate_crystal_structure` (overlapping atoms $< 0.7\text{ \AA}$, extreme density, BVS anomalies, space group symmetry).
   - Verify stoichiometric formulas and balanced reactions with `check_stoichiometry_and_valence`.
   - Verify Born mechanical/phonon stability via `check_elastic_and_phonon_stability`, Materials Project properties via `verify_material_properties`, and OPTIMADE novelty via `check_novel_structure_prior_art`.
4. **Formal Proofs**: Search Mathlib4/`PhysLib` lemmas via `search_lean_premises` before writing Lean 4 code; never accept proofs containing `sorry`, `admit`, or undeclared `axiom` assertions (`verify_lean4_proof`).
5. **Literature Integrity & Provenance**:
   - Verify DOIs/arXiv IDs and retraction status with `verify_citation`, check claim-to-abstract alignment with `verify_claim_against_paper`, and track new preprints via `track_recent_discoveries`.
   - Export reproducible verification trails via `export_audit_certificate`.
