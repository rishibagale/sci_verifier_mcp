"""Literature citation verification, bibliography auditing, and similarity search."""

from sci_verifier_mcp.literature.citation_verifier import verify_citation
from sci_verifier_mcp.literature.bibliography_auditor import audit_bibliography
from sci_verifier_mcp.literature.similarity import find_similar_papers

__all__ = [
    "verify_citation",
    "audit_bibliography",
    "find_similar_papers",
]
