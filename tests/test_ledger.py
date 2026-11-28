"""Unit tests for the persistent SQLite verification provenance ledger and audit certificate."""

import json
from pathlib import Path

from sci_verifier_mcp.core.ledger import AuditLedger, audit_ledger, export_audit_certificate
from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.server import (
    check_dimensional_analysis,
    check_equation_equivalence,
)
from sci_verifier_mcp.server import (
    export_audit_certificate as server_export_cert,
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

    md_cert = server_export_cert(title="Session Test Audit", format="markdown", clear_after_export=False)
    assert md_cert["status"] == VerificationStatus.VERIFIED.value
    assert md_cert["details"]["summary_counts"]["total"] == 2
    assert "# Session Test Audit" in md_cert["details"]["certificate"]
    assert "check_equation_equivalence" in md_cert["details"]["certificate"]

    json_cert = server_export_cert(title="JSON Audit", format="json", clear_after_export=True)
    parsed = json.loads(json_cert["details"]["certificate"])
    assert parsed["summary_counts"]["verified"] == 2
    assert len(audit_ledger.get_entries()) == 0


def test_audit_ledger_persists_across_restarts(tmp_path: Path):
    db_file = tmp_path / "audit_persist.sqlite"
    ledger_one = AuditLedger(db_path=db_file)
    ledger_one.record(
        "check_equation_equivalence",
        {"lhs": "x", "rhs": "x"},
        {"status": "verified", "summary": "Identical", "sources": ["https://example.org/1"]},
    )

    # Re-instantiate against the same SQLite path to simulate process restart
    ledger_two = AuditLedger(db_path=db_file)
    entries = ledger_two.get_entries()
    assert len(entries) == 1
    assert entries[0]["tool"] == "check_equation_equivalence"
    assert entries[0]["sources"] == ["https://example.org/1"]

    cert = export_audit_certificate(title="Restart Audit", format="markdown", clear_after_export=True, ledger=ledger_two)
    assert cert.details["summary_counts"]["total"] == 1
    assert len(ledger_two.get_entries()) == 0
