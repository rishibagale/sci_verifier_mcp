"""Standardized response models across all verification tools."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL_MATCH = "partial_match"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    ERROR = "error"


class VerificationResult(BaseModel):
    """Unified response contract for all SciVerifier tools."""
    status: VerificationStatus = Field(
        ...,
        description="Verification outcome: verified, failed, partial_match, unavailable, timeout, or error"
    )
    summary: str = Field(
        ...,
        description="Concise human-readable explanation of the result"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured diagnostics, counterexamples, metrics, or breakdown"
    )
    sources: list[str] = Field(
        default_factory=list,
        description="URLs, DOIs, arXiv IDs, or database references backing the verification"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a standard dictionary with string status."""
        return {
            "status": self.status.value,
            "summary": self.summary,
            "details": self.details,
            "sources": self.sources,
        }
