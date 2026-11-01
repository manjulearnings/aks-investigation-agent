from aks_agent.parser import AKSLogParser
from aks_agent.engine import InvestigationEngine
from aks_agent.models import Severity


def test_azure_cni_ip_exhaustion_detection():
    parser = AKSLogParser()
    engine = InvestigationEngine()

    raw = (
        "2026-11-01T08:00:00Z stderr F Warning FailedCreatePodSandBox pod/payment-gw-78-98ks "
        "Failed to create pod sandbox: NetworkPlugin cni failed: Failed to allocate IP address from subnet: No more IP addresses available in subnet\n"
        "2026-11-01T08:00:15Z stderr F CrashLoopBackOff: back-off 10s restarting failed container"
    )
    entries = parser.parse_text(raw)
    report = engine.analyze(entries)

    assert report.root_cause_category == "AZURE_CNI_IP_EXHAUSTION"
    assert report.severity == Severity.CRITICAL
    assert "Azure CNI subnet IP address exhaustion" in report.root_cause_summary
    assert any("az network vnet subnet" in step.command for step in report.remediation_plan if step.command)


def test_azure_keyvault_csi_failure_detection():
    parser = AKSLogParser()
    engine = InvestigationEngine()

    raw = (
        "2026-11-01T11:00:00Z stderr F Warning FailedMount pod/auth-service-59bc-x89lp "
        "MountVolume.SetUp failed for volume secrets-store-inline : keyvault.go: failed to get secret from https://myvault.vault.azure.net: 401 Unauthorized"
    )
    entries = parser.parse_text(raw)
    report = engine.analyze(entries)

    assert report.root_cause_category == "AZURE_KEYVAULT_CSI_FAILURE"
    assert report.severity == Severity.CRITICAL
    assert any("Key Vault Secrets User" in step.command for step in report.remediation_plan if step.command)


def test_azure_disk_multi_attach_detection():
    parser = AKSLogParser()
    engine = InvestigationEngine()

    raw = (
        "2026-11-01T09:00:00Z stderr F Warning FailedAttachVolume pod/db-replica-0 "
        "AttachVolume.Attach failed for volume pvc-1234 : Multi-Attach error for volume pvc-1234 Volume is already exclusively attached to one node"
    )
    entries = parser.parse_text(raw)
    report = engine.analyze(entries)

    assert report.root_cause_category == "AZURE_DISK_MULTI_ATTACH"
    assert report.severity == Severity.HIGH
    assert any("kubectl get volumeattachment" in step.command for step in report.remediation_plan if step.command)


def test_acr_unauthorized_image_pull_detection():
    parser = AKSLogParser()
    engine = InvestigationEngine()

    raw = (
        "2026-11-01T12:00:00Z stderr F Warning Failed pod/worker-7c49-29mks "
        "Failed to pull image myacr.azurecr.io/worker:v1: failed to fetch oauth token: 401 Unauthorized\n"
        "2026-11-01T12:00:01Z stderr F Error: ImagePullBackOff"
    )
    entries = parser.parse_text(raw)
    report = engine.analyze(entries)

    assert report.root_cause_category == "ACR_UNAUTHORIZED_IMAGE_PULL"
    assert report.severity == Severity.HIGH
    assert any("az aks update" in step.command for step in report.remediation_plan if step.command)


def test_azure_spot_eviction_detection():
    parser = AKSLogParser()
    engine = InvestigationEngine()

    raw = (
        "2026-11-01T14:00:00Z stderr F Warning NodeTerminationScheduled pod/batch-job-98ks "
        "Preempted by Azure Spot pricing engine, node deallocation scheduled"
    )
    entries = parser.parse_text(raw)
    report = engine.analyze(entries)

    assert report.root_cause_category == "AZURE_SPOT_EVICTION"
    assert report.severity == Severity.HIGH

