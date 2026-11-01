from unittest.mock import MagicMock, patch
from aks_agent.azure_ai import AzureOpenAIInvestigator
from aks_agent.models import InvestigationReport, Severity, FindingEvidence


def test_azure_ai_unavailable_without_endpoint():
    investigator = AzureOpenAIInvestigator(endpoint=None)
    assert investigator.is_available() is False

    report = InvestigationReport(
        incident_id="INC-1",
        log_source="test.log",
        root_cause_category="APPLICATION_PANIC",
        root_cause_summary="Panic",
        severity=Severity.HIGH,
    )
    res = investigator.diagnose_unknown_failure(report)
    assert res == report


@patch("aks_agent.azure_ai.AzureOpenAIInvestigator._get_client")
def test_azure_ai_diagnose_mocked(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"root_cause_summary": "Uncaught NullReferenceException in PaymentWorker.cs line 88", "detailed_findings": ["Object was null due to missing environment variable"], "suggested_remediations": [{"action_type": "IMMEDIATE", "description": "Add DB_SECRET_KEY env var", "command": "kubectl set env deployment/payment DB_SECRET_KEY=secret"}]}'
            )
        )
    ]
    mock_client.chat.completions.create.return_value = mock_response

    investigator = AzureOpenAIInvestigator(
        endpoint="https://test.openai.azure.com/",
        deployment="gpt-4o",
        api_key="mock-key",
    )

    report = InvestigationReport(
        incident_id="INC-AI-TEST",
        log_source="payment.log",
        root_cause_category="APPLICATION_PANIC",
        root_cause_summary="Generic Panic",
        severity=Severity.HIGH,
        key_evidence=[
            FindingEvidence(
                line_numbers=[10],
                log_snippet="System.NullReferenceException: Object reference not set to an instance",
                signal_type="APPLICATION_PANIC",
            )
        ],
    )

    enriched = investigator.diagnose_unknown_failure(report)
    assert "NullReferenceException" in enriched.root_cause_summary
    assert enriched.ai_provider == "Azure OpenAI (gpt-4o)"
    assert len(enriched.remediation_plan) == 1
    assert "kubectl set env" in enriched.remediation_plan[0].command

