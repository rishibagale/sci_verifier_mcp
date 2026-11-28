"""Crystal structure validation (CIF/POSCAR via pymatgen/ase/fallback), distance, density, BVS, and symmetry."""

import math
from io import StringIO
from typing import Any

import numpy as np

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus

# Standard atomic masses (g/mol) for density plausibility calculations
ATOMIC_MASSES: dict[str, float] = {
    "H": 1.008, "He": 4.003, "Li": 6.941, "Be": 9.012, "B": 10.81, "C": 12.011,
    "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.18, "Na": 22.99, "Mg": 24.305,
    "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "Ar": 39.948,
    "K": 39.098, "Ca": 40.078, "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996,
    "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.63, "As": 74.922, "Se": 78.971, "Br": 79.904, "Rb": 85.468,
    "Sr": 87.62, "Y": 88.906, "Zr": 91.224, "Nb": 92.906, "Mo": 95.95, "Ru": 101.07,
    "Rh": 102.91, "Pd": 106.42, "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71,
    "Sb": 121.76, "Te": 127.6, "I": 126.9, "Cs": 132.91, "Ba": 137.33, "La": 138.91,
    "Ce": 140.12, "Nd": 144.24, "Gd": 157.25, "Hf": 178.49, "Ta": 180.95, "W": 183.84,
    "Pt": 195.08, "Au": 196.97, "Pb": 207.2, "Bi": 208.98, "U": 238.03,
}

# Representative Brown-Altermatt R0 parameters (Angstrom) for cation-oxide pairs and expected valence
BVS_OXIDE_R0: dict[str, tuple[float, float]] = {
    "Li": (1.466, 1.0), "Na": (1.803, 1.0), "K": (2.132, 1.0),
    "Mg": (1.693, 2.0), "Ca": (1.967, 2.0), "Sr": (2.118, 2.0), "Ba": (2.285, 2.0),
    "Al": (1.651, 3.0), "Ga": (1.730, 3.0), "In": (1.902, 3.0),
    "Si": (1.624, 4.0), "Ge": (1.748, 4.0), "Ti": (1.815, 4.0), "Zr": (1.928, 4.0),
    "Fe": (1.759, 3.0), "Cr": (1.724, 3.0), "Mn": (1.760, 3.0), "Co": (1.692, 2.0),
    "Ni": (1.654, 2.0), "Cu": (1.679, 2.0), "Zn": (1.704, 2.0), "La": (2.172, 3.0),
}


def parse_cif_fallback(cif_text: str) -> dict[str, Any]:
    """Lightweight built-in CIF parser when external libraries are unavailable."""
    lines = cif_text.strip().splitlines()
    params = {"_cell_length_a": 1.0, "_cell_length_b": 1.0, "_cell_length_c": 1.0,
              "_cell_angle_alpha": 90.0, "_cell_angle_beta": 90.0, "_cell_angle_gamma": 90.0}
    atoms = []
    claimed_sg = None

    in_atom_loop = False
    atom_cols: list[str] = []

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
                vals = line_clean.split()
                if len(vals) >= len(atom_cols):
                    row = dict(zip(atom_cols, vals, strict=False))
                    try:
                        elem = row.get("_atom_site_type_symbol", row.get("_atom_site_label", "X")).split("(")[0]
                        elem = "".join(filter(str.isalpha, elem))
                        x = float(row.get("_atom_site_fract_x", "0").split("(")[0])
                        y = float(row.get("_atom_site_fract_y", "0").split("(")[0])
                        z = float(row.get("_atom_site_fract_z", "0").split("(")[0])
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


