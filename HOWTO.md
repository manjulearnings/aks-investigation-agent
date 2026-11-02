# 📖 How-To Guide & Usage Recipes

Welcome to the **AKS Investigation Agent** practical guide! This document provides real-world recipes, copy-paste commands, and workflows for Site Reliability Engineers (SREs), DevOps practitioners, and platform engineers.

---

## 📑 Table of Contents
1. [⚡ Quick Start Checklist](#-quick-start-checklist)
2. [🖥️ What Does the Output Look Like?](#️-what-does-the-output-look-like)
3. [Recipe 1: Offline / Local Log Analysis (Air-Gapped)](#recipe-1-offline--local-log-analysis-air-gapped) ("I want to test the tool right now with sample logs")
4. [Recipe 2: Live On-Call SRE Debugging (kubectl & az aks piping)](#recipe-2-live-on-call-sre-debugging-kubectl--az-aks-piping) ("A pod is crashing or stuck in my cluster right now")
5. [Recipe 3: Direct Azure Log Analytics Querying (KQL)](#recipe-3-direct-azure-log-analytics-querying-kql) ("The pod crashed hours ago and is already deleted")
6. [Recipe 4: ChatOps & Incident Delivery (Teams & Azure DevOps)](#recipe-4-chatops--incident-delivery-teams--azure-devops) ("I want to send incident alerts to Microsoft Teams / DevOps")
7. [Recipe 5: AI-Powered Deep Diagnosis with Azure OpenAI](#recipe-5-ai-powered-deep-diagnosis-with-azure-openai) ("My app crashed with a mysterious Java/Python/.NET exception")
8. [Recipe 6: Python SDK & CI/CD Integration](#recipe-6-python-sdk--cicd-integration) ("I want to automate checks in my CI/CD pipeline or Python code")
9. [🎛️ CLI Options & Flags Reference](#️-cli-options--flags-reference)
10. [❓ Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)

---

## 🎯 At a Glance: Which Recipe Do I Need?

| Recipe (Earlier Version) | Scenario & Goal (User-Friendly Version) | Azure Credentials Required? |
| :--- | :--- | :--- |
| **Recipe 1: Offline / Local Log Analysis (Air-Gapped)** | *"I want to test the tool right now with sample logs"* | ❌ **No** (100% offline & air-gapped) |
| **Recipe 2: Live On-Call SRE Debugging (kubectl & az aks piping)** | *"A pod is crashing or stuck in my cluster right now"* | ❌ **No** (standard `kubectl` / `az login`) |
| **Recipe 3: Direct Azure Log Analytics Querying (KQL)** | *"The pod crashed hours ago and is already deleted"* | ✅ **Yes** (`Log Analytics Reader`) |
| **Recipe 4: ChatOps & Incident Delivery (Teams & Azure DevOps)** | *"I want to send incident alerts to Microsoft Teams / DevOps"* | ❌ **No** (just a Teams webhook URL) |
| **Recipe 5: AI-Powered Deep Diagnosis with Azure OpenAI** | *"My app crashed with a mysterious Java/Python/.NET exception"* | ✅ **Yes** (`AZURE_OPENAI_ENDPOINT`) |
| **Recipe 6: Python SDK & CI/CD Integration** | *"I want to automate checks in my CI/CD pipeline or Python code"* | ❌ **No** (standard Python) |

---

## ⚡ Quick Start Checklist

### Step 1: Clone & Set Up Virtual Environment

> [!TIP]
> A virtual environment (`venv`) keeps the agent's dependencies isolated so they won't interfere with your system Python.

#### On Windows (PowerShell)
```powershell
# 1. Clone your repository
git clone https://github.com/manjulearnings/aks-investigation-agent.git
cd aks-investigation-agent

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install the agent in editable mode
pip install -e .
```

#### On Linux / macOS (Bash / Zsh)
```bash
# 1. Clone your repository
git clone https://github.com/manjulearnings/aks-investigation-agent.git
cd aks-investigation-agent

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install the agent in editable mode
pip install -e .
```

### Step 2: Verify Installation
Verify that the `aks-agent` CLI is installed and available:
```bash
aks-agent --help
```

### Step 3: Instant Smoke Test (Zero Azure Setup Needed)
Run the agent against one of the included real-world incident logs:
```bash
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log
```

---

## 🖥️ What Does the Output Look Like?

When the agent runs, it renders a formatted, color-coded incident dashboard directly in your terminal:

```
╭──────────────────────── ☁️ AKS Incident Report • INC-20261101 • CRITICAL ────────────────────────╮
│ Source:              sample_logs/01_azure_cni_ip_exhaustion.log                                    │
│ Root Cause Category: AZURE_CNI_IP_EXHAUSTION                                                      │
│ Confidence Score:    100%                                                                         │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────────── 🎯 Root Cause Deduction ─────────────────────────────────────────╮
│ Azure CNI failed to allocate an IP address from the VNet subnet for the pod sandbox.              │
│ Subnet address space is exhausted, preventing new pods from reaching the Running state.           │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯

⏱️ Chronological Incident Progression:
┌─────────────────────┬───────────────────┬────────────────────────────────────────────────────────┐
│ Timestamp           │ Phase             │ Incident Event                                         │
├─────────────────────┼───────────────────┼────────────────────────────────────────────────────────┤
│ 2026-11-01 10:14:02 │ Inception         │ Pod scheduled to node aks-agentpool-31298471-vmss000000│
│ 2026-11-01 10:14:05 │ Propagation       │ CNI network plugin failed: allocateIPAddress failed    │
│ 2026-11-01 10:14:15 │ Kubelet Action    │ Container runtime sandbox creation failed: no IP left  │
└─────────────────────┴───────────────────┴────────────────────────────────────────────────────────┘

🔍 Empirical Supporting Evidence:
 • Log Line 14: "Failed to allocate IP address from subnet /subscriptions/.../subnets/aks-subnet"
 • Log Line 18: "CreatePodSandbox failed: NetworkPlugin cni failed to set up pod network"

🛠️ Actionable Remediation Plan:
 1. [CLI] Expand AKS Subnet CIDR:
    az network vnet subnet update --resource-group rg-aks --vnet-name vnet-aks --name aks-subnet --address-prefixes 10.240.0.0/20
 2. [K8s] Drain stale pending pods:
    kubectl get pods -A --field-selector status.phase=Pending
```

---

## Recipe 1: Offline / Local Log Analysis (Air-Gapped)

> **When to use:** You have exported logs, post-mortem files, or work in an isolated/air-gapped network. **No internet, no Azure login, and no secrets required.**

### Analyze a single file:
```bash
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log
```

### Try all bundled failure scenarios:
```bash
# Scenario 1: Azure CNI Subnet IP exhaustion
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log

# Scenario 2: Azure Managed Disk Multi-Attach lock between nodes
aks-agent sample_logs/02_azure_disk_multi_attach.log

# Scenario 3: Azure Key Vault CSI Workload Identity token failure
aks-agent sample_logs/03_azure_keyvault_csi_failure.log

# Scenario 4: ACR ImagePullBackOff (missing AcrPull RBAC role)
aks-agent sample_logs/04_acr_unauthorized_imagepull.log

# Scenario 5: OOMKilled (Exit Code 137) memory leak crash
aks-agent sample_logs/05_aks_oom_crashloop.log
```

---

## Recipe 2: Live On-Call SRE Debugging (kubectl & az aks piping)

> **When to use:** You are on-call and alerted to a crashing, restarting, or pending pod in a live Kubernetes cluster. Instead of reading hundreds of lines of raw logs manually, stream them directly into the agent.

> [!NOTE]
> The `-` argument at the end of the command tells `aks-agent` to read directly from standard input (`stdin`).

### A. Pipe directly from `kubectl`
```bash
# Option 1: Investigate the PREVIOUS crashed container instance
kubectl logs pod/checkout-service-7bb8c57657-69vsd -n prod --previous | aks-agent -

# Option 2: Investigate recent logs from a specific container
kubectl logs pod/payment-api-54fc794b65-qkwg2 -c app-container -n prod --tail=300 | aks-agent -
```

### B. Pipe through Azure CLI (Zero Kubeconfig Required)
If you don't have direct cluster network access (e.g. private AKS cluster):
```bash
az aks command invoke \
  --resource-group rg-production \
  --name aks-prod-cluster \
  --command "kubectl logs pod/order-service-7f89b-9xkld -n prod --previous" | aks-agent -
```

---

## Recipe 3: Direct Azure Log Analytics Querying (KQL)

> **When to use:** The crashed pod was already deleted or restarted hours ago, so `kubectl logs` is no longer available. Logs are safely stored in Azure Log Analytics (`ContainerLogV2`).

### 1. Prerequisites
Log in with Azure CLI:
```bash
az login
```
*(Ensure your user account or Managed Identity has the **Log Analytics Reader** role on your Azure Log Analytics workspace).*

### 2. Query Azure Monitor directly
```bash
aks-agent --query-monitor \
  --workspace-id "11223344-5566-7788-99aa-bbccddeeff00" \
  --pod "payment-gateway" \
  --namespace "prod" \
  --hours 2
```

> [!TIP]
> You can set your Workspace ID once in your environment to avoid typing it each time:
> - **PowerShell:** `$env:AZURE_LOG_ANALYTICS_WORKSPACE_ID="11223344-5566-7788-99aa-bbccddeeff00"`
> - **Bash:** `export AZURE_LOG_ANALYTICS_WORKSPACE_ID="11223344-5566-7788-99aa-bbccddeeff00"`
>
> Then simply run:
> ```bash
> aks-agent --query-monitor --pod "payment-gateway"
> ```

---

## Recipe 4: ChatOps & Incident Delivery (Teams & Azure DevOps)

> **When to use:** You want to share findings with your engineering team, post an incident summary to a Slack/Teams alert channel, or attach a ticket to Azure DevOps / Jira.

### 1. Send an interactive card to Microsoft Teams
Post directly to an SRE alert channel using an Incoming Webhook:
```bash
aks-agent crash.log --teams-webhook "https://outlook.office.com/webhook/xxx"
```
*The Teams message arrives as a formatted Adaptive Card with color-coded severity badges, root cause deduction, and remediation command buttons.*

### 2. Generate Markdown for Azure DevOps / Jira / GitHub Issues
```bash
aks-agent crash.log --format markdown --output incident-report.md
```
*Outputs a GitHub/Azure DevOps Flavored Markdown document ready to paste into an incident ticket.*

### 3. Generate JSON for Automated Alerting Pipelines
```bash
aks-agent crash.log --format json --output incident.json
```
*Outputs structured, machine-readable JSON for ingestion into Datadog, Splunk, PagerDuty, or ServiceNow.*

---

## Recipe 5: AI-Powered Deep Diagnosis with Azure OpenAI

> **When to use:** The issue isn't an AKS infrastructure failure (like CNI IP exhaustion), but an unclassified application bug or custom language stack trace (C#, Java, Python, Go, Node.js).

### 1. Configure Azure OpenAI Endpoint
The agent supports **zero-secret authentication** via Azure Entra ID (`DefaultAzureCredential`):
```bash
# 1. Log in with Azure CLI
az login

# 2. Set endpoint and deployment name
export AZURE_OPENAI_ENDPOINT="https://<your-openai-resource>.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
```
*(On Windows PowerShell, use `$env:AZURE_OPENAI_ENDPOINT = "https://..."`)*

Or pass an API Key if your organization does not use Entra ID:
```bash
export AZURE_OPENAI_KEY="your-api-key"
```

### 2. Run with AI Diagnosis
```bash
# Automatically calls GPT-4o if an unclassified application exception is detected:
aks-agent app-crash.log

# Or force AI analysis regardless of error type:
aks-agent app-crash.log --force-ai
```

---

## Recipe 6: Python SDK & CI/CD Integration

> **When to use:** You want to embed AKS incident triage inside your own Python microservices, automated testing harnesses, or CI/CD deployment pipelines.

### Using as a Python Library:
```python
from aks_agent import AKSInvestigationAgent
from aks_agent.models import AzureClusterMetadata

# 1. Initialize the agent
agent = AKSInvestigationAgent()

# 2. (Optional) Provide cluster context
metadata = AzureClusterMetadata(
    cluster_name="aks-prod-weu",
    resource_group="rg-production",
    subscription_id="00000000-0000-0000-0000-000000000000"
)

# 3. Perform investigation
report = agent.investigate_file(
    filepath="sample_logs/01_azure_cni_ip_exhaustion.log",
    azure_metadata=metadata
)

# 4. Access clean, structured properties
print(f"Title:       {report.incident_title}")
print(f"Severity:    {report.severity.value}")
print(f"Root Cause:  {report.root_cause_summary}")
print(f"Confidence:  {report.confidence_score * 100:.0f}%")

print("\nRemediation Actions:")
for step in report.remediation_actions:
    print(f" - [{step.action_type.value}] {step.title}: {step.command or step.description}")
```

### In GitHub Actions / Azure Pipelines (Deployment Gate):
```bash
# Pipe container logs from post-deployment validation into the agent
kubectl logs deployment/order-processor -n staging --tail=200 | aks-agent - --format json --output report.json

# Fail build if CRITICAL or HIGH severity failure detected
python -c "import json; r=json.load(open('report.json')); exit(1 if r['severity'] in ['CRITICAL', 'HIGH'] else 0)"
```

---

## 🎛️ CLI Options & Flags Cheat Sheet

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Log Source** | `[log_source]` | Path to log file, or `-` for stdin pipe | `None` |
| **Output Format** | `-f, --format` | `terminal`, `markdown`, `json`, `teams` | `terminal` |
| **Output File** | `-o, --output` | File path to write the formatted report | `stdout` |
| **Teams Webhook**| `--teams-webhook` | Incoming Webhook URL for Microsoft Teams | `None` |
| **Query Monitor** | `--query-monitor`| Query live Azure Log Analytics workspace | `False` |
| **Workspace ID** | `--workspace-id` | Azure Log Analytics Workspace GUID | Env Var |
| **Pod Name** | `--pod` | Target pod name for Log Analytics query | `None` |
| **Namespace** | `--namespace` | Target namespace for Log Analytics query| `None` |
| **Query Hours** | `--hours` | Lookback window in hours for Log Analytics | `2` |
| **Force AI** | `--force-ai` | Force Azure OpenAI analysis for all errors | `False` |
| **OpenAI Endpoint**| `--azure-openai-endpoint` | Azure OpenAI resource endpoint | Env Var |
| **OpenAI Deployment**| `--azure-openai-deployment` | Azure OpenAI deployment model name | `gpt-4o` |

---

## ❓ Frequently Asked Questions (FAQ)

### Q: Do I need an Azure account or credentials to use this?
**No.** Local log file analysis, sample logs, and `stdin` pipes work completely air-gapped without any Azure subscription, credentials, or network connection.

### Q: Does this send my confidential logs to external third parties?
**No.** All causal rule engine parsing and analysis runs 100% locally on your machine. External network calls only happen if you explicitly configure:
1. Azure Log Analytics querying (`--query-monitor`).
2. Microsoft Teams Webhook delivery (`--teams-webhook`).
3. Azure OpenAI Service (`--azure-openai-endpoint`).

### Q: What operating systems are supported?
The agent runs identically on **Windows (PowerShell & CMD)**, **Linux (Ubuntu, Debian, RHEL, Alpine)**, and **macOS**.
