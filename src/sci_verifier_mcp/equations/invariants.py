"""Physical invariant and convergence auditing for numerical simulation outputs."""

import math
from typing import Any

import numpy as np

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def verify_simulation_invariants(
    data: dict[str, Any] | list[Any],
    checks: list[str],
    tolerance: float = 1e-6,
) -> VerificationResult:
    """Verify conservation laws, probability normalization, matrix PSD/unitarity, or grid convergence order."""
    if not checks:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Provide at least one invariant check (e.g. 'conservation', 'probability_norm', 'psd', 'unitary', 'convergence_order').",
            details={}
        )

    report: dict[str, Any] = {}
    failures: list[str] = []

    for raw_check in checks:
        chk = raw_check.strip().lower()

        try:
            if chk in ("conservation", "energy_conservation", "mass_conservation"):
                series_map = data if isinstance(data, dict) else {"trajectory": data}
                series_report = {}
                for name, vals in series_map.items():
                    if not isinstance(vals, list) or len(vals) < 2:
                        continue
                    arr = np.asarray(vals, dtype=float)
                    ref = float(arr[0])
                    max_abs_drift = float(np.max(np.abs(arr - ref)))
                    rel_drift = max_abs_drift / max(abs(ref), 1.0)
                    passed = rel_drift <= tolerance
                    series_report[name] = {
                        "initial": ref,
                        "max_abs_drift": max_abs_drift,
                        "max_rel_drift": rel_drift,
                        "passed": passed,
                    }
                    if not passed:
                        failures.append(f"{chk}:{name} (rel drift {rel_drift:.3e} > {tolerance:.3e})")
                if not series_report:
                    failures.append(f"{chk}: no valid 1D trajectories (>= 2 points) found")
                report[chk] = series_report

            elif chk == "probability_norm":
                raw_vals = data.get("probabilities", data) if isinstance(data, dict) else data
                prob_arr = np.asarray(raw_vals, dtype=float)
                prob_2d = prob_arr.reshape(1, -1) if prob_arr.ndim == 1 else prob_arr
                min_entry = float(np.min(prob_2d))
                sums = np.sum(prob_2d, axis=-1)
                max_norm_err = float(np.max(np.abs(sums - 1.0)))
                passed = (min_entry >= -tolerance) and (max_norm_err <= tolerance)
                report[chk] = {
                    "min_entry": min_entry,
                    "max_sum_deviation_from_1": max_norm_err,
                    "passed": passed,
                }
                if not passed:
                    failures.append(f"probability_norm (min={min_entry:.3e}, norm_err={max_norm_err:.3e})")

            elif chk in ("hermitian", "psd"):
                raw_mat = data.get("matrix", data) if isinstance(data, dict) else data
                mat = np.asarray(raw_mat, dtype=complex)
                if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
                    raise ValueError("Matrix check requires a square 2D matrix.")
                herm_err = float(np.max(np.abs(mat - mat.conj().T)))
                eigvals = np.linalg.eigvalsh(0.5 * (mat + mat.conj().T))
                min_eig = float(np.min(eigvals.real))
                passed = herm_err <= tolerance and (chk == "hermitian" or min_eig >= -tolerance)
                report[chk] = {
                    "hermiticity_error": herm_err,
                    "min_eigenvalue": min_eig,
                    "passed": passed,
                }
                if not passed:
                    failures.append(f"{chk} (herm_err={herm_err:.3e}, min_eig={min_eig:.3e})")

            elif chk == "unitary":
                raw_mat = data.get("matrix", data) if isinstance(data, dict) else data
                mat = np.asarray(raw_mat, dtype=complex)
                if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
                    raise ValueError("Unitary check requires a square 2D matrix.")
                ident = np.eye(mat.shape[0], dtype=complex)
                unit_err = float(np.max(np.abs(mat.conj().T @ mat - ident)))
                passed = unit_err <= tolerance
                report[chk] = {"unitarity_error": unit_err, "passed": passed}
                if not passed:
                    failures.append(f"unitary (err={unit_err:.3e})")

            elif chk == "convergence_order":
                if not isinstance(data, dict) or "h" not in data or "error" not in data:
                    raise ValueError("convergence_order requires dict with 'h' and 'error' lists.")
                h_arr = np.asarray(data["h"], dtype=float)
                e_arr = np.asarray(data["error"], dtype=float)
                if len(h_arr) < 2 or len(h_arr) != len(e_arr):
                    raise ValueError("'h' and 'error' must have equal length >= 2.")
                if np.any(h_arr <= 0) or np.any(e_arr <= 0):
                    raise ValueError("'h' and 'error' values must be strictly positive.")
                slope, _ = np.polyfit(np.log(h_arr), np.log(e_arr), 1)
                observed_order = float(slope)
                expected_order = data.get("expected_order")
                order_tol = float(data.get("order_tolerance", 0.25))
                passed = True
                if expected_order is not None:
                    passed = abs(observed_order - float(expected_order)) <= order_tol
                else:
                    passed = math.isfinite(observed_order) and observed_order > 0
                report[chk] = {
                    "observed_order": round(observed_order, 4),
                    "expected_order": expected_order,
                    "passed": passed,
                }
                if not passed:
                    failures.append(f"convergence_order (observed={observed_order:.3f}, expected={expected_order})")

            else:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Unsupported invariant check '{raw_check}'.",
                    details={"supported": ["conservation", "probability_norm", "hermitian", "psd", "unitary", "convergence_order"]}
                )

        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to evaluate invariant '{raw_check}': {e}",
                details={"check": raw_check, "error": str(e)}
            )

    if failures:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Simulation invariant violation(s) detected: {'; '.join(failures)}.",
            details={"checks": report, "failures": failures, "tolerance": tolerance},
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=f"All {len(checks)} simulation invariant check(s) passed within tolerance {tolerance:.1e}.",
        details={"checks": report, "tolerance": tolerance},
    )
