import sys
import argparse
from pathlib import Path
from typing import Optional
from .agent import AKSInvestigationAgent
from .models import AzureClusterMetadata
from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aks-agent",
        description="Autonomous Incident Investigation Agent for Azure Kubernetes Service (AKS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Analyze an AKS log file (Rich terminal report)
  aks-agent sample_logs/01_azure_cni_ip_exhaustion.log

  # 2. Pipe logs live from kubectl or az aks
  az aks command invoke --resource-group myRG --name myAKS --command "kubectl logs pod/checkout -n prod" | aks-agent -

  # 3. Query Azure Monitor / Log Analytics directly
  aks-agent --query-monitor --workspace-id <GUID> --pod checkout-service-7bb8c57657-69vsd --hours 1

  # 4. Generate Markdown for Azure DevOps / Jira
  aks-agent crash.log --format markdown --output incident-report.md

  # 5. Send report directly to Microsoft Teams
  aks-agent crash.log --teams-webhook https://outlook.office.com/webhook/xxx
        """,
    )

    parser.add_argument(
        "log_source",
        nargs="?",
        default=None,
        help="Path to the log file to analyze, or '-' to read from standard input.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["terminal", "markdown", "json", "teams"],
        default="terminal",
        help="Output report format (default: terminal).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Optional file path to write the formatted report to.",
    )
    parser.add_argument(
        "--force-ai",
        action="store_true",
        help="Force Azure OpenAI diagnosis even for standard classified failure modes.",
    )
    parser.add_argument(
        "--azure-openai-endpoint",
        type=str,
        default=None,
        help="Azure OpenAI resource endpoint URL (or set AZURE_OPENAI_ENDPOINT env var).",
    )
    parser.add_argument(
        "--azure-openai-deployment",
        type=str,
        default=None,
        help="Azure OpenAI deployment name (e.g. gpt-4o, gpt-4o-mini).",
    )
    parser.add_argument(
        "--query-monitor",
        action="store_true",
        help="Query Azure Log Analytics workspace directly instead of reading a local file.",
    )
    parser.add_argument(
        "--workspace-id",
        type=str,
        default=None,
        help="Azure Log Analytics Workspace ID for live querying.",
    )
    parser.add_argument(
        "--pod",
        type=str,
        default=None,
        help="Target pod name when querying Azure Log Analytics.",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Target namespace when querying Azure Log Analytics.",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=2,
        help="Hours lookback window for Azure Monitor query (default: 2).",
    )
    parser.add_argument(
        "--teams-webhook",
        type=str,
        default=None,
        help="Microsoft Teams Incoming Webhook URL to automatically post an Adaptive Card.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    agent = AKSInvestigationAgent(
        azure_openai_endpoint=args.azure_openai_endpoint,
        azure_openai_deployment=args.azure_openai_deployment,
        force_ai=args.force_ai,
        workspace_id=args.workspace_id,
    )

    report = None

    # Scenario A: Direct Azure Monitor Query
    if args.query_monitor:
        if not args.pod:
            sys.stderr.write("Error: --pod <pod-name> is required when using --query-monitor.\n")
            sys.exit(1)
        try:
            report = agent.investigate_azure_monitor(
                pod_name=args.pod,
                namespace=args.namespace,
                hours=args.hours,
                workspace_id=args.workspace_id,
            )
        except Exception as e:
            sys.stderr.write(f"Azure Monitor Query Error: {e}\n")
            sys.exit(1)

    # Scenario B: Stdin or File
    elif args.log_source:
        if args.log_source == "-":
            if sys.stdin.isatty():
                sys.stderr.write("Waiting for piped input from stdin (Press Ctrl+Z / Ctrl+D to submit)...\n")
            content = sys.stdin.read()
            report = agent.investigate(content, source_name="stdin")
        else:
            filepath = Path(args.log_source)
            if not filepath.exists():
                sys.stderr.write(f"Error: Log file not found: {args.log_source}\n")
                sys.exit(1)
            report = agent.investigate_file(filepath)
    else:
        parser.print_help()
        sys.exit(0)

    if not report:
        sys.stderr.write("Error: Failed to generate report.\n")
        sys.exit(1)

    # Post to Microsoft Teams if requested
    if args.teams_webhook:
        success = agent.post_to_teams_webhook(report, args.teams_webhook)
        if success:
            sys.stdout.write(f"Successfully posted incident report to Microsoft Teams!\n")
        else:
            sys.stderr.write("Warning: Failed to post Adaptive Card to Teams webhook.\n")

    # Render according to requested output format
    if args.format == "terminal":
        agent.print_terminal_report(report)
        if args.output:
            # Also write markdown to the output path if specified
            md = agent.export_markdown(report)
            Path(args.output).write_text(md, encoding="utf-8")
            sys.stdout.write(f"\n[Report saved to {args.output}]\n")

    elif args.format == "markdown":
        md = agent.export_markdown(report)
        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
            sys.stdout.write(f"Report saved to {args.output}\n")
        else:
            sys.stdout.write(md + "\n")

    elif args.format == "json":
        json_str = agent.export_json(report)
        if args.output:
            Path(args.output).write_text(json_str, encoding="utf-8")
            sys.stdout.write(f"Report saved to {args.output}\n")
        else:
            sys.stdout.write(json_str + "\n")

    elif args.format == "teams":
        import json
        card = agent.export_teams_card(report)
        card_str = json.dumps(card, indent=2)
        if args.output:
            Path(args.output).write_text(card_str, encoding="utf-8")
            sys.stdout.write(f"Adaptive Card saved to {args.output}\n")
        else:
            sys.stdout.write(card_str + "\n")


if __name__ == "__main__":
    main()

