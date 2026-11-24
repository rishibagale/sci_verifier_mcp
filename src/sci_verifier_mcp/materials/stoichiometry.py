"""Stoichiometry, oxidation state plausibility, and reaction mass balance verification."""

import re
from typing import Any
from collections import defaultdict

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus

# Standard electronegativities / common oxidation states for elements
COMMON_OXIDATION_STATES: dict[str, list[int]] = {
    "H": [1, -1], "He": [0], "Li": [1], "Be": [2], "B": [3], "C": [4, -4, 2], "N": [-3, 3, 5],
    "O": [-2, -1], "F": [-1], "Ne": [0], "Na": [1], "Mg": [2], "Al": [3], "Si": [4, -4],
    "P": [5, 3, -3], "S": [-2, 4, 6], "Cl": [-1, 1, 3, 5, 7], "Ar": [0], "K": [1], "Ca": [2],
    "Sc": [3], "Ti": [4, 3, 2], "V": [5, 4, 3, 2], "Cr": [3, 6, 2], "Mn": [2, 4, 7, 3],
    "Fe": [3, 2], "Co": [2, 3], "Ni": [2, 3], "Cu": [2, 1], "Zn": [2], "Ga": [3], "Ge": [4, 2],
    "As": [3, 5, -3], "Se": [-2, 4, 6], "Br": [-1, 1, 5], "Kr": [0], "Rb": [1], "Sr": [2],
    "Y": [3], "Zr": [4], "Nb": [5, 4], "Mo": [6, 4], "Tc": [7, 4], "Ru": [3, 4], "Rh": [3],
    "Pd": [2, 4], "Ag": [1], "Cd": [2], "In": [3], "Sn": [4, 2], "Sb": [3, 5], "Te": [-2, 4, 6],
    "I": [-1, 1, 5, 7], "Xe": [0, 2, 4, 6], "Cs": [1], "Ba": [2], "La": [3], "Ce": [3, 4],
    "Pr": [3], "Nd": [3], "Sm": [3], "Eu": [2, 3], "Gd": [3], "Tb": [3, 4], "Dy": [3],
    "Ho": [3], "Er": [3], "Tm": [3], "Yb": [3, 2], "Lu": [3], "Hf": [4], "Ta": [5], "W": [6, 4],
    "Re": [7, 4], "Os": [4], "Ir": [3, 4], "Pt": [2, 4], "Au": [3, 1], "Hg": [2, 1], "Tl": [1, 3],
    "Pb": [2, 4], "Bi": [3, 5], "Th": [4], "U": [4, 6], "Pu": [4],
}


def parse_formula(formula: str) -> dict[str, float]:
    """Parse a chemical formula like 'BaTiO3' or 'Fe2O3' or '(NH4)2SO4' into element counts."""
    formula = formula.strip()
    
    # Handle parenthesized groups e.g. (NH4)2
    pattern = r"\(([^()]+)\)(\d*\.?\d*)"
    while "(" in formula and ")" in formula:
        match = re.search(pattern, formula)
        if not match:
            break
        group, count_str = match.groups()
        mult = float(count_str) if count_str else 1.0
        inner_counts = parse_formula(group)
        expanded = "".join(f"{el}{c * mult}" for el, c in inner_counts.items())
        formula = formula[:match.start()] + expanded + formula[match.end():]

    element_pattern = r"([A-Z][a-z]*)(\d*\.?\d*)"
    matches = re.findall(element_pattern, formula)
    if not matches:
        raise ValueError(f"Could not parse chemical formula '{formula}'.")

    counts: dict[str, float] = defaultdict(float)
    for elem, num_str in matches:
        num = float(num_str) if num_str else 1.0
        counts[elem] += num

    return dict(counts)


def find_neutral_oxidation_states(composition: dict[str, float]) -> list[dict[str, int]]:
    """Determine plausible combinations of oxidation states that yield total charge zero."""
    elements = list(composition.keys())
    counts = [composition[el] for el in elements]

    valid_solutions = []

    def backtrack(idx: int, current_sum: float, current_assignment: dict[str, int]):
        if idx == len(elements):
            if abs(current_sum) < 1e-5:
                valid_solutions.append(dict(current_assignment))
            return

        el = elements[idx]
        c = counts[idx]
        states = COMMON_OXIDATION_STATES.get(el, [-2, -1, 1, 2, 3, 4])
        for s in states:
            current_assignment[el] = s
            backtrack(idx + 1, current_sum + s * c, current_assignment)
            del current_assignment[el]

    backtrack(0, 0.0, {})
    return valid_solutions


