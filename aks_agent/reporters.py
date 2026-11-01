import json
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from .models import InvestigationReport, Severity, TimelinePhase


class TerminalReporter:
    """Rich interactive terminal reporter styled for Azure Kubernetes Service."""

    def __init__(self):
        self.console = Console()

    def render(self, report: InvestigationReport):
        # Header Badge
        sev_color = {
            Severity.CRITICAL: "bold white on red",
            Severity.HIGH: "bold white on dark_red",
            Severity.MEDIUM: "bold black on yellow",
            Severity.LOW: "bold white on blue",
            Severity.INFO: "bold white on cyan",
        }.get(report.severity, "bold white on blue")

        sev_badge = f"[{sev_color}] {report.severity.value} [/]"
        title = f"[bold #0078D4]☁️ AKS Incident Report[/] • [white]{report.incident_id}[/] • {sev_badge}"

        # Metadata Details
        meta_lines = [
            f"[bold cyan]Source:[/] {report.log_source}",
            f"[bold cyan]Root Cause Category:[/] [bold]{report.root_cause_category}[/]",
        ]
        if report.azure_metadata:
            meta = report.azure_metadata
            if meta.cluster_name:
                meta_lines.append(f"[bold cyan]AKS Cluster:[/] {meta.cluster_name}")
            if meta.resource_group:
                meta_lines.append(f"[bold cyan]Resource Group:[/] {meta.resource_group}")
            if meta.node_pool:
                meta_lines.append(f"[bold cyan]Node Pool:[/] {meta.node_pool}")
        if report.ai_provider:
            meta_lines.append(f"[bold cyan]AI Diagnosis:[/] [italic green]{report.ai_provider}[/]")

        header_text = "\n".join(meta_lines)
        self.console.print(Panel(header_text, title=title, border_style="#0078D4", box=box.ROUNDED))

        # Root Cause Summary Panel
        self.console.print(
            Panel(
                f"[bold white]{report.root_cause_summary}[/]",
                title="[bold yellow]🎯 Root Cause Deduction[/]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        # Timeline Table
        if report.timeline.events:
            t_table = Table(title="[bold cyan]⏱️ Chronological Incident Progression[/]", box=box.SIMPLE_HEAVY)
            t_table.add_column("Timestamp", style="dim", no_wrap=True)
            t_table.add_column("Phase", style="bold magenta")
            t_table.add_column("Incident Event")

            for ev in report.timeline.events:
                phase_color = {
                    TimelinePhase.INCEPTION: "red",
                    TimelinePhase.PROPAGATION: "yellow",
                    TimelinePhase.KUBELET_ACTION: "blue",
                    TimelinePhase.AZURE_INTERVENTION: "cyan",
                }.get(ev.phase, "white")

                t_table.add_row(
                    ev.timestamp or "N/A",
                    f"[{phase_color}]{ev.phase.value}[/]",
                    f"{ev.description}\n[dim italic]{ev.log_snippet or ''}[/]" if ev.log_snippet else ev.description,
                )
            self.console.print(t_table)

        # Supporting Empirical Evidence
        if report.key_evidence:
            e_table = Table(title="[bold cyan]🔍 Empirical Supporting Evidence (Verbatim Logs)[/]", box=box.SIMPLE_HEAVY)
            e_table.add_column("Lines", justify="center", style="dim")
            e_table.add_column("Signal Type", style="bold green")
            e_table.add_column("Verbatim Log Excerpt")

            for ev in report.key_evidence:
                lines_str = ",".join(str(l) for l in ev.line_numbers)
                e_table.add_row(lines_str, ev.signal_type, ev.log_snippet)
            self.console.print(e_table)

        # Actionable Remediation Plan
        if report.remediation_plan:
            r_table = Table(title="[bold green]🛠️ Remediation & Prevention Plan[/]", box=box.ROUNDED)
            r_table.add_column("Action", style="bold yellow")
            r_table.add_column("Description")
            r_table.add_column("Executable Command / Link", style="bold cyan")

            for step in report.remediation_plan:
                cmd = step.command or step.doc_url or ""
                r_table.add_row(step.action_type, step.description, cmd)
            self.console.print(r_table)


class MarkdownReporter:
    """GitHub Flavored / Azure DevOps Markdown reporter for incident tickets."""

    def render(self, report: InvestigationReport) -> str:
        lines = []
        lines.append(f"# ☁️ AKS Incident Report: `{report.incident_id}`")
        lines.append("")
        lines.append(f"> **Severity**: **{report.severity.value}** | **Category**: `{report.root_cause_category}` | **Generated**: {report.generated_at.isoformat()}Z")
        if report.ai_provider:
            lines.append(f"> **AI Diagnosis Provider**: *{report.ai_provider}*")
        lines.append("")

        lines.append("## 🎯 Root Cause Deduction")
        lines.append("")
        lines.append(f"**{report.root_cause_summary}**")
        lines.append("")

        if report.detailed_findings:
            lines.append("### Key Findings")
            for f in report.detailed_findings:
                lines.append(f"- {f}")
            lines.append("")

        if report.timeline.events:
            lines.append("## ⏱️ Chronological Incident Progression")
            lines.append("")
            lines.append("| Timestamp | Phase | Progression Event |")
            lines.append("| :--- | :--- | :--- |")
            for ev in report.timeline.events:
                lines.append(f"| `{ev.timestamp or 'N/A'}` | **{ev.phase.value}** | {ev.description} |")
            lines.append("")

        if report.key_evidence:
            lines.append("## 🔍 Supporting Empirical Evidence")
            lines.append("")
            for ev in report.key_evidence:
                lines_str = ",".join(str(l) for l in ev.line_numbers)
                lines.append(f"#### Signal: `{ev.signal_type}` (Lines {lines_str})")
                lines.append("```text")
                lines.append(ev.log_snippet)
                lines.append("```")
                lines.append("")

        if report.remediation_plan:
            lines.append("## 🛠️ Actionable Remediation Plan")
            lines.append("")
            for step in report.remediation_plan:
                lines.append(f"### `{step.action_type}`: {step.description}")
                if step.command:
                    lines.append("```bash")
                    lines.append(step.command)
                    lines.append("```")
                if step.doc_url:
                    lines.append(f"📖 Reference: [{step.doc_url}]({step.doc_url})")
                lines.append("")

        return "\n".join(lines)


class JSONReporter:
    """Machine-readable JSON serialization for CI/CD pipelines & automated alerts."""

    def render(self, report: InvestigationReport) -> str:
        return report.model_dump_json(indent=2)


class TeamsAdaptiveCardReporter:
    """Generates Microsoft Teams Adaptive Cards for webhook incident delivery."""

    def render(self, report: InvestigationReport) -> Dict[str, Any]:
        sev_color = {
            Severity.CRITICAL: "Attention",
            Severity.HIGH: "Warning",
            Severity.MEDIUM: "Warning",
            Severity.LOW: "Accent",
            Severity.INFO: "Default",
        }.get(report.severity, "Accent")

        facts = [
            {"title": "Incident ID", "value": report.incident_id},
            {"title": "Severity", "value": report.severity.value},
            {"title": "Category", "value": report.root_cause_category},
            {"title": "Source", "value": report.log_source},
        ]
        if report.azure_metadata and report.azure_metadata.cluster_name:
            facts.append({"title": "Cluster", "value": report.azure_metadata.cluster_name})

        card_body = [
            {
                "type": "TextBlock",
                "text": f"☁️ AKS Incident Report: {report.incident_id}",
                "weight": "Bolder",
                "size": "Medium",
                "color": sev_color,
            },
            {
                "type": "TextBlock",
                "text": report.root_cause_summary,
                "wrap": True,
                "weight": "Bolder",
            },
            {
                "type": "FactSet",
                "facts": facts,
            },
        ]

        if report.remediation_plan:
            actions_text = []
            for step in report.remediation_plan[:3]:
                if step.command:
                    actions_text.append(f"• **{step.action_type}**: `{step.command}`")
                else:
                    actions_text.append(f"• **{step.action_type}**: {step.description}")

            card_body.append({
                "type": "TextBlock",
                "text": "**Suggested Remediation:**\n" + "\n".join(actions_text),
                "wrap": True,
            })

        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": card_body,
                    },
                }
            ],
        }
        return card

