"""Unit tests for the session verification provenance ledger and audit certificate."""

import json

from sci_verifier_mcp.core.ledger import audit_ledger
from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.server import (
    check_dimensional_analysis,
    check_equation_equivalence,
    export_audit_certificate,
)


def test_audit_ledger_records_and_exports_certificates():
    audit_ledger.clear()

    r1 = check_equation_equivalence(lhs="(x+1)**2", rhs="x**2 + 2*x + 1", format="sympy")
    r2 = check_dimensional_analysis(
        equation="E = m * c**2",
        symbol_units={"E": "joule", "m": "kg", "c": "m/s"},
    )
    assert r1["status"] == "verified"
    assert r2["status"] == "verified"

    md_cert = export_audit_certificate(title="Session Test Audit", format="markdown", clear_after_export=False)
    assert md_cert["status"] == VerificationStatus.VERIFIED.value
    assert md_cert["details"]["summary_counts"]["total"] == 2
    assert "# Session Test Audit" in md_cert["details"]["certificate"]
    assert "check_equation_equivalence" in md_cert["details"]["certificate"]

    json_cert = export_audit_certificate(title="JSON Audit", format="json", clear_after_export=True)
    parsed = json.loads(json_cert["details"]["certificate"])
    assert parsed["summary_counts"]["verified"] == 2
    assert len(audit_ledger.get_entries()) == 0
