import os
import json
import logging
from typing import Optional, Dict, Any, List
from .models import InvestigationReport, RemediationStep, Severity

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_DEPLOYMENT = "gpt-4o"


class AzureOpenAIInvestigator:
    """Enterprise Azure OpenAI Service integration for AKS incident diagnosis.

    Authenticates seamlessly via:
      1. Azure Entra ID / Managed Identity using DefaultAzureCredential (Zero-secret pattern)
      2. Or explicit Azure OpenAI API Key

    Diagnoses complex or unclassified application stack traces and enriches
    remediation steps with tailored code-level guidance.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.endpoint = (
            endpoint
            or os.environ.get("AZURE_OPENAI_ENDPOINT")
            or os.environ.get("AZURE_OPENAI_BASE_URL")
        )
        self.deployment = (
            deployment
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or os.environ.get("AZURE_OPENAI_MODEL")
            or DEFAULT_DEPLOYMENT
        )
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
        self.api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION") or DEFAULT_API_VERSION
        self._client = None

    def is_available(self) -> bool:
        """Returns True if minimum endpoint configuration is present."""
        return bool(self.endpoint)

    def _get_client(self):
        if self._client is not None:
            return self._client

        from openai import AzureOpenAI

        if self.api_key:
            # Authenticate via API Key
            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )
        else:
            # Enterprise pattern: Authenticate via Azure Entra ID / Managed Identity
            try:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                credential = DefaultAzureCredential()
                token_provider = get_bearer_token_provider(
                    credential, "https://cognitiveservices.azure.com/.default"
                )
                self._client = AzureOpenAI(
                    azure_endpoint=self.endpoint,
                    azure_ad_token_provider=token_provider,
                    api_version=self.api_version,
                )
            except Exception as e:
                logger.error(f"Failed to initialize DefaultAzureCredential for Azure OpenAI: {e}")
                raise

        return self._client

    def diagnose_unknown_failure(self, report: InvestigationReport) -> InvestigationReport:
        """Consults Azure OpenAI to diagnose an unclassified application error or custom panic."""
        if not self.is_available():
            return report

        # Extract context from evidence and timeline
        evidence_texts = []
        for ev in report.key_evidence[:6]:
            lines = ",".join(str(l) for l in ev.line_numbers)
            evidence_texts.append(f"Line {lines} [{ev.timestamp or 'N/A'}]:\n{ev.log_snippet}")

        evidence_str = "\n\n".join(evidence_texts) if evidence_texts else "No raw lines cataloged."

        system_prompt = (
            "You are a Principal Site Reliability Engineer (SRE) specializing in Azure Kubernetes Service (AKS) "
            "and cloud-native application debugging. You diagnose application errors, stack traces, and pod crashes.\n"
            "Analyze the provided log evidence and return a JSON object with this EXACT structure:\n"
            "{\n"
            '  "root_cause_summary": "1-2 sentence precise technical diagnosis of the root cause",\n'
            '  "detailed_findings": ["Bullet 1 with code-level insight", "Bullet 2 with impact on AKS pod"],\n'
            '  "suggested_remediations": [\n'
            '     {"action_type": "IMMEDIATE|KUBECTL|AZURE_CLI|PREVENTION", "description": "...", "command": "optional kubectl or az command"}\n'
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"Incident Source: {report.log_source}\n"
            f"Preliminary Classification: {report.root_cause_category}\n"
            f"Key Log Evidence & Stack Trace:\n{evidence_str}\n\n"
            f"Provide an authoritative root-cause diagnosis and concrete remediation plan."
        )

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            raw_json = response.choices[0].message.content
            data = json.loads(raw_json)

            if "root_cause_summary" in data:
                report.root_cause_summary = data["root_cause_summary"]
            if "detailed_findings" in data and isinstance(data["detailed_findings"], list):
                report.detailed_findings.extend(data["detailed_findings"])

            if "suggested_remediations" in data and isinstance(data["suggested_remediations"], list):
                for rem in data["suggested_remediations"]:
                    report.remediation_plan.append(
                        RemediationStep(
                            action_type=rem.get("action_type", "IMMEDIATE"),
                            description=rem.get("description", ""),
                            command=rem.get("command"),
                        )
                    )

            report.ai_analysis = data.get("root_cause_summary")
            report.ai_provider = f"Azure OpenAI ({self.deployment})"

        except Exception as e:
            logger.warning(f"Azure OpenAI diagnosis call failed: {e}")
            report.detailed_findings.append(
                f"Azure OpenAI diagnosis call failed: {e}. Falling back to deterministic rules."
            )

        return report

