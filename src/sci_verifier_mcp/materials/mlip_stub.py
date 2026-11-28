"""Optional Machine Learning Interatomic Potential (MACE / CHGNet) relaxation & sanity plugin."""

from io import StringIO

import numpy as np

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def relax_and_score_mlip(
    structure_text: str,
    format: str = "cif",
    model: str = "mace",
    fmax: float = 0.05,
    max_steps: int = 50,
) -> VerificationResult:
    """Relax and evaluate atomic forces/energy delta via MACE or CHGNet (graceful unavailable fallback)."""
    clean_text = structure_text.strip()
    if not clean_text:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty crystal structure text provided.",
            details={}
        )

    model_name = model.strip().lower()
    if model_name not in ("mace", "chgnet"):
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Unsupported MLIP model '{model}'. Choose 'mace' or 'chgnet'.",
            details={}
        )

    try:
        from ase.io import read as ase_read
        from ase.optimize import BFGS
    except ImportError:
        return VerificationResult(
            status=VerificationStatus.UNAVAILABLE,
            summary=f"ASE and MLIP backend ('{model_name}') are not installed on this host.",
            details={
                "model": model_name,
                "help": "Install ASE + MACE (`pip install ase mace-torch`) or CHGNet (`pip install ase chgnet`).",
            },
        )

    calc = None
    if model_name == "mace":
        try:
            from mace.calculators import mace_mp
            calc = mace_mp(model="medium", default_dtype="float32")
        except ImportError:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                summary="MACE calculator (`mace-torch`) is not installed on this host.",
                details={"help": "Install via: pip install mace-torch ase"},
            )
    else:
        try:
            from chgnet.model.dynamics import CHGNetCalculator
            calc = CHGNetCalculator()
        except ImportError:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                summary="CHGNet calculator (`chgnet`) is not installed on this host.",
                details={"help": "Install via: pip install chgnet ase"},
            )

    try:
        ase_fmt = "vasp" if format.lower() in ("poscar", "contcar", "vasp") else format.lower()
        atoms_raw = ase_read(StringIO(clean_text), format=ase_fmt)
        if isinstance(atoms_raw, list):
            if not atoms_raw:
                raise ValueError("ASE parsed zero atomic frames.")
            atoms = atoms_raw[0]
        else:
            atoms = atoms_raw
        atoms.calc = calc
        initial_energy = float(atoms.get_potential_energy())
        initial_forces = atoms.get_forces()
        initial_fmax = float(np.max(np.linalg.norm(initial_forces, axis=1)))

        opt = BFGS(atoms, logfile=None)
        converged = bool(opt.run(fmax=fmax, steps=max_steps))
        final_energy = float(atoms.get_potential_energy())
        final_fmax = float(np.max(np.linalg.norm(atoms.get_forces(), axis=1)))
        delta_e_per_atom = (final_energy - initial_energy) / max(len(atoms), 1)

        return VerificationResult(
            status=VerificationStatus.VERIFIED if converged else VerificationStatus.PARTIAL_MATCH,
            summary=(
                f"MLIP ({model_name}) relaxation {'converged' if converged else 'hit step limit'}: "
                f"dE = {delta_e_per_atom:.4f} eV/atom, fmax {initial_fmax:.3f} -> {final_fmax:.3f} eV/\u00c5."
            ),
            details={
                "model": model_name,
                "converged": converged,
                "initial_energy_ev": initial_energy,
                "final_energy_ev": final_energy,
                "delta_e_per_atom_ev": delta_e_per_atom,
                "initial_fmax": initial_fmax,
                "final_fmax": final_fmax,
            },
        )
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"MLIP evaluation failed: {e}",
            details={"error": str(e), "model": model_name},
        )
