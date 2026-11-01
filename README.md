# ☁️ Azure Kubernetes Service (AKS) Investigation Agent

An autonomous incident investigation agent designed specifically for **Azure Kubernetes Service (AKS)**, **Azure Monitor (ContainerLogV2 / KubeEvents)**, and **Azure OpenAI Service**.

The agent ingests AKS container runtime logs, event streams, or direct Azure Log Analytics telemetry, performs deep causal failure analysis across Azure cloud-infrastructure boundaries, catalogs empirical supporting evidence, and generates actionable `az aks` and `kubectl` remediation plans.

---

## 🌟 Key Capabilities

- **Azure-Specific Cloud Failure Mode Diagnostics**:
  - **Azure CNI IP Exhaustion**: Detects VNet subnet address depletion preventing pod sandbox initialization.
  - **Azure Managed Disk Multi-Attach**: Identifies `ReadWriteOnce` storage volume locks across AKS nodes.
  - **Azure Key Vault CSI Provider**: Diagnoses Workload Identity token failures, expired service principals, and 401/403 access denials.
  - **Azure Container Registry (ACR) Authentication**: Diagnoses `ImagePullBackOff` caused by missing `AcrPull` RBAC role assignments on the AKS Kubelet identity.
  - **Azure Spot VM Eviction**: Detects scheduled Spot capacity preemptions and node deallocations.
  - **Azure Policy (Gatekeeper)**: Identifies admission webhook policy enforcement rejections.
  - **Standard Kubernetes Incidents**: OOMKilled (Exit Code 137), CoreDNS timeouts, database connection pool exhaustion, cascading CrashLoopBackOff restarts.
- **Direct Azure Monitor & Log Analytics Ingestion**:
  - Ingests `ContainerLogV2`, `ContainerLog`, and `KubeEvents` natively via KQL and the `azure-monitor-query` SDK.
- **Enterprise Azure OpenAI Integration**:
  - Powered by **Azure OpenAI Service** (GPT-4o / GPT-4o-mini).
  - Authenticates securely via **Azure Entra ID (`DefaultAzureCredential`)** with zero hardcoded API keys, or via Azure OpenAI API keys.
  - Diagnoses unclassified application stack traces (C#, Java, Python, Go, Node.js).
- **Incident Delivery & ChatOps**:
  - **Rich Interactive Terminal** with Azure blue styling and status badges.
  - **Microsoft Teams Adaptive Cards** posted directly to Teams webhooks.
  - **Azure DevOps / GitHub Flavored Markdown** for incident work items.
  - **Machine-readable JSON** for automated alerting pipelines.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Sources ["1. Telemetry & Log Ingestion"]
        A["Azure Monitor / Log Analytics<br/>(ContainerLogV2, KubeEvents)"]
        B["kubectl logs / az aks CLI stdin"]
        C["Local / Stored Incident Logs"]
    end

    subgraph Agent ["2. AKS Investigation Agent"]
        D["AKSLogParser<br/>(ContainerLogV2, CRI-O, JSON, Traces)"]
        E["Deterministic Causal Engine"]
        subgraph Rules ["AKS & Azure Failure Signatures"]
            E1["Azure CNI IP Exhaustion"]
            E2["Azure Disk Multi-Attach Conflict"]
            E3["Key Vault CSI / Workload Identity"]
            E4["ACR Pull 401 / AcrPull RBAC"]
            E5["Azure Spot VM Preemption"]
            E6["OOMKilled & Probe Timeouts"]
        end
        E --- Rules
        F{"Unclassified Trace & Azure OpenAI Configured?"}
        G["Azure OpenAI Service<br/>(GPT-4o via DefaultAzureCredential)"]
    end

    subgraph Outputs ["3. Incident Delivery & Remediation"]
        H["Rich Terminal UI"]
        I["Microsoft Teams Adaptive Cards"]
        J["Azure DevOps Work Items / Markdown"]
        K["JSON Pipeline Export"]
    end

    Sources --> D --> E --> F
    F -- Yes --> G --> H
    F -- No --> H
    H --> I
    H --> J
    H --> K
```

---

## 🚀 Installation

```bash
cd aks-investigation-agent
pip install -e .
```

Or install dependencies directly:
```bash
pip install -r requirements.txt
```

---

## 💻 CLI Usage

The agent installs a CLI command `aks-agent` (or `python -m aks_agent.cli`):

### 1. Analyze a Local Log File
```bash
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log
```

### 2. Stream Live Logs from `az aks` or `kubectl`
```bash
az aks command invoke \
  --resource-group myRG \
  --name myAKSCluster \
  --command "kubectl logs pod/payment-gateway-6f987dbf54-zk92w --previous" | aks-agent -
```

### 3. Query Azure Monitor / Log Analytics Directly via KQL
```bash
aks-agent --query-monitor \
  --workspace-id "11223344-5566-7788-99aa-bbccddeeff00" \
  --pod "payment-gateway" \
  --hours 2
```

### 4. Post Incident Card Directly to Microsoft Teams
```bash
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log \
  --teams-webhook "https://outlook.office.com/webhook/your-teams-webhook-url"
```

### 5. Generate Markdown for Azure DevOps Work Items
```bash
aks-agent crash.log --format markdown --output azdo-incident.md
```

---

## 🔐 Azure Authentication Setup

### Authenticating with Azure OpenAI
The agent supports **zero-secret authentication** via Azure Entra ID / Managed Identity:

```bash
# 1. Log in with Azure CLI (or run inside an AKS pod with Workload Identity)
az login

# 2. Configure endpoint
export AZURE_OPENAI_ENDPOINT="https://my-openai-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Optional: API Key if not using Entra ID
export AZURE_OPENAI_KEY="your-azure-openai-key"
```

### Authenticating with Azure Monitor
Ensure your account or Managed Identity has the **Log Analytics Reader** role on the target workspace:

```bash
export AZURE_LOG_ANALYTICS_WORKSPACE_ID="11223344-5566-7788-99aa-bbccddeeff00"
```

---

## 🧪 Running the Test Suite

```bash
pytest
```

---

## ⚖️ License
Apache-2.0

