"""Literature citation verification, retraction/claim auditing, bibliography auditing, and discovery feeds."""

from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography
from sci_verifier_mcp.literature.citation_verifier import verify_citation
from sci_verifier_mcp.literature.claim_alignment import verify_claim_against_paper
from sci_verifier_mcp.literature.discovery_feed import track_recent_discoveries
from sci_verifier_mcp.literature.similarity import find_similar_papers

__all__ = [
    "verify_citation",
    "audit_bibliography",
    "find_similar_papers",
    "verify_claim_against_paper",
    "track_recent_discoveries",
]
