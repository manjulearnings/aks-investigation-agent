import os
import json
from pathlib import Path
from typing import Union, Optional, TextIO, Dict, Any, List
import httpx
from .models import InvestigationReport, AzureClusterMetadata
from .parser import AKSLogParser
from .engine import InvestigationEngine
from .azure_ai import AzureOpenAIInvestigator
from .azure_monitor import AzureMonitorLogFetcher
from .reporters import TerminalReporter, MarkdownReporter, JSONReporter, TeamsAdaptiveCardReporter


class AKSInvestigationAgent:
    """Enterprise Autonomous Investigation Agent for Azure Kubernetes Service (AKS).

    Combines:
      - Ultra-fast deterministic causal rule engine for AKS failure modes
        (Azure CNI IP exhaustion, Azure Disk locks, Key Vault CSI, ACR RBAC, Spot evictions)
      - Direct Azure Log Analytics / Azure Monitor KQL ingestion
      - Azure OpenAI Service (GPT-4o) with Managed Identity (DefaultAzureCredential)
      - Rich reporting to Terminal, Markdown, JSON, and Microsoft Teams
    """

    def __init__(
        self,
        azure_openai_endpoint: Optional[str] = None,
        azure_openai_deployment: Optional[str] = None,
        azure_openai_key: Optional[str] = None,
        force_ai: bool = False,
        workspace_id: Optional[str] = None,
    ):
        self.parser = AKSLogParser()
        self.engine = InvestigationEngine()
        self.ai = AzureOpenAIInvestigator(
            endpoint=azure_openai_endpoint,
            deployment=azure_openai_deployment,
            api_key=azure_openai_key,
        )
        self.monitor_fetcher = AzureMonitorLogFetcher(workspace_id=workspace_id)
        self.force_ai = force_ai

        self.terminal_reporter = TerminalReporter()
        self.markdown_reporter = MarkdownReporter()
        self.json_reporter = JSONReporter()
        self.teams_reporter = TeamsAdaptiveCardReporter()

    def investigate(
        self,
        log_input: Union[str, Path, TextIO],
        source_name: Optional[str] = None,
        azure_metadata: Optional[AzureClusterMetadata] = None,
    ) -> InvestigationReport:
        """Performs end-to-end causal investigation of AKS logs."""
        raw_text, detected_source = self._load_log_content(log_input)
        effective_source = source_name or detected_source

        # 1. Parse into structured log entries
        entries = self.parser.parse_text(raw_text)

        # 2. Run deterministic causal failure analysis
        report = self.engine.analyze(
            entries,
            source_name=effective_source,
            azure_metadata=azure_metadata,
        )

        # 3. Azure OpenAI Enrichment (for unclassified errors or when forced)
        if self.ai.is_available():
            if report.root_cause_category in ("APPLICATION_ERROR", "APPLICATION_PANIC") or self.force_ai:
                report = self.ai.diagnose_unknown_failure(report)
        elif report.root_cause_category in ("APPLICATION_ERROR", "APPLICATION_PANIC"):
            report.detailed_findings.append(
                "💡 **Azure OpenAI Tip**: Configure AZURE_OPENAI_ENDPOINT (and Managed Identity / API Key) "
                "to unlock deep AI diagnosis and code-level fixes for custom application exceptions."
            )

        return report

    def investigate_file(
        self, filepath: Union[str, Path], azure_metadata: Optional[AzureClusterMetadata] = None
    ) -> InvestigationReport:
        """Convenience helper to investigate a log file on disk."""
        path_obj = Path(filepath)
        if not path_obj.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        return self.investigate(path_obj, source_name=path_obj.name, azure_metadata=azure_metadata)

    def investigate_azure_monitor(
        self,
        pod_name: str,
        namespace: Optional[str] = None,
        hours: int = 2,
        workspace_id: Optional[str] = None,
    ) -> InvestigationReport:
        """Queries Azure Log Analytics directly via KQL and analyzes the returned telemetry."""
        records = self.monitor_fetcher.fetch_pod_logs(
            pod_name=pod_name,
            namespace=namespace,
            hours=hours,
            workspace_id=workspace_id,
        )

        source_label = f"AzureLogAnalytics:{workspace_id or self.monitor_fetcher.workspace_id} (pod/{pod_name})"
        raw_json_str = json.dumps(records)

        meta = AzureClusterMetadata(
            workspace_id=workspace_id or self.monitor_fetcher.workspace_id,
        )

        return self.investigate(raw_json_str, source_name=source_label, azure_metadata=meta)

    def print_terminal_report(self, report: InvestigationReport):
        self.terminal_reporter.render(report)

    def export_markdown(self, report: InvestigationReport) -> str:
        return self.markdown_reporter.render(report)

    def export_json(self, report: InvestigationReport) -> str:
        return self.json_reporter.render(report)

    def export_teams_card(self, report: InvestigationReport) -> Dict[str, Any]:
        return self.teams_reporter.render(report)

    def post_to_teams_webhook(self, report: InvestigationReport, webhook_url: str) -> bool:
        """Posts an interactive Adaptive Card report to a Microsoft Teams Incoming Webhook."""
        card_payload = self.export_teams_card(report)
        with httpx.Client(timeout=10.0) as client:
            res = client.post(webhook_url, json=card_payload)
            return res.status_code in (200, 202)

    def _load_log_content(self, log_input: Union[str, Path, TextIO]) -> tuple[str, str]:
        if isinstance(log_input, Path):
            return log_input.read_text(encoding="utf-8", errors="replace"), log_input.name

        if isinstance(log_input, str):
            # Check if this string is a path on disk
            try:
                candidate = Path(log_input)
                if candidate.exists() and candidate.is_file():
                    return candidate.read_text(encoding="utf-8", errors="replace"), candidate.name
            except Exception:
                pass
            return log_input, "text_input"

        if hasattr(log_input, "read"):
            content = log_input.read()
            name = getattr(log_input, "name", "stream_input")
            return content, name

        raise ValueError(f"Unsupported log input type: {type(log_input)}")

