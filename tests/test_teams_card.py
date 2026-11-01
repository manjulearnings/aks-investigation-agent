from aks_agent.reporters import TeamsAdaptiveCardReporter
from aks_agent.models import InvestigationReport, Severity, RemediationStep


def test_teams_card_generation():
    reporter = TeamsAdaptiveCardReporter()
    report = InvestigationReport(
        incident_id="AKS-INC-TEST1234",
        log_source="payment-gateway.log",
        root_cause_category="AZURE_CNI_IP_EXHAUSTION",
        root_cause_summary="Subnet IP exhaustion blocked pod sandbox initialization.",
        severity=Severity.CRITICAL,
        remediation_plan=[
            RemediationStep(
                action_type="AZURE_CLI",
                description="Update subnet CIDR",
                command="az network vnet subnet update ...",
            )
        ],
    )

    card = reporter.render(report)
    assert card["type"] == "message"
    assert len(card["attachments"]) == 1
    content = card["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard"
    assert "AKS-INC-TEST1234" in str(content["body"])
    assert "Attention" in str(content["body"])  # Critical severity color in Adaptive Card

