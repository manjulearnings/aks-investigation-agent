from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class EvidenceConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TimelinePhase(str, Enum):
    INCEPTION = "INCEPTION"
    PROPAGATION = "PROPAGATION"
    KUBELET_ACTION = "KUBELET_ACTION"
    AZURE_INTERVENTION = "AZURE_INTERVENTION"


class AzureClusterMetadata(BaseModel):
    """Azure Kubernetes Service context metadata."""
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    cluster_name: Optional[str] = None
    node_pool: Optional[str] = None
    region: Optional[str] = None
    workspace_id: Optional[str] = None


class FindingEvidence(BaseModel):
    """Empirical supporting evidence linking findings to exact log lines."""
    line_numbers: List[int] = Field(default_factory=list)
    timestamp: Optional[str] = None
    log_snippet: str
    signal_type: str
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH


class TimelineEvent(BaseModel):
    """Chronological event mapping incident progression."""
    timestamp: Optional[str] = None
    phase: TimelinePhase
    description: str
    log_snippet: Optional[str] = None


class FailureTimeline(BaseModel):
    """Structured incident progression timeline."""
    events: List[TimelineEvent] = Field(default_factory=list)


class RemediationStep(BaseModel):
    """Actionable mitigation or prevention instruction."""
    action_type: str = Field(description="IMMEDIATE, AZURE_CLI, KUBECTL, or PREVENTION")
    description: str
    command: Optional[str] = None
    doc_url: Optional[str] = None


class StructuredLogEntry(BaseModel):
    """Normalized representation of a parsed container or platform log entry."""
    line_number: int
    raw_text: str
    timestamp: Optional[datetime] = None
    timestamp_str: Optional[str] = None
    stream: Optional[str] = None  # stdout, stderr, etc.
    log_level: Optional[str] = None
    message: str
    pod_name: Optional[str] = None
    container_name: Optional[str] = None
    namespace: Optional[str] = None
    is_stack_trace: bool = False
    stack_trace_lines: List[str] = Field(default_factory=list)
    azure_properties: Dict[str, Any] = Field(default_factory=dict)


class InvestigationReport(BaseModel):
    """Comprehensive incident investigation report."""
    incident_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    log_source: str
    azure_metadata: Optional[AzureClusterMetadata] = None
    root_cause_category: str
    root_cause_summary: str
    severity: Severity
    key_evidence: List[FindingEvidence] = Field(default_factory=list)
    timeline: FailureTimeline = Field(default_factory=FailureTimeline)
    remediation_plan: List[RemediationStep] = Field(default_factory=list)
    detailed_findings: List[str] = Field(default_factory=list)
    ai_analysis: Optional[str] = None
    ai_provider: Optional[str] = None

