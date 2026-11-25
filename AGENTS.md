# Multi-Agent Verification Protocol (OpenCode, Aider & Agent Frameworks)

This repository provides the `sci-verifier` MCP server for formal and empirical scientific verification across Mathematics, Theoretical Physics, and Materials Science.

## Core Directives for Autonomous Agents
1. **Equations & Derivations**: Always verify intermediate algebraic steps via `check_equation_equivalence`. Check numerical counterexamples on discrepancy.
2. **Dimensions & Units**: Always run `check_dimensional_analysis` before evaluating complex physical equations.
3. **Materials Science**:
   - Never trust AI-generated CIF/POSCAR files without checking `validate_crystal_structure` for overlapping atoms (< 0.7 A).
   - Verify stoichiometric formulas and balanced reactions with `check_stoichiometry_and_valence`.
   - Verify property claims against the Materials Project via `verify_material_properties`.
4. **Formal Proofs**: Never accept Lean 4 proofs containing `sorry`, `admit`, or newly declared `axiom` assertions.
5. **Literature**: Always verify DOIs and arXiv IDs with `verify_citation` to prevent fabricated citations.
