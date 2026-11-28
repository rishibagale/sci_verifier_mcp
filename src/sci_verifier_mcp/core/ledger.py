"""Session verification provenance ledger and audit certificate exporter."""

import json
import threading
from datetime import UTC, datetime
from typing import Any

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


class AuditLedger:
    """Thread-safe in-memory provenance ledger recording tool verification checks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []

    def record(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Append a verification check record to the session ledger."""
        # Truncate large raw inputs (e.g. long CIF/Lean blobs) for clean certificates
        compact_inputs: dict[str, Any] = {}
        for k, v in inputs.items():
            s = str(v)
            compact_inputs[k] = (s[:160] + "...") if len(s) > 160 else v

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool_name,
            "status": result.get("status", "unknown"),
            "summary": result.get("summary", ""),
            "inputs": compact_inputs,
            "sources": result.get("sources", []),
        }
        with self._lock:
            self._entries.append(entry)

    def get_entries(self) -> list[dict[str, Any]]:
        """Return a shallow copy of recorded audit entries."""
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        """Reset recorded session entries."""
        with self._lock:
            self._entries.clear()


audit_ledger = AuditLedger()


def export_audit_certificate(
    title: str = "SciVerifier Audit Report",
    format: str = "markdown",
    clear_after_export: bool = False,
) -> VerificationResult:
    """Export a peer-reviewable provenance certificate of all verification checks in the session."""
    entries = audit_ledger.get_entries()
    fmt = format.strip().lower()
    if fmt not in ("markdown", "json"):
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Unsupported certificate format '{format}'. Use 'markdown' or 'json'.",
            details={},
        )

    counts = {
        "total": len(entries),
        "verified": sum(1 for e in entries if e["status"] == "verified"),
        "failed": sum(1 for e in entries if e["status"] == "failed"),
        "partial_match": sum(1 for e in entries if e["status"] == "partial_match"),
        "unavailable": sum(1 for e in entries if e["status"] == "unavailable"),
        "error": sum(1 for e in entries if e["status"] in ("error", "timeout")),
    }
    all_sources = list(dict.fromkeys(src for e in entries for src in e.get("sources", [])))

    if fmt == "json":
        certificate_body = json.dumps(
            {
                "title": title,
                "generated_at": datetime.now(UTC).isoformat(),
                "summary_counts": counts,
                "entries": entries,
                "sources": all_sources,
            },
            indent=2,
        )
    else:
        lines = [
            f"# {title}",
            f"- **Generated (UTC)**: {datetime.now(UTC).isoformat()}",
            f"- **Checks Recorded**: {counts['total']} "
            f"({counts['verified']} verified, {counts['failed']} failed, "
            f"{counts['partial_match']} partial, {counts['unavailable']} unavailable, {counts['error']} error/timeout)",
            "",
            "| # | Tool | Status | Summary |",
            "|---|---|---|---|",
        ]
        for idx, e in enumerate(entries, start=1):
            safe_summary = str(e["summary"]).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {idx} | `{e['tool']}` | `{e['status']}` | {safe_summary} |")
        if all_sources:
            lines.append("")
            lines.append("## Provenance Sources")
            for s in all_sources:
                lines.append(f"- {s}")
        certificate_body = "\n".join(lines)

    if clear_after_export:
        audit_ledger.clear()

    return VerificationResult(
        status=VerificationStatus.VERIFIED if counts["failed"] == 0 else VerificationStatus.PARTIAL_MATCH,
        summary=f"Exported {fmt} verification certificate covering {counts['total']} check(s).",
        details={
            "format": fmt,
            "summary_counts": counts,
            "certificate": certificate_body,
            "entries": entries,
        },
        sources=all_sources,
    )
