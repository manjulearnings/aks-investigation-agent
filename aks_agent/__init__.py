"""AKS Investigation Agent.

Autonomous incident investigation agent tailored for Azure Kubernetes Service (AKS),
Azure Monitor / Log Analytics, and Azure OpenAI Service.
"""

from .agent import AKSInvestigationAgent
from .models import (
    InvestigationReport,
    FindingEvidence,
    FailureTimeline,
    RemediationStep,
    Severity,
    AzureClusterMetadata,
)

__version__ = "0.1.0"
__all__ = [
    "AKSInvestigationAgent",
    "InvestigationReport",
    "FindingEvidence",
    "FailureTimeline",
    "RemediationStep",
    "Severity",
    "AzureClusterMetadata",
]

