# 📖 How-To Guide & Usage Recipes

Welcome to the **AKS Investigation Agent** practical guide! This document provides real-world recipes, copy-paste commands, and workflows for Site Reliability Engineers (SREs), DevOps practitioners, and platform engineers.

---

## 📑 Table of Contents
1. [⚡ Quick Start Checklist](#-quick-start-checklist)
2. [Recipe 1: Offline / Local Log Analysis (Air-Gapped)](#recipe-1-offline--local-log-analysis-air-gapped)
3. [Recipe 2: Live On-Call SRE Debugging (kubectl & az aks piping)](#recipe-2-live-on-call-sre-debugging-kubectl--az-aks-piping)
4. [Recipe 3: Direct Azure Log Analytics Querying (KQL)](#recipe-3-direct-azure-log-analytics-querying-kql)
5. [Recipe 4: ChatOps & Incident Delivery (Teams & Azure DevOps)](#recipe-4-chatops--incident-delivery-teams--azure-devops)
6. [Recipe 5: AI-Powered Deep Diagnosis with Azure OpenAI](#recipe-5-ai-powered-deep-diagnosis-with-azure-openai)
7. [Recipe 6: Python SDK & CI/CD Integration](#recipe-6-python-sdk--cicd-integration)
8. [🎛️ CLI Options & Flags Reference](#️-cli-options--flags-reference)
9. [❓ Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)

---

## ⚡ Quick Start Checklist

### 1. Clone & Set Up Virtual Environment

#### On Windows (PowerShell)
```powershell
git clone https://github.com/manjulearnings/aks-investigation-agent.git
cd aks-investigation-agent
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
```

#### On Linux / macOS (Bash / Zsh)
```bash
git clone https://github.com/manjulearnings/aks-investigation-agent.git
cd aks-investigation-agent
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Verify Installation
```bash
aks-agent --help
```

---

## Recipe 1: Offline / Local Log Analysis (Air-Gapped)

> **Use Case:** Analyzing exported pod logs, incident archives, or troubleshooting in an isolated network with **zero Azure credentials or cloud access**.

### Analyze a single log file:
```bash
aks-agent sample_logs/01_azure_cni_ip_exhaustion.log
```

### Try other bundled real-world incident samples:
```bash
# Azure Disk Multi-Attach lock between nodes
aks-agent sample_logs/02_azure_disk_multi_attach.log

# Key Vault CSI Workload Identity authentication failure
aks-agent sample_logs/03_azure_keyvault_csi_failure.log

# ACR Unauthorized ImagePull (missing AcrPull role)
aks-agent sample_logs/04_acr_unauthorized_imagepull.log

# Pod OOMKilled (Exit Code 137) with memory spikes
aks-agent sample_logs/05_aks_oom_crashloop.log
```

---

## Recipe 2: Live On-Call SRE Debugging (kubectl & az aks piping)

> **Use Case:** An engineer is on-call, alerted to a crashing or pending pod, and wants instant root-cause analysis without manually scrolling through hundreds of log lines.

### Stream live logs directly from `kubectl`:
```bash
# Stream previous crashed container instance:
kubectl logs pod/checkout-service-7bb8c57657-69vsd -n prod --previous | aks-agent -

# Tail live failing logs:
kubectl logs pod/payment-processor-54fc794b65-qkwg2 -n billing --tail=200 | aks-agent -
```

### Stream directly via `az aks` (No local kubeconfig needed):
```bash
az aks command invoke \
  --resource-group rg-production-aks \
  --name aks-cluster-prod \
  --command "kubectl logs pod/inventory-api-7b878564fb-f4pnd -n core --previous" | aks-agent -
```

---

## Recipe 3: Direct Azure Log Analytics Querying (KQL)

> **Use Case:** The crashed pod has already been restarted or terminated by Kubernetes, so `kubectl logs` is no longer available. Query historical logs preserved in Azure Log Analytics (`ContainerLogV2`).

### Prerequisites
1. Log in via Azure CLI:
   ```bash
   az login
   ```
2. Ensure your account or Managed Identity has the **Log Analytics Reader** role on the target workspace.

### Run query:
```bash
aks-agent --query-monitor \
  --workspace-id "11223344-5566-7788-99aa-bbccddeeff00" \
  --pod "payment-gateway" \
  --namespace "prod" \
  --hours 2
```

*(You can also set the workspace ID as an environment variable `export AZURE_LOG_ANALYTICS_WORKSPACE_ID="<guid>"` to avoid passing it every time).*

---

## Recipe 4: ChatOps & Incident Delivery (Teams & Azure DevOps)

> **Use Case:** Automatically send structured incident reports to your team's communication channels or ticketing systems.

### 1. Send an interactive Adaptive Card to Microsoft Teams
Post directly to an SRE alert channel via Incoming Webhook:
```bash
aks-agent incident.log \
  --teams-webhook "https://outlook.office.com/webhook/your-webhook-guid/IncomingWebhook/..."
```

### 2. Generate Markdown for Azure DevOps / Jira / GitHub
Export a cleanly formatted markdown file ready to paste into an Azure DevOps Bug or GitHub Issue:
```bash
aks-agent incident.log --format markdown --output incident-report.md
```

### 3. Generate JSON for Automated Alerting Pipelines
Output machine-readable JSON for ingestion into Datadog, Splunk, PagerDuty, or ServiceNow:
```bash
aks-agent incident.log --format json --output incident.json
```

---

## Recipe 5: AI-Powered Deep Diagnosis with Azure OpenAI

> **Use Case:** When an incident is caused by an unclassified application bug or custom stack trace (C#, Java, Python, Go, Node.js) rather than an infrastructure error, let Azure OpenAI (GPT-4o) diagnose the code.

### 1. Configure Azure OpenAI Endpoint
You can authenticate securely via **Azure Entra ID (zero secrets)**:
```bash
az login
export AZURE_OPENAI_ENDPOINT="https://<your-resource-name>.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
```

Or provide an API Key if preferred:
```bash
export AZURE_OPENAI_KEY="your-api-key-here"
```

### 2. Run investigation with AI enrichment
```bash
# Automatically invokes AI if application crash is detected:
aks-agent app-crash.log

# Or force AI analysis regardless of error type:
aks-agent app-crash.log --force-ai
```

---

## Recipe 6: Python SDK & CI/CD Integration

> **Use Case:** Embedding AKS failure diagnostics into your own automated scripts, test suites, or CI/CD deployment pipelines.

### Programmatic Python Usage:
```python
from aks_agent import AKSInvestigationAgent
from aks_agent.models import AzureClusterMetadata

# 1. Initialize the agent
agent = AKSInvestigationAgent()

# Optional: enrich with cluster context
metadata = AzureClusterMetadata(
    cluster_name="aks-prod-weu",
    resource_group="rg-production",
    subscription_id="00000000-0000-0000-0000-000000000000"
)

# 2. Run investigation
report = agent.investigate_file(
    filepath="sample_logs/01_azure_cni_ip_exhaustion.log",
    azure_metadata=metadata
)

# 3. Access structured properties
print(f"Incident:    {report.incident_title}")
print(f"Severity:    {report.severity.value}")
print(f"Root Cause:  {report.root_cause_category}")
print(f"Confidence:  {report.confidence_score * 100:.0f}%")

print("\nRemediation Actions:")
for step in report.remediation_actions:
    print(f" - {step.title}: {step.command or step.description}")
```

### CI/CD Deployment Verification (GitHub Actions / Azure Pipelines):
```bash
# Run post-deployment smoke test and fail build if fatal errors detected:
kubectl logs deployment/catalog-service -n staging | aks-agent - --format json --output report.json

# Check severity with jq:
python -c "import json; r=json.load(open('report.json')); exit(1 if r['severity'] == 'CRITICAL' else 0)"
```

---

## 🎛️ CLI Options & Flags Reference

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Log Source** | `[log_source]` | Path to log file, or `-` for stdin pipe | `None` |
| **Output Format** | `-f, --format` | `terminal`, `markdown`, `json`, `teams` | `terminal` |
| **Output File** | `-o, --output` | File path to write the formatted report | `stdout` |
| **Teams Webhook**| `--teams-webhook` | Incoming Webhook URL for Microsoft Teams | `None` |
| **Query Monitor** | `--query-monitor`| Enable live Log Analytics KQL ingestion | `False` |
| **Workspace ID** | `--workspace-id` | Azure Log Analytics Workspace GUID | Env Var |
| **Pod Name** | `--pod` | Target pod name for Log Analytics query | `None` |
| **Namespace** | `--namespace` | Target namespace for Log Analytics query| `None` |
| **Query Hours** | `--hours` | Lookback window in hours for Log Analytics | `2` |
| **Force AI** | `--force-ai` | Force Azure OpenAI diagnosis for all errors | `False` |
| **OpenAI Endpoint**| `--azure-openai-endpoint` | Azure OpenAI resource endpoint | Env Var |
| **OpenAI Deployment**| `--azure-openai-deployment` | Azure OpenAI deployment model name | `gpt-4o` |

---

## ❓ Frequently Asked Questions (FAQ)

### Q: Do I need an Azure account to use this?
**No.** Offline file analysis, sample logs, and stdin pipes work completely air-gapped without any Azure subscription, credentials, or network connection.

### Q: Does this send my logs to the internet?
**No.** All deterministic failure analysis runs 100% locally on your machine. Network calls only happen if:
1. You explicitly query Azure Log Analytics (`--query-monitor`).
2. You provide a Microsoft Teams webhook (`--teams-webhook`).
3. You configure Azure OpenAI Service (`--azure-openai-endpoint`).

### Q: What shell is supported?
The agent runs identically on **Windows PowerShell**, **Command Prompt**, **Linux Bash/Zsh**, and **macOS Terminal**.

