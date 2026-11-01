import re
import uuid
from typing import List, Optional, Tuple, Dict
from .models import (
    StructuredLogEntry,
    InvestigationReport,
    FindingEvidence,
    EvidenceConfidence,
    FailureTimeline,
    TimelineEvent,
    TimelinePhase,
    RemediationStep,
    Severity,
    AzureClusterMetadata,
)


class InvestigationEngine:
    """Deterministic Causal Analysis Engine specialized for AKS & Azure Cloud Failures."""

    def analyze(
        self,
        entries: List[StructuredLogEntry],
        source_name: Optional[str] = None,
        azure_metadata: Optional[AzureClusterMetadata] = None,
    ) -> InvestigationReport:
        incident_id = f"AKS-INC-{uuid.uuid4().hex[:8].upper()}"
        source = source_name or "stream"

        if not entries:
            return InvestigationReport(
                incident_id=incident_id,
                log_source=source,
                azure_metadata=azure_metadata,
                root_cause_category="NO_DATA",
                root_cause_summary="Provided log input contains no parseable log entries.",
                severity=Severity.INFO,
            )

        # 1. Detect Signals across all entries
        signals = self._detect_signals(entries)

        # 2. Extract Cluster & Resource Metadata
        cluster_meta = azure_metadata or self._infer_azure_metadata(entries)
        resource_names = self._infer_resource_names(entries)

        # 3. Apply Causal Hierarchy (Root Cause vs Cascading Symptoms)
        root_cause, severity, summary, detailed_findings = self._deduce_root_cause(signals, resource_names)

        # 4. Catalog Empirical Evidence
        evidence_list = self._gather_evidence(signals)

        # 5. Build Chronological Incident Timeline
        timeline = self._build_timeline(entries, signals)

        # 6. Generate Actionable Remediation Plan
        remediation_plan = self._generate_remediations(root_cause, resource_names, cluster_meta)

        return InvestigationReport(
            incident_id=incident_id,
            log_source=source,
            azure_metadata=cluster_meta,
            root_cause_category=root_cause,
            root_cause_summary=summary,
            severity=severity,
            key_evidence=evidence_list,
            timeline=timeline,
            remediation_plan=remediation_plan,
            detailed_findings=detailed_findings,
        )

    def _detect_signals(self, entries: List[StructuredLogEntry]) -> Dict[str, List[StructuredLogEntry]]:
        signals: Dict[str, List[StructuredLogEntry]] = {
            "AZURE_CNI_IP_EXHAUSTION": [],
            "AZURE_DISK_MULTI_ATTACH": [],
            "AZURE_KEYVAULT_CSI_FAILURE": [],
            "ACR_UNAUTHORIZED_IMAGE_PULL": [],
            "AZURE_SPOT_EVICTION": [],
            "AZURE_POLICY_DENIAL": [],
            "OOM_KILLED": [],
            "DB_CONNECTION_FAILURE": [],
            "DNS_RESOLUTION_FAILURE": [],
            "APPLICATION_PANIC": [],
            "APPLICATION_ERROR": [],
            "PROBE_FAILURE": [],
            "CRASHLOOP_BACKOFF": [],
        }

        for entry in entries:
            msg = entry.message
            msg_lower = msg.lower()

            # Azure CNI IP Exhaustion
            if (
                "failed to allocate ip address from subnet" in msg_lower
                or "no more ip addresses available in subnet" in msg_lower
                or ("failedcreatepodsandbox" in msg_lower and "allocate ip" in msg_lower)
                or ("failedcreatepodsandbox" in msg_lower and "ipam" in msg_lower)
            ):
                signals["AZURE_CNI_IP_EXHAUSTION"].append(entry)

            # Azure Disk Multi-Attach
            elif (
                "multi-attach error for volume" in msg_lower
                or ("attachvolume.attach failed" in msg_lower and "already exclusively attached" in msg_lower)
                or "volumeattachment" in msg_lower and "timed out waiting" in msg_lower
            ):
                signals["AZURE_DISK_MULTI_ATTACH"].append(entry)

            # Azure Key Vault CSI Driver Failure
            elif (
                ("keyvault.go" in msg_lower and "failed to get secret" in msg_lower)
                or ("secrets-store.csi" in msg_lower and ("401" in msg or "403" in msg or "unauthorized" in msg_lower))
                or "failed to get key vault token" in msg_lower
            ):
                signals["AZURE_KEYVAULT_CSI_FAILURE"].append(entry)

            # ACR Unauthorized / AcrPull role missing
            elif (
                "azurecr.io" in msg_lower
                and ("401 unauthorized" in msg_lower or "failed to pull and unpack image" in msg_lower or "imagepullbackoff" in msg_lower)
            ):
                signals["ACR_UNAUTHORIZED_IMAGE_PULL"].append(entry)

            # Azure Spot Eviction
            elif (
                "nodeterminationscheduled" in msg_lower
                or ("spot" in msg_lower and "evicted" in msg_lower)
                or "preempted by azure spot" in msg_lower
            ):
                signals["AZURE_SPOT_EVICTION"].append(entry)

            # Azure Policy / Gatekeeper Denials
            elif (
                "validation.gatekeeper.sh" in msg_lower
                or "azurepolicy" in msg_lower
            ):
                signals["AZURE_POLICY_DENIAL"].append(entry)

            # Out of Memory
            elif (
                "oomkilled" in msg_lower
                or "exit code 137" in msg_lower
                or "out of memory: kill process" in msg_lower
                or "memory cgroup out of memory" in msg_lower
                or "java.lang.outofmemoryerror" in msg_lower
            ):
                signals["OOM_KILLED"].append(entry)

            # Database Connection Failure
            elif (
                "connection refused" in msg_lower
                or "could not connect to server" in msg_lower
                or "dial tcp" in msg_lower and ("connection refused" in msg_lower or "i/o timeout" in msg_lower)
                or "sqlconnection" in msg_lower and "timeout" in msg_lower
            ):
                signals["DB_CONNECTION_FAILURE"].append(entry)

            # DNS Resolution Failure
            elif (
                "no such host" in msg_lower
                or "temporary failure in name resolution" in msg_lower
                or "name or service not known" in msg_lower
                or "cannot resolve host" in msg_lower
            ):
                signals["DNS_RESOLUTION_FAILURE"].append(entry)

            # Application Panic / Stack Trace
            elif entry.is_stack_trace or "panic:" in msg_lower or "fatal error:" in msg_lower:
                signals["APPLICATION_PANIC"].append(entry)

            # Application Error
            elif entry.log_level in ("ERROR", "FATAL") and not signals["CRASHLOOP_BACKOFF"]:
                signals["APPLICATION_ERROR"].append(entry)

            # Probe Failures
            if "liveness probe failed" in msg_lower or "readiness probe failed" in msg_lower:
                signals["PROBE_FAILURE"].append(entry)

            # CrashLoopBackOff
            if "crashloopbackoff" in msg_lower or "back-off restarting failed container" in msg_lower:
                signals["CRASHLOOP_BACKOFF"].append(entry)

        return signals

    def _deduce_root_cause(
        self, signals: Dict[str, List[StructuredLogEntry]], resources: Dict[str, str]
    ) -> Tuple[str, Severity, str, List[str]]:
        pod = resources.get("pod", "the affected pod")
        findings = []

        # Causal Priority 1: Azure CNI Subnet Exhaustion
        if signals["AZURE_CNI_IP_EXHAUSTION"]:
            findings.append("Azure CNI IPAM driver reported zero available IP addresses in the target VNet subnet.")
            findings.append(f"Kubelet failed to initialize the pod sandbox network interface for {pod}.")
            if signals["CRASHLOOP_BACKOFF"] or signals["PROBE_FAILURE"]:
                findings.append("Secondary: Pod entered restart loop as a consequence of repeated sandbox initialization aborts.")
            return (
                "AZURE_CNI_IP_EXHAUSTION",
                Severity.CRITICAL,
                f"Azure CNI subnet IP address exhaustion prevented pod network sandbox creation for {pod}.",
                findings,
            )

        # Causal Priority 2: Azure Key Vault CSI Auth / Secret Retrieval Failure
        if signals["AZURE_KEYVAULT_CSI_FAILURE"]:
            findings.append("The Secrets Store CSI Driver failed communicating with Azure Key Vault.")
            findings.append("Observed 401 Unauthorized or 403 Forbidden attempting token/secret retrieval.")
            findings.append("Pod volume mount blocked, preventing container startup.")
            return (
                "AZURE_KEYVAULT_CSI_FAILURE",
                Severity.CRITICAL,
                f"Azure Key Vault CSI Driver authentication failure prevented secret volume mount for {pod}.",
                findings,
            )

        # Causal Priority 3: Azure Disk Multi-Attach Lock
        if signals["AZURE_DISK_MULTI_ATTACH"]:
            findings.append("Azure Managed Disk VolumeAttachment failed due to exclusive lock on an existing node.")
            findings.append("Kubernetes AttachVolume controller timed out waiting for prior node detachment.")
            return (
                "AZURE_DISK_MULTI_ATTACH",
                Severity.HIGH,
                f"Azure Managed Disk ReadWriteOnce multi-attach conflict blocked storage attachment for {pod}.",
                findings,
            )

        # Causal Priority 4: ACR Unauthorized Image Pull
        if signals["ACR_UNAUTHORIZED_IMAGE_PULL"]:
            findings.append("Container runtime received 401 Unauthorized pulling container image from Azure Container Registry.")
            findings.append("AKS Kubelet Managed Identity lacks AcrPull role assignment or credentials expired.")
            return (
                "ACR_UNAUTHORIZED_IMAGE_PULL",
                Severity.HIGH,
                f"ACR authentication failure: Kubelet identity lacks AcrPull role to download image for {pod}.",
                findings,
            )

        # Causal Priority 5: Azure Spot VM Eviction
        if signals["AZURE_SPOT_EVICTION"]:
            findings.append("Underlying node was scheduled for preemption/eviction by the Azure Spot pricing engine.")
            findings.append(f"Workload {pod} was terminated during node deallocation.")
            return (
                "AZURE_SPOT_EVICTION",
                Severity.HIGH,
                f"Azure Spot node eviction forced graceful/ungraceful termination of {pod}.",
                findings,
            )

        # Causal Priority 6: Azure Policy / Gatekeeper Denials
        if signals["AZURE_POLICY_DENIAL"]:
            findings.append("Azure Policy Gatekeeper admission webhook rejected the pod deployment.")
            findings.append("Resource violated active Azure governance constraint templates.")
            return (
                "AZURE_POLICY_DENIAL",
                Severity.MEDIUM,
                f"Azure Policy (Gatekeeper) admission webhook blocked pod creation for {pod}.",
                findings,
            )

        # Causal Priority 7: Out Of Memory
        if signals["OOM_KILLED"]:
            findings.append(f"Container exceeded allocated cgroup memory limit on AKS node and was terminated by the Linux OOM Killer (exit code 137).")
            if signals["CRASHLOOP_BACKOFF"]:
                findings.append("Secondary: Repeated OOM terminations triggered Kubelet CrashLoopBackOff exponential delay.")
            return (
                "OOM_KILLED",
                Severity.CRITICAL,
                f"Pod {pod} was terminated with exit code 137 (OOMKilled) after exceeding memory limit.",
                findings,
            )

        # Causal Priority 8: Database / DNS Failures
        if signals["DB_CONNECTION_FAILURE"]:
            findings.append("Application failed to establish TCP connection with the target database endpoint.")
            return (
                "DATABASE_OUTAGE",
                Severity.CRITICAL,
                f"Application in {pod} experienced fatal database connection refusal/timeout.",
                findings,
            )

        if signals["DNS_RESOLUTION_FAILURE"]:
            findings.append("CoreDNS or Azure DNS returned NXDOMAIN / temporary resolution failure for service name.")
            return (
                "DNS_RESOLUTION_FAILURE",
                Severity.HIGH,
                f"Service name resolution failed in CoreDNS / Azure DNS for {pod}.",
                findings,
            )

        # Causal Priority 9: Unhandled Application Panic / Exceptions
        if signals["APPLICATION_PANIC"]:
            findings.append("Application crashed due to an unhandled runtime exception or language panic.")
            return (
                "APPLICATION_PANIC",
                Severity.HIGH,
                f"Application panic/fatal exception crashed container in {pod}.",
                findings,
            )

        if signals["APPLICATION_ERROR"]:
            findings.append("Application emitted continuous ERROR-level exceptions in runtime logs.")
            return (
                "APPLICATION_ERROR",
                Severity.HIGH,
                f"Application errors caused degradation in {pod}.",
                findings,
            )

        # Secondary Cascading Fallback
        if signals["PROBE_FAILURE"]:
            findings.append("Kubelet liveness/readiness health probes failed consecutively.")
            return (
                "HEALTH_PROBE_TIMEOUT",
                Severity.MEDIUM,
                f"Kubelet killed {pod} because liveness/readiness probe timed out.",
                findings,
            )

        if signals["CRASHLOOP_BACKOFF"]:
            findings.append("Container repeatedly exited with a non-zero exit status.")
            return (
                "CRASHLOOP_BACKOFF",
                Severity.HIGH,
                f"Pod {pod} is stuck in CrashLoopBackOff.",
                findings,
            )

        return (
            "UNKNOWN_OR_HEALTHY",
            Severity.LOW,
            "No active Kubernetes failure signatures detected in provided logs.",
            ["Logs appear operational or contain no recognized incident signals."],
        )

    def _gather_evidence(self, signals: Dict[str, List[StructuredLogEntry]]) -> List[FindingEvidence]:
        evidence_list: List[FindingEvidence] = []
        for signal_name, entries in signals.items():
            if not entries:
                continue
            # Pick representative entries (up to 2 per signal)
            for entry in entries[:2]:
                snippet = entry.message if len(entry.message) <= 300 else entry.message[:297] + "..."
                evidence_list.append(
                    FindingEvidence(
                        line_numbers=[entry.line_number],
                        timestamp=entry.timestamp_str,
                        log_snippet=snippet,
                        signal_type=signal_name,
                        confidence=EvidenceConfidence.HIGH,
                    )
                )
        return evidence_list

    def _build_timeline(
        self, entries: List[StructuredLogEntry], signals: Dict[str, List[StructuredLogEntry]]
    ) -> FailureTimeline:
        events: List[TimelineEvent] = []

        # Find Inception Trigger
        root_signals = [
            "AZURE_CNI_IP_EXHAUSTION",
            "AZURE_KEYVAULT_CSI_FAILURE",
            "AZURE_DISK_MULTI_ATTACH",
            "ACR_UNAUTHORIZED_IMAGE_PULL",
            "AZURE_SPOT_EVICTION",
            "AZURE_POLICY_DENIAL",
            "OOM_KILLED",
            "DB_CONNECTION_FAILURE",
            "APPLICATION_PANIC",
        ]

        inception_entry = None
        inception_signal = None
        for sig in root_signals:
            if signals[sig]:
                inception_entry = signals[sig][0]
                inception_signal = sig
                break

        if inception_entry:
            events.append(
                TimelineEvent(
                    timestamp=inception_entry.timestamp_str,
                    phase=TimelinePhase.INCEPTION,
                    description=f"Primary incident trigger initiated: {inception_signal.replace('_', ' ').title()}",
                    log_snippet=inception_entry.message[:180],
                )
            )

        # Propagation Events
        if signals["APPLICATION_ERROR"] and inception_signal != "APPLICATION_ERROR":
            err = signals["APPLICATION_ERROR"][0]
            events.append(
                TimelineEvent(
                    timestamp=err.timestamp_str,
                    phase=TimelinePhase.PROPAGATION,
                    description="Application cascading degradation and error logging began",
                    log_snippet=err.message[:180],
                )
            )

        # Kubelet Actions / Azure Interventions
        if signals["PROBE_FAILURE"]:
            pb = signals["PROBE_FAILURE"][0]
            events.append(
                TimelineEvent(
                    timestamp=pb.timestamp_str,
                    phase=TimelinePhase.KUBELET_ACTION,
                    description="Kubelet health probe threshold exceeded",
                    log_snippet=pb.message[:180],
                )
            )

        if signals["CRASHLOOP_BACKOFF"]:
            cl = signals["CRASHLOOP_BACKOFF"][-1]
            events.append(
                TimelineEvent(
                    timestamp=cl.timestamp_str,
                    phase=TimelinePhase.KUBELET_ACTION,
                    description="Kubelet enforced CrashLoopBackOff restart cooldown",
                    log_snippet=cl.message[:180],
                )
            )

        if signals["AZURE_SPOT_EVICTION"]:
            sp = signals["AZURE_SPOT_EVICTION"][0]
            events.append(
                TimelineEvent(
                    timestamp=sp.timestamp_str,
                    phase=TimelinePhase.AZURE_INTERVENTION,
                    description="Azure Resource Manager initiated node deallocation",
                    log_snippet=sp.message[:180],
                )
            )

        return FailureTimeline(events=events)

    def _generate_remediations(
        self,
        root_cause: str,
        resources: Dict[str, str],
        meta: Optional[AzureClusterMetadata],
    ) -> List[RemediationStep]:
        pod = resources.get("pod", "<pod-name>")
        deployment = resources.get("deployment", "<deployment-name>")
        rg = (meta and meta.resource_group) or "<my-resource-group>"
        cluster = (meta and meta.cluster_name) or "<my-aks-cluster>"

        plan: List[RemediationStep] = []

        if root_cause == "AZURE_CNI_IP_EXHAUSTION":
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description="Inspect available IP addresses in your AKS node pool subnet via Azure CLI.",
                    command=f"az network vnet subnet show --resource-group {rg} --vnet-name <my-vnet> --name <aks-subnet> --query '{{AddressPrefix:addressPrefix, AvailableIPs:numberOfAvailableIPs}}'",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="AZURE_CLI",
                    description="Assign an additional secondary IP address prefix to the subnet, or enable Azure CNI Pod Subnet.",
                    command=f"az network vnet subnet update --resource-group {rg} --vnet-name <my-vnet> --name <aks-subnet> --add addressPrefixes '10.241.0.0/16'",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="PREVENTION",
                    description="Migrate new node pools to Azure CNI Overlay mode to eliminate VNet IP address consumption per pod.",
                    doc_url="https://learn.microsoft.com/en-us/azure/aks/azure-cni-overlay",
                )
            )

        elif root_cause == "AZURE_KEYVAULT_CSI_FAILURE":
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description="Check the SecretProviderClass status and events on the namespace.",
                    command=f"kubectl describe secretproviderclass -n <namespace>",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="AZURE_CLI",
                    description="Grant the AKS Workload Identity or Kubelet Identity access to Key Vault secrets.",
                    command=f"az role assignment create --role 'Key Vault Secrets User' --assignee <managed-identity-client-id> --scope /subscriptions/<sub-id>/resourceGroups/{rg}/providers/Microsoft.KeyVault/vaults/<keyvault-name>",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="KUBECTL",
                    description="Ensure your ServiceAccount has the correct Workload Identity client ID annotation.",
                    command=f"kubectl annotate serviceaccount <sa-name> azure.workload.identity/client-id=<client-id> --overwrite",
                )
            )

        elif root_cause == "AZURE_DISK_MULTI_ATTACH":
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description="Check stuck VolumeAttachment resources that have not detached from the previous node.",
                    command="kubectl get volumeattachment | grep -i attached",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="KUBECTL",
                    description="Force deletion of the stuck VolumeAttachment if safe, or restart the target node.",
                    command="kubectl delete volumeattachment <volume-attachment-name> --force --grace-period=0",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="PREVENTION",
                    description="Use Azure Files (NFS/SMB ReadWriteMany) for shared multi-pod storage or ensure zonal anti-affinity.",
                    doc_url="https://learn.microsoft.com/en-us/azure/aks/azure-csi-disk",
                )
            )

        elif root_cause == "ACR_UNAUTHORIZED_IMAGE_PULL":
            plan.append(
                RemediationStep(
                    action_type="AZURE_CLI",
                    description="Attach the Azure Container Registry directly to your AKS cluster to configure AcrPull automatically.",
                    command=f"az aks update --resource-group {rg} --name {cluster} --attach-acr <my-acr-name>",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="KUBECTL",
                    description="Verify image pull status once RBAC has propagated.",
                    command=f"kubectl get pods -l app={deployment}",
                )
            )

        elif root_cause == "AZURE_SPOT_EVICTION":
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description="Check AKS node pool status and Azure Activity Log for Spot eviction events.",
                    command=f"az aks nodepool show --resource-group {rg} --cluster-name {cluster} --name <spot-nodepool>",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="PREVENTION",
                    description="Set node affinity to ensure critical workloads run on Regular (On-Demand) node pools.",
                    doc_url="https://learn.microsoft.com/en-us/azure/aks/spot-node-pool",
                )
            )

        elif root_cause == "OOM_KILLED":
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description="Increase the container memory limit in the deployment manifest.",
                    command=f"kubectl set resources deployment/{deployment} --limits=memory=2Gi --requests=memory=1Gi",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="PREVENTION",
                    description="Analyze memory profiling dumps and monitor ContainerLogV2 / Azure Monitor Metrics.",
                )
            )

        else:
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description=f"Inspect pod status and recent events for {pod}.",
                    command=f"kubectl describe pod {pod}",
                )
            )
            plan.append(
                RemediationStep(
                    action_type="IMMEDIATE",
                    description=f"Stream recent container logs for {pod}.",
                    command=f"kubectl logs {pod} --previous",
                )
            )

        return plan

    def _infer_azure_metadata(self, entries: List[StructuredLogEntry]) -> AzureClusterMetadata:
        meta = AzureClusterMetadata()
        for entry in entries:
            props = entry.azure_properties
            if props.get("SubscriptionId"):
                meta.subscription_id = str(props["SubscriptionId"])
            if props.get("Computer") and not meta.node_pool:
                comp = str(props["Computer"])
                # AKS nodes are named: aks-<nodepool>-<number>-vmss000000
                m = re.match(r"^aks-([a-zA-Z0-9]+)-", comp)
                if m:
                    meta.node_pool = m.group(1)
        return meta

    def _infer_resource_names(self, entries: List[StructuredLogEntry]) -> Dict[str, str]:
        resources = {}
        for entry in entries:
            if entry.pod_name and "pod" not in resources:
                resources["pod"] = entry.pod_name
                # Derive deployment from pod (e.g., checkout-service-7bb8c57657-69vsd -> checkout-service)
                parts = entry.pod_name.split("-")
                if len(parts) >= 3 and len(parts[-1]) >= 4 and len(parts[-2]) >= 4:
                    resources["deployment"] = "-".join(parts[:-2])
                else:
                    resources["deployment"] = entry.pod_name
        return resources

