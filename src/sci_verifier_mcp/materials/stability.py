"""Mechanical (Born elastic criteria) and dynamical (phonon) stability verification for crystals."""

from typing import Any

import numpy as np

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def check_elastic_and_phonon_stability(
    elastic_tensor_gpa: list[list[float]] | None = None,
    phonon_frequencies_thz: list[float] | None = None,
    imaginary_threshold_thz: float = -0.1,
) -> VerificationResult:
    """Verify Born mechanical stability criteria on 6x6 Voigt elastic tensor C_ij and phonon stability."""
    if elastic_tensor_gpa is None and phonon_frequencies_thz is None:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Provide at least one of 'elastic_tensor_gpa' (6x6 matrix) or 'phonon_frequencies_thz'.",
            details={}
        )

    details: dict[str, Any] = {}
    failures: list[str] = []

    if elastic_tensor_gpa is not None:
        try:
            c_mat = np.asarray(elastic_tensor_gpa, dtype=float)
            if c_mat.shape != (6, 6):
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Elastic tensor must be a 6x6 Voigt matrix, got shape {c_mat.shape}.",
                    details={"shape": list(c_mat.shape)}
                )
            asym = float(np.max(np.abs(c_mat - c_mat.T)))
            if asym > 1.0:
                failures.append(f"Elastic tensor is asymmetric (max |C - C^T| = {asym:.2f} GPa)")

            c_sym = 0.5 * (c_mat + c_mat.T)
            eigvals = np.linalg.eigvalsh(c_sym)
            min_eig = float(np.min(eigvals))

            # Voigt bulk (B_V) and shear (G_V) moduli in GPa
            b_voigt = float(
                (c_sym[0, 0] + c_sym[1, 1] + c_sym[2, 2]
                 + 2.0 * (c_sym[0, 1] + c_sym[1, 2] + c_sym[0, 2])) / 9.0
            )
            g_voigt = float(
                (c_sym[0, 0] + c_sym[1, 1] + c_sym[2, 2]
                 - (c_sym[0, 1] + c_sym[1, 2] + c_sym[0, 2])
                 + 3.0 * (c_sym[3, 3] + c_sym[4, 4] + c_sym[5, 5])) / 15.0
            )
            born_stable = min_eig > 0.0 and b_voigt > 0.0 and g_voigt > 0.0
            if not born_stable:
                failures.append(
                    f"Violates Born mechanical stability (min eigenvalue = {min_eig:.3f} GPa, B_V = {b_voigt:.2f}, G_V = {g_voigt:.2f})"
                )

            details["elastic"] = {
                "born_stable": born_stable,
                "eigenvalues_gpa": [round(float(v), 4) for v in eigvals],
                "min_eigenvalue_gpa": round(min_eig, 4),
                "voigt_bulk_modulus_gpa": round(b_voigt, 3),
                "voigt_shear_modulus_gpa": round(g_voigt, 3),
                "symmetry_deviation_gpa": round(asym, 4),
            }
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to analyze elastic tensor: {e}",
                details={"error": str(e)}
            )

    if phonon_frequencies_thz is not None:
        try:
            freqs = np.asarray(phonon_frequencies_thz, dtype=float)
            imaginary_modes = [float(f) for f in freqs if f < imaginary_threshold_thz]
            min_freq = float(np.min(freqs)) if len(freqs) > 0 else 0.0
            dynamically_stable = len(imaginary_modes) == 0
            if not dynamically_stable:
                failures.append(
                    f"Dynamically unstable: {len(imaginary_modes)} imaginary phonon mode(s) below {imaginary_threshold_thz} THz (min = {min_freq:.3f} THz)"
                )
            details["phonon"] = {
                "dynamically_stable": dynamically_stable,
                "total_modes": int(len(freqs)),
                "min_frequency_thz": round(min_freq, 4),
                "imaginary_modes_thz": imaginary_modes,
            }
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to analyze phonon frequencies: {e}",
                details={"error": str(e)}
            )

    if failures:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="; ".join(failures),
            details=details,
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary="Crystal passes all evaluated mechanical (Born) and/or dynamical (phonon) stability checks.",
        details=details,
    )
