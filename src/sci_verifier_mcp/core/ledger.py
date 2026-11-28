"""Persistent SQLite-backed session verification provenance ledger and audit certificate exporter."""

import contextlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


class AuditLedger:
    """Thread-safe provenance ledger backed by SQLite so trails survive server restarts."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self.db_path = Path(db_path or config.AUDIT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=10.0)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL
                )
            """)
            conn.commit()

    def record(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Append a verification check record to the persistent SQLite ledger."""
        compact_inputs: dict[str, Any] = {}
        for k, v in inputs.items():
            s = str(v)
            compact_inputs[k] = (s[:160] + "...") if len(s) > 160 else v

        timestamp = datetime.now(UTC).isoformat()
        status = str(result.get("status", "unknown"))
        summary = str(result.get("summary", ""))
        inputs_json = json.dumps(compact_inputs, default=str)
        sources_json = json.dumps(result.get("sources", []), default=str)

        with self._lock, contextlib.suppress(Exception), self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_entries (timestamp, tool, status, summary, inputs_json, sources_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (timestamp, tool_name, status, summary, inputs_json, sources_json),
            )
            conn.commit()

    def get_entries(self) -> list[dict[str, Any]]:
        """Return all recorded audit entries ordered chronologically."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    rows = conn.execute(
                        "SELECT timestamp, tool, status, summary, inputs_json, sources_json "
                        "FROM audit_entries ORDER BY id ASC"
                    ).fetchall()
                return [
                    {
                        "timestamp": row[0],
                        "tool": row[1],
                        "status": row[2],
                        "summary": row[3],
                        "inputs": json.loads(row[4]),
                        "sources": json.loads(row[5]),
                    }
                    for row in rows
                ]
            except Exception:
                return []

    def clear(self) -> None:
        """Delete all recorded audit entries from the ledger."""
        with self._lock, contextlib.suppress(Exception), self._get_connection() as conn:
            conn.execute("DELETE FROM audit_entries")
            conn.commit()


audit_ledger = AuditLedger()


def export_audit_certificate(
    title: str = "SciVerifier Audit Report",
    format: str = "markdown",
    clear_after_export: bool = False,
    ledger: AuditLedger | None = None,
) -> VerificationResult:
    """Export a peer-reviewable provenance certificate of all verification checks in the ledger."""
    active_ledger = ledger or audit_ledger
    entries = active_ledger.get_entries()
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
            (
                f"- **Checks Recorded**: {counts['total']} "
                f"({counts['verified']} verified, {counts['failed']} failed, "
                f"{counts['partial_match']} partial, {counts['unavailable']} unavailable, "
                f"{counts['error']} error/timeout)"
            ),
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
        active_ledger.clear()

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
