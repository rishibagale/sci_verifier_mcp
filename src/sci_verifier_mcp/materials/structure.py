"""Crystal structure validation (CIF/POSCAR), interatomic distance checks, and symmetry/spacegroup analysis."""

import math
from typing import Any
import numpy as np

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def parse_cif_fallback(cif_text: str) -> dict[str, Any]:
    """Lightweight built-in CIF parser when external libraries are unavailable."""
    lines = cif_text.strip().splitlines()
    params = {"_cell_length_a": 1.0, "_cell_length_b": 1.0, "_cell_length_c": 1.0,
              "_cell_angle_alpha": 90.0, "_cell_angle_beta": 90.0, "_cell_angle_gamma": 90.0}
    atoms = []
    claimed_sg = None

    in_atom_loop = False
    atom_cols = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        for p in params:
            if line_clean.startswith(p):
                parts = line_clean.split()
                if len(parts) >= 2:
                    val_str = parts[1].split("(")[0]
                    params[p] = float(val_str)

        if "_symmetry_space_group_name_H-M" in line_clean or "_space_group_IT_number" in line_clean:
            parts = line_clean.split(None, 1)
            if len(parts) >= 2:
                claimed_sg = parts[1].strip("'\"")

        if line_clean.startswith("loop_"):
            in_atom_loop = True
            atom_cols = []
            continue

        if in_atom_loop:
            if line_clean.startswith("_atom_site_"):
                atom_cols.append(line_clean)
            elif atom_cols:
                # Value line
                vals = line_clean.split()
                if len(vals) >= len(atom_cols):
                    row = dict(zip(atom_cols, vals))
                    try:
                        elem = row.get("_atom_site_type_symbol", row.get("_atom_site_label", "X")).split("(")[0]
                        elem = "".join(filter(str.isalpha, elem))
                        x = float(row.get("_atom_site_fract_x", 0).split("(")[0])
                        y = float(row.get("_atom_site_fract_y", 0).split("(")[0])
                        z = float(row.get("_atom_site_fract_z", 0).split("(")[0])
                        atoms.append({"element": elem, "coords": [x, y, z]})
                    except Exception:
                        pass

    return {
        "a": params["_cell_length_a"],
        "b": params["_cell_length_b"],
        "c": params["_cell_length_c"],
        "alpha": params["_cell_angle_alpha"],
        "beta": params["_cell_angle_beta"],
        "gamma": params["_cell_angle_gamma"],
        "atoms": atoms,
        "claimed_sg": claimed_sg,
    }


def compute_lattice_matrix(a: float, b: float, c: float, alpha_deg: float, beta_deg: float, gamma_deg: float) -> np.ndarray:
    """Compute 3x3 Cartesian lattice vectors from cell parameters."""
    alpha = math.radians(alpha_deg)
    beta = math.radians(beta_deg)
    gamma = math.radians(gamma_deg)

    cos_alpha = math.cos(alpha)
    cos_beta = math.cos(beta)
    cos_gamma = math.cos(gamma)
    sin_gamma = math.sin(gamma)

    val = (cos_alpha - cos_beta * cos_gamma) / sin_gamma
    val = max(-1.0, min(1.0, val))

    c_x = c * cos_beta
    c_y = c * val
    c_z = c * math.sqrt(max(0.0, math.sin(beta)**2 - val**2))

    return np.array([
        [a, 0.0, 0.0],
        [b * cos_gamma, b * sin_gamma, 0.0],
        [c_x, c_y, c_z]
    ])


def check_minimum_interatomic_distance(
    coords_cart: np.ndarray,
    lattice_matrix: np.ndarray,
    min_dist_threshold: float = 0.7
) -> tuple[float, tuple[int, int] | None]:
    """Compute the minimum interatomic distance under periodic boundary conditions."""
    n_atoms = len(coords_cart)
    if n_atoms < 2:
        return float("inf"), None

    min_dist = float("inf")
    closest_pair = None

    # Periodic shift vectors (-1, 0, 1 in fractional)
    shifts = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                shifts.append(dx * lattice_matrix[0] + dy * lattice_matrix[1] + dz * lattice_matrix[2])

    for i in range(n_atoms):
        for j in range(i + 1, n_atoms):
            r_ij = coords_cart[j] - coords_cart[i]
            for shift in shifts:
                d = float(np.linalg.norm(r_ij + shift))
                if d < min_dist:
                    min_dist = d
                    closest_pair = (i, j)

    return min_dist, closest_pair