def parse_poscar_fallback(poscar_text: str) -> dict[str, Any]:
    """Built-in VASP5 POSCAR/CONTCAR parser when pymatgen and ase are unavailable."""
    lines = [ln.strip() for ln in poscar_text.strip().splitlines() if ln.strip()]
    if len(lines) < 8:
        raise ValueError("POSCAR text is too short (expected >= 8 non-empty lines).")

    scale = float(lines[1].split()[0])
    lattice = np.array([[float(x) for x in lines[i].split()[:3]] for i in range(2, 5)], dtype=float)
    if scale < 0:
        target_vol = -scale
        cur_vol = abs(float(np.linalg.det(lattice)))
        scale = (target_vol / cur_vol) ** (1.0 / 3.0)
    lattice = lattice * scale

    line5_tokens = lines[5].split()
    if all(tok.isalpha() for tok in line5_tokens):
        elem_names = line5_tokens
        counts = [int(x) for x in lines[6].split()]
        idx = 7
    else:
        raise ValueError("VASP4 POSCAR without element symbols on line 6 is unsupported in fallback mode.")

    if len(elem_names) != len(counts):
        raise ValueError("Mismatch between element symbols and counts in POSCAR.")

    if lines[idx].lower().startswith("s"):  # Selective dynamics
        idx += 1

    coord_mode = lines[idx].lower()
    is_direct = coord_mode.startswith("d")
    idx += 1

    total_atoms = sum(counts)
    if len(lines) < idx + total_atoms:
        raise ValueError("POSCAR has fewer coordinate lines than declared atom count.")

    species: list[str] = []
    for el, cnt in zip(elem_names, counts, strict=False):
        species.extend([el] * cnt)

    raw_coords = np.array([[float(x) for x in lines[idx + i].split()[:3]] for i in range(total_atoms)], dtype=float)
    if is_direct:
        coords_frac = raw_coords
        coords_cart = coords_frac @ lattice
    else:
        coords_cart = raw_coords * scale
        coords_frac = coords_cart @ np.linalg.inv(lattice)

    return {
        "lattice_matrix": lattice,
        "coords_frac": coords_frac,
        "coords_cart": coords_cart,
        "species": species,
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

    shifts = [
        dx * lattice_matrix[0] + dy * lattice_matrix[1] + dz * lattice_matrix[2]
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
    ]

    for i in range(n_atoms):
        for j in range(i + 1, n_atoms):
            r_ij = coords_cart[j] - coords_cart[i]
            for shift in shifts:
                d = float(np.linalg.norm(r_ij + shift))
                if d < min_dist:
                    min_dist = d
                    closest_pair = (i, j)

    return min_dist, closest_pair


def compute_density_g_cm3(species: list[str], volume_angstrom3: float) -> float | None:
    """Compute crystal mass density in g/cm^3 from species list and unit cell volume."""
    if volume_angstrom3 <= 0 or not species:
        return None
    total_amu = 0.0
    for sp in species:
        el = "".join(ch for ch in sp if ch.isalpha())
        if el not in ATOMIC_MASSES:
            return None
        total_amu += ATOMIC_MASSES[el]
    # 1 amu / A^3 = 1.66053906660 g/cm^3
    return float((total_amu / volume_angstrom3) * 1.66053906660)


def check_oxide_bond_valence_sums(
    species: list[str],
    coords_cart: np.ndarray,
    lattice_matrix: np.ndarray,
) -> dict[str, Any] | None:
    """Check Bond Valence Sum plausibility for binary/ternary oxides with known R0 parameters."""
    clean_species = ["".join(ch for ch in s if ch.isalpha()) for s in species]
    if "O" not in clean_species:
        return None
    cations = [s for s in clean_species if s != "O"]
    if not cations or not all(c in BVS_OXIDE_R0 for c in cations):
        return None

    shifts = [
        dx * lattice_matrix[0] + dy * lattice_matrix[1] + dz * lattice_matrix[2]
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
    ]

    anomalies: list[dict[str, Any]] = []
    bvs_values: dict[str, list[float]] = {}
    oxygen_indices = [idx for idx, el in enumerate(clean_species) if el == "O"]

    for i, el in enumerate(clean_species):
        if el == "O":
            continue
        r0, expected_val = BVS_OXIDE_R0[el]
        bvs = 0.0
        for j in oxygen_indices:
            r_ij = coords_cart[j] - coords_cart[i]
            d_min = min(float(np.linalg.norm(r_ij + sh)) for sh in shifts)
            if 0.7 <= d_min <= 3.5:
                bvs += math.exp((r0 - d_min) / 0.37)

        bvs_values.setdefault(el, []).append(round(bvs, 3))
        if abs(bvs - expected_val) > 1.5:
            anomalies.append({
                "site": f"{el}#{i}",
                "computed_bvs": round(bvs, 3),
                "expected_valence": expected_val,
            })

    return {"bvs_by_element": bvs_values, "anomalies": anomalies}


def validate_crystal_structure(
    structure_text: str,
    format: str = "cif",
    claimed_spacegroup: str | int | None = None,
    min_interatomic_distance_angstrom: float = 0.7,
    check_bvs: bool = True,
) -> VerificationResult:
    """Validate crystal structure syntax, interatomic distances, density, BVS, and space group."""
    clean_text = structure_text.strip()
    if not clean_text:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty structure text provided.",
            details={"format": format}
        )

    fmt = format.strip().lower()
    lattice_matrix = None
    coords_frac = np.array([])
    coords_cart = np.array([])
    species: list[str] = []
    volume = 0.0
    computed_sg_number = None
    computed_sg_symbol = None
    parsing_engine = "fallback"

    # 1a. Try pymatgen
    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

        struct = Structure.from_str(clean_text, fmt=fmt)
        lattice_matrix = np.array(struct.lattice.matrix, dtype=float)
        coords_cart = np.array(struct.cart_coords, dtype=float)
        coords_frac = np.array(struct.frac_coords, dtype=float)
        species = [str(sp) for sp in struct.species]
        volume = float(struct.volume)
        parsing_engine = "pymatgen"

        sga = SpacegroupAnalyzer(struct, symprec=0.01)
        computed_sg_number = sga.get_space_group_number()
        computed_sg_symbol = sga.get_space_group_symbol()
    except Exception:
        # 1b. Try ASE fallback
        ase_parsed = False
        try:
            from ase.io import read as ase_read

            ase_fmt = "vasp" if fmt in ("poscar", "contcar", "vasp") else fmt
            atoms_raw = ase_read(StringIO(clean_text), format=ase_fmt)
            if isinstance(atoms_raw, list):
                if not atoms_raw:
                    raise ValueError("ASE parsed zero atomic frames.")
                atoms_obj = atoms_raw[0]
            else:
                atoms_obj = atoms_raw
            lattice_matrix = np.array(atoms_obj.get_cell().array, dtype=float)
            coords_cart = np.array(atoms_obj.get_positions(), dtype=float)
            coords_frac = np.array(atoms_obj.get_scaled_positions(), dtype=float)
            species = list(atoms_obj.get_chemical_symbols())
            volume = float(abs(np.linalg.det(lattice_matrix)))
            parsing_engine = "ase"
            ase_parsed = True
        except Exception:
            ase_parsed = False

        # 1c. Built-in CIF / POSCAR fallback
        if not ase_parsed:
            if fmt == "cif":
                try:
                    parsed = parse_cif_fallback(clean_text)
                    lattice_matrix = compute_lattice_matrix(
                        parsed["a"], parsed["b"], parsed["c"],
                        parsed["alpha"], parsed["beta"], parsed["gamma"]
                    )
                    volume = float(abs(np.linalg.det(lattice_matrix)))
                    atoms = parsed["atoms"]
                    if atoms:
                        coords_frac = np.array([a["coords"] for a in atoms], dtype=float)
                        coords_cart = coords_frac @ lattice_matrix
                        species = [a["element"] for a in atoms]
                    if claimed_spacegroup is None and parsed.get("claimed_sg"):
                        claimed_spacegroup = parsed["claimed_sg"]
                except Exception as e:
                    return VerificationResult(
                        status=VerificationStatus.ERROR,
                        summary=f"Failed to parse CIF crystal structure: {e}",
                        details={"error": str(e), "format": format}
                    )
            elif fmt in ("poscar", "contcar", "vasp"):
                try:
                    parsed = parse_poscar_fallback(clean_text)
                    lattice_matrix = parsed["lattice_matrix"]
                    coords_frac = parsed["coords_frac"]
                    coords_cart = parsed["coords_cart"]
                    species = parsed["species"]
                    volume = float(abs(np.linalg.det(lattice_matrix)))
                except Exception as e:
                    return VerificationResult(
                        status=VerificationStatus.ERROR,
                        summary=f"Failed to parse POSCAR crystal structure: {e}",
                        details={"error": str(e), "format": format}
                    )
            else:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Unsupported structure format '{format}'. Use 'cif' or 'poscar'.",
                    details={"format": format}
                )

    if lattice_matrix is None or len(coords_cart) == 0:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="No valid atomic positions or lattice found in crystal structure.",
            details={"format": format}
        )

    # Run spglib symmetry analysis if pymatgen didn't compute it
    if computed_sg_number is None and len(coords_frac) > 0:
        try:
            import spglib
            species_map = {sp: idx + 1 for idx, sp in enumerate(sorted(set(species)))}
            numbers = [species_map[s] for s in species]
            cell = (lattice_matrix.tolist(), coords_frac.tolist(), numbers)
            dataset = spglib.get_symmetry_dataset(cell, symprec=1e-2)
            if dataset is not None:
                computed_sg_number = int(getattr(dataset, "number", 0) or dataset["number"])
                computed_sg_symbol = str(getattr(dataset, "international", "") or dataset["international"])
        except Exception:
            pass

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
                "engine": parsing_engine,
                "min_interatomic_distance_angstrom": min_dist,
                "threshold_angstrom": min_interatomic_distance_angstrom,
                "closest_pair": pair_info,
                "total_atoms": len(species),
                "volume_angstrom3": volume,
            }
        )

    # 3. Density plausibility check
    density = compute_density_g_cm3(species, volume)
    bvs_report = check_oxide_bond_valence_sums(species, coords_cart, lattice_matrix) if check_bvs else None

    details = {
        "engine": parsing_engine,
        "total_atoms": len(species),
        "formula": "".join(species),
        "volume_angstrom3": round(volume, 4),
        "density_g_cm3": round(density, 4) if density is not None else None,
        "min_interatomic_distance_angstrom": round(min_dist, 4),
        "computed_spacegroup_number": computed_sg_number,
        "computed_spacegroup_symbol": computed_sg_symbol,
        "bvs_report": bvs_report,
    }

    if density is not None and (density < 0.3 or density > 25.0):
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Unphysical crystal density ({density:.2f} g/cm\u00b3 outside plausible range 0.3–25.0 g/cm\u00b3).",
            details=details,
        )

    if bvs_report and bvs_report.get("anomalies"):
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Bond Valence Sum (BVS) anomaly detected for {len(bvs_report['anomalies'])} cation site(s): "
                "unphysical coordination environment."
            ),
            details=details,
        )

    # 4. Check claimed vs computed space group
    if claimed_spacegroup is not None and computed_sg_number is not None:
        claimed_str = str(claimed_spacegroup).strip().lower()
        computed_num_str = str(computed_sg_number)
        computed_sym_str = str(computed_sg_symbol).strip().lower() if computed_sg_symbol else ""

        match = claimed_str in (computed_num_str, computed_sym_str)
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
            f"Crystal structure valid (engine: {parsing_engine}, volume: {volume:.2f} \u00c5\u00b3, "
            f"min distance: {min_dist:.2f} \u00c5, "
            f"space group: {computed_sg_symbol or 'unknown'} [#{computed_sg_number or '?'}])."
        ),
        details=details
    )