def parse_reaction_side(side_str: str) -> dict[str, float]:
    """Parse a reaction side (e.g. '2 H2 + O2') into total element counts."""
    terms = [t.strip() for t in side_str.split("+") if t.strip()]
    total_counts: dict[str, float] = defaultdict(float)

    for term in terms:
        # Match leading stoichiometric coefficient e.g. '2 H2O'
        match = re.match(r"^(\d*\.?\d*)\s*([A-Za-z0-9\(\)]+)$", term)
        if match:
            coeff_str, formula = match.groups()
            coeff = float(coeff_str) if coeff_str else 1.0
        else:
            coeff = 1.0
            formula = term

        sub_counts = parse_formula(formula)
        for el, c in sub_counts.items():
            total_counts[el] += c * coeff

    return dict(total_counts)


def check_stoichiometry_and_valence(formula_or_reaction: str) -> VerificationResult:
    """Verify stoichiometry, charge neutrality, or chemical reaction balance."""
    clean_input = formula_or_reaction.strip()
    if not clean_input:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty formula or reaction provided.",
            details={}
        )

    # 1. Reaction check if arrow '->' or '=' is present
    reaction_sep = None
    if "->" in clean_input:
        reaction_sep = "->"
    elif "=>" in clean_input:
        reaction_sep = "=>"
    elif "=" in clean_input and not any(clean_input.startswith(c) for c in ("E=", "s=")):
        reaction_sep = "="

    if reaction_sep:
        parts = clean_input.split(reaction_sep)
        if len(parts) == 2:
            lhs_side, rhs_side = parts[0].strip(), parts[1].strip()
            try:
                lhs_counts = parse_reaction_side(lhs_side)
                rhs_counts = parse_reaction_side(rhs_side)
            except Exception as e:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Failed to parse reaction terms: {e}",
                    details={"error": str(e), "reaction": clean_input}
                )

            all_elements = sorted(set(lhs_counts.keys()) | set(rhs_counts.keys()))
            unbalanced = {}
            for el in all_elements:
                l_cnt = lhs_counts.get(el, 0.0)
                r_cnt = rhs_counts.get(el, 0.0)
                if abs(l_cnt - r_cnt) > 1e-4:
                    unbalanced[el] = {"reactants": l_cnt, "products": r_cnt, "difference": r_cnt - l_cnt}

            if unbalanced:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    summary="Chemical reaction is unbalanced (mass/stoichiometry violation).",
                    details={
                        "reaction": clean_input,
                        "unbalanced_elements": unbalanced,
                        "reactants_atoms": lhs_counts,
                        "products_atoms": rhs_counts,
                    }
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    summary="Chemical reaction is mass- and stoichiometry-balanced.",
                    details={
                        "reaction": clean_input,
                        "conserved_elements": all_elements,
                        "atom_counts": lhs_counts,
                    }
                )

    # 2. Single chemical formula analysis
    try:
        # If pymatgen is available, try using Composition
        try:
            from pymatgen.core import Composition
            comp = Composition(clean_input)
            formula_clean = comp.reduced_formula
            atom_counts = {str(k): float(v) for k, v in comp.fractional_composition.as_dict().items()}
        except Exception:
            formula_clean = clean_input
            atom_counts = parse_formula(clean_input)

        element_counts = parse_formula(clean_input)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Invalid chemical formula '{clean_input}': {e}",
            details={"error": str(e)}
        )

    # Check oxidation state neutrality
    neutral_solutions = find_neutral_oxidation_states(element_counts)

    if not neutral_solutions:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Formula '{clean_input}' violates charge neutrality: "
                f"no combination of common oxidation states sums to zero."
            ),
            details={
                "formula": clean_input,
                "element_counts": element_counts,
                "tested_common_states": {el: COMMON_OXIDATION_STATES.get(el, []) for el in element_counts},
            }
        )

    best_solution = neutral_solutions[0]
    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=(
            f"Valid stoichiometric formula '{clean_input}' with plausible charge neutrality "
            f"({', '.join(f'{el}: {st:+d}' for el, st in best_solution.items())})."
        ),
        details={
            "formula": clean_input,
            "element_counts": element_counts,
            "oxidation_state_solution": best_solution,
            "alternative_neutral_states": neutral_solutions[:5],
        }
    )