def validate_crystal_structure(
    structure_text: str,
    format: str = "cif",
    claimed_spacegroup: str | int | None = None,
    min_interatomic_distance_angstrom: float = 0.7
) -> VerificationResult:
    """Validate crystal structure syntax, check interatomic distances, and verify space group."""
    clean_text = structure_text.strip()
    if not clean_text:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty structure text provided.",
            details={"format": format}
        )

    # 1. Attempt parsing with pymatgen / ase / fallback
    lattice_matrix = None
    coords_frac = []
    coords_cart = []
    species = []
    volume = 0.0
    computed_sg_number = None
    computed_sg_symbol = None
    parsing_engine = "fallback"

    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

        struct = Structure.from_str(clean_text, fmt=format.lower())
        lattice_matrix = struct.lattice.matrix
        coords_cart = np.array(struct.cart_coords)
        coords_frac = np.array(struct.frac_coords)
        species = [str(sp) for sp in struct.species]
        volume = float(struct.volume)
        parsing_engine = "pymatgen"

        # Symmetry analysis
        sga = SpacegroupAnalyzer(struct, symprec=0.01)
        computed_sg_number = sga.get_space_group_number()
        computed_sg_symbol = sga.get_space_group_symbol()

    except Exception:
        # Fallback to built-in CIF parser
        if format.lower() == "cif":
            try:
                parsed = parse_cif_fallback(clean_text)
                lattice_matrix = compute_lattice_matrix(
                    parsed["a"], parsed["b"], parsed["c"],
                    parsed["alpha"], parsed["beta"], parsed["gamma"]
                )
                volume = float(abs(np.linalg.det(lattice_matrix)))
                atoms = parsed["atoms"]
                if atoms:
                    coords_frac = np.array([a["coords"] for a in atoms])
                    coords_cart = coords_frac @ lattice_matrix
                    species = [a["element"] for a in atoms]

                # If spglib is installed, run symmetry analysis
                try:
                    import spglib
                    species_map = {sp: idx + 1 for idx, sp in enumerate(sorted(set(species)))}
                    numbers = [species_map[s] for s in species]
                    cell = (lattice_matrix, coords_frac, numbers)
                    dataset = spglib.get_symmetry_dataset(cell, symprec=1e-2)
                    if dataset is not None:
                        computed_sg_number = int(getattr(dataset, "number", 0) or dataset["number"])
                        computed_sg_symbol = str(getattr(dataset, "international", "") or dataset["international"])
                except Exception:
                    pass

                if claimed_spacegroup is None and parsed.get("claimed_sg"):
                    claimed_spacegroup = parsed["claimed_sg"]

            except Exception as e:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Failed to parse crystal structure: {e}",
                    details={"error": str(e), "format": format}
                )
        else:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Unable to parse format '{format}' without pymatgen.",
                details={"format": format}
            )

    if lattice_matrix is None or len(coords_cart) == 0:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="No valid atomic positions or lattice found in crystal structure.",
            details={"format": format}
        )

    # 2. Check for overlapping atoms / minimum interatomic distance
    min_dist, closest_pair = check_minimum_interatomic_distance(
        coords_cart, lattice_matrix, min_dist_threshold=min_interatomic_distance_angstrom
    )

    if min_dist < min_interatomic_distance_angstrom:
        pair_info = None
        if closest_pair is not None:
            i, j = closest_pair
            sp_i = species[i] if i < len(species) else "?"
            sp_j = species[j] if j < len(species) else "?"
            pair_info = f"{sp_i}#{i} - {sp_j}#{j}"

        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Unphysical crystal structure: overlapping atoms detected "
                f"(min distance {min_dist:.3f} \u00c5 < threshold {min_interatomic_distance_angstrom:.3f} \u00c5)."
            ),
            details={
                "min_interatomic_distance_angstrom": min_dist,
                "threshold_angstrom": min_interatomic_distance_angstrom,
                "closest_pair": pair_info,
                "total_atoms": len(species),
                "volume_angstrom3": volume,
            }
        )

    # 3. Check claimed vs computed space group
    details = {
        "engine": parsing_engine,
        "total_atoms": len(species),
        "formula": "".join(species),
        "volume_angstrom3": volume,
        "min_interatomic_distance_angstrom": min_dist,
        "computed_spacegroup_number": computed_sg_number,
        "computed_spacegroup_symbol": computed_sg_symbol,
    }

    if claimed_spacegroup is not None and computed_sg_number is not None:
        claimed_str = str(claimed_spacegroup).strip().lower()
        computed_num_str = str(computed_sg_number)
        computed_sym_str = str(computed_sg_symbol).strip().lower() if computed_sg_symbol else ""

        match = (claimed_str == computed_num_str) or (claimed_str == computed_sym_str)
        if not match:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=(
                    f"Symmetry mismatch: claimed space group '{claimed_spacegroup}' "
                    f"does not match computed space group {computed_sg_symbol} (#{computed_sg_number})."
                ),
                details=details
            )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=(
            f"Crystal structure valid (volume: {volume:.2f} \u00c5\u00b3, "
            f"min distance: {min_dist:.2f} \u00c5, "
            f"space group: {computed_sg_symbol or 'unknown'} [#{computed_sg_number or '?'}])."
        ),
        details=details
    )
