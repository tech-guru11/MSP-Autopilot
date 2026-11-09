from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str
    observation: str
    supports: str


class CauseHypothesis(BaseModel):
    title: str
    explanation: str
    confidence: Literal["low", "medium", "high"]
    evidence_sources: list[str] = Field(default_factory=list)


class RemediationRecommendation(BaseModel):
    action: str
    reason: str
    risk: Literal["low", "medium", "high", "critical"]
    reversible: bool
    requires_approval: bool


class InvestigationResult(BaseModel):
    incident_summary: str
    severity_assessment: Literal["P1", "P2", "P3", "P4"]
    hypotheses: list[CauseHypothesis] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommendation: RemediationRecommendation
    verification_steps: list[str] = Field(default_factory=list)
