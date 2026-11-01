import re
import json
import csv
import io
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from .models import StructuredLogEntry

# Standard timestamp regex patterns
TIMESTAMP_ISO_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

# CRI-O / containerd format: 2026-11-01T10:00:00.123456789Z stdout F Message...
CRIO_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(stdout|stderr)\s+([FP])\s+(.*)$"
)

# Standard Kubernetes Event log line: Warning  FailedScheduling  pod/checkout-xxx  0/3 nodes available
K8S_EVENT_PATTERN = re.compile(
    r"^(Normal|Warning|Error)\s+([A-Za-z0-9_]+)\s+(?:pod/|deployment/|node/)?([^\s]+)\s+(.*)$"
)

# Stack trace indicators across runtimes
STACK_TRACE_START_PATTERNS = [
    re.compile(r"^Traceback \(most recent call last\):"),
    re.compile(r"^[A-Za-z0-9_.]+(?:Exception|Error):"),
    re.compile(r"^panic:\s+"),
    re.compile(r"^goroutine \d+ \[[^\]]+\]:"),
    re.compile(r"^\s+at [A-Za-z0-9_.$<>]+\([^)]+\)"),
]


class AKSLogParser:
    """Intelligent log parser for Kubernetes & Azure AKS telemetry.

    Supports:
      - containerd / CRI-O log streams
      - Docker JSON & stdout/stderr logs
      - Azure Monitor ContainerLog & ContainerLogV2 (JSON / CSV / KQL output)
      - Kubernetes Event streams
      - Multi-line stack trace reconstruction
    """

    def parse_text(self, text: str) -> List[StructuredLogEntry]:
        """Parses a multi-line log string into structured entries."""
        lines = text.splitlines()
        if not lines:
            return []

        # Check if the entire payload is a JSON array or CSV from Azure Log Analytics
        stripped = text.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                data = json.loads(stripped)
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    return self._parse_azure_monitor_json_list(data)
            except Exception:
                pass

        # Check if payload is CSV (e.g. exported from Azure Portal Log Analytics)
        if "ContainerLogV2" in lines[0] or ("TimeGenerated" in lines[0] and "LogMessage" in lines[0]):
            try:
                entries = self._parse_azure_monitor_csv(text)
                if entries:
                    return entries
            except Exception:
                pass

        # Fall back to line-by-line parsing with multi-line stack trace aggregation
        return self._parse_lines(lines)

    def _parse_lines(self, lines: List[str]) -> List[StructuredLogEntry]:
        entries: List[StructuredLogEntry] = []
        current_trace_entry: Optional[StructuredLogEntry] = None

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            # Check if this line continues an ongoing stack trace
            if current_trace_entry and self._is_stack_trace_continuation(line):
                current_trace_entry.stack_trace_lines.append(line)
                current_trace_entry.message += "\n" + line
                continue
            else:
                current_trace_entry = None

            # Attempt CRI-O format
            crio_match = CRIO_PATTERN.match(line)
            if crio_match:
                ts_str, stream, flag, msg = crio_match.groups()
                entry = StructuredLogEntry(
                    line_number=idx,
                    raw_text=line,
                    timestamp=self._parse_iso_timestamp(ts_str),
                    timestamp_str=ts_str,
                    stream=stream,
                    log_level=self._infer_log_level(msg, stream),
                    message=msg,
                )
                self._extract_k8s_attributes(entry)
                if self._is_stack_trace_start(msg):
                    entry.is_stack_trace = True
                    entry.stack_trace_lines.append(msg)
                    current_trace_entry = entry
                entries.append(entry)
                continue

            # Attempt JSON per line (ContainerLogV2 / Zap / Winston)
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    json_data = json.loads(stripped)
                    entry = self._parse_json_line(json_data, idx, line)
                    if entry:
                        entries.append(entry)
                        continue
                except Exception:
                    pass

            # Attempt Kubernetes Event format
            event_match = K8S_EVENT_PATTERN.match(line)
            if event_match:
                severity, reason, resource, msg = event_match.groups()
                entry = StructuredLogEntry(
                    line_number=idx,
                    raw_text=line,
                    log_level=severity.upper(),
                    message=f"[{reason}] {msg}",
                    pod_name=resource if "pod" in line.lower() else None,
                )
                entries.append(entry)
                continue

            # Standard line with timestamp prefix
            ts_match = TIMESTAMP_ISO_PATTERN.match(line)
            if ts_match:
                ts_str = ts_match.group(1)
                msg = line[len(ts_str):].lstrip(" :-\t")
                entry = StructuredLogEntry(
                    line_number=idx,
                    raw_text=line,
                    timestamp=self._parse_iso_timestamp(ts_str),
                    timestamp_str=ts_str,
                    log_level=self._infer_log_level(msg),
                    message=msg,
                )
                self._extract_k8s_attributes(entry)
                if self._is_stack_trace_start(msg):
                    entry.is_stack_trace = True
                    entry.stack_trace_lines.append(msg)
                    current_trace_entry = entry
                entries.append(entry)
                continue

            # Plain log line
            entry = StructuredLogEntry(
                line_number=idx,
                raw_text=line,
                log_level=self._infer_log_level(line),
                message=line,
            )
            self._extract_k8s_attributes(entry)
            if self._is_stack_trace_start(line):
                entry.is_stack_trace = True
                entry.stack_trace_lines.append(line)
                current_trace_entry = entry
            entries.append(entry)

        return entries

    def _parse_json_line(self, data: Dict[str, Any], line_num: int, raw_text: str) -> StructuredLogEntry:
        # Check for Azure ContainerLogV2 format
        # Common fields: TimeGenerated, PodName, PodNamespace, ContainerName, LogMessage, LogLevel
        msg = data.get("LogMessage") or data.get("message") or data.get("msg") or data.get("log") or json.dumps(data)
        ts_str = data.get("TimeGenerated") or data.get("time") or data.get("timestamp") or data.get("@timestamp")
        pod_name = data.get("PodName") or data.get("pod") or data.get("k8s_pod_name")
        container_name = data.get("ContainerName") or data.get("container")
        namespace = data.get("PodNamespace") or data.get("namespace")
        level = data.get("LogLevel") or data.get("level") or data.get("severity")

        entry = StructuredLogEntry(
            line_number=line_num,
            raw_text=raw_text,
            timestamp=self._parse_iso_timestamp(ts_str) if ts_str else None,
            timestamp_str=str(ts_str) if ts_str else None,
            log_level=str(level).upper() if level else self._infer_log_level(str(msg)),
            message=str(msg),
            pod_name=str(pod_name) if pod_name else None,
            container_name=str(container_name) if container_name else None,
            namespace=str(namespace) if namespace else None,
            azure_properties={k: v for k, v in data.items() if k.startswith("Azure") or k in ("Computer", "SubscriptionId")},
        )
        return entry

    def _parse_azure_monitor_json_list(self, records: List[Dict[str, Any]]) -> List[StructuredLogEntry]:
        entries = []
        for idx, rec in enumerate(records, start=1):
            raw = json.dumps(rec)
            entries.append(self._parse_json_line(rec, idx, raw))
        return entries

    def _parse_azure_monitor_csv(self, csv_text: str) -> List[StructuredLogEntry]:
        reader = csv.DictReader(io.StringIO(csv_text))
        entries = []
        for idx, row in enumerate(reader, start=1):
            msg = row.get("LogMessage") or row.get("LogEntry") or ""
            ts_str = row.get("TimeGenerated") or ""
            pod = row.get("PodName") or ""
            container = row.get("ContainerName") or ""
            ns = row.get("PodNamespace") or ""
            level = row.get("LogLevel") or row.get("LogSeverity") or ""

            entry = StructuredLogEntry(
                line_number=idx,
                raw_text=json.dumps(row),
                timestamp=self._parse_iso_timestamp(ts_str) if ts_str else None,
                timestamp_str=ts_str if ts_str else None,
                log_level=level.upper() if level else self._infer_log_level(msg),
                message=msg,
                pod_name=pod or None,
                container_name=container or None,
                namespace=ns or None,
            )
            entries.append(entry)
        return entries

    def _is_stack_trace_start(self, text: str) -> bool:
        for pattern in STACK_TRACE_START_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _is_stack_trace_continuation(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if line.startswith(" ") or line.startswith("\t"):
            return True
        if stripped.startswith("at ") or stripped.startswith("File "):
            return True
        if stripped.startswith("Caused by:") or stripped.startswith("... "):
            return True
        return False

    def _parse_iso_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        if not ts_str:
            return None
        # Clean fractional seconds down to 6 digits for standard python strptime
        cleaned = re.sub(r"(\.\d{6})\d+", r"\1", ts_str.strip())
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S,%f",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                pass
        return None

    def _infer_log_level(self, text: str, stream: Optional[str] = None) -> str:
        upper = text.upper()
        if "FATAL" in upper or "PANIC" in upper or "CRITICAL" in upper:
            return "FATAL"
        if "ERROR" in upper or "ERR" in upper or stream == "stderr":
            return "ERROR"
        if "WARN" in upper:
            return "WARN"
        if "INFO" in upper:
            return "INFO"
        if "DEBUG" in upper:
            return "DEBUG"
        return "INFO"

    def _extract_k8s_attributes(self, entry: StructuredLogEntry):
        """Extracts pod names or deployments embedded inside text lines."""
        pod_match = re.search(r"pod[/:\s]([a-z0-9][a-z0-9\-\.]{1,63}-[a-z0-9]{5,10}-[a-z0-9]{5})", entry.message, re.IGNORECASE)
        if pod_match and not entry.pod_name:
            entry.pod_name = pod_match.group(1)

