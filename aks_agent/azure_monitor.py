import os
import logging
from datetime import timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class AzureMonitorLogFetcher:
    """Client for querying Azure Log Analytics workspaces using KQL (Kusto Query Language)."""

    def __init__(self, workspace_id: Optional[str] = None):
        self.workspace_id = (
            workspace_id
            or os.environ.get("AZURE_LOG_ANALYTICS_WORKSPACE_ID")
            or os.environ.get("WORKSPACE_ID")
        )

    def is_configured(self) -> bool:
        return bool(self.workspace_id)

    def fetch_pod_logs(
        self,
        pod_name: str,
        namespace: Optional[str] = None,
        hours: int = 2,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries ContainerLogV2 and KubeEvents for a specific pod over a given timespan."""
        ws_id = workspace_id or self.workspace_id
        if not ws_id:
            raise ValueError(
                "Azure Log Analytics Workspace ID is required. Pass --workspace or set AZURE_LOG_ANALYTICS_WORKSPACE_ID."
            )

        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import LogsQueryClient, LogsQueryStatus

        credential = DefaultAzureCredential()
        client = LogsQueryClient(credential)

        # Build KQL Query
        ns_filter = f"| where PodNamespace == '{namespace}'" if namespace else ""
        query = f"""
        ContainerLogV2
        | where TimeGenerated > ago({hours}h)
        | where PodName has '{pod_name}'
        {ns_filter}
        | project TimeGenerated, PodName, PodNamespace, ContainerName, LogMessage, LogLevel, Computer
        | order by TimeGenerated asc
        """

        logger.info(f"Executing KQL query against Azure Log Analytics workspace {ws_id} for pod {pod_name}...")
        response = client.query_workspace(
            workspace_id=ws_id,
            query=query,
            timespan=timedelta(hours=hours),
        )

        records: List[Dict[str, Any]] = []
        if response.status == LogsQueryStatus.SUCCESS:
            for table in response.tables:
                columns = [c.name for c in table.columns]
                for row in table.rows:
                    record = dict(zip(columns, row))
                    records.append(record)
        else:
            logger.warning(f"Azure Monitor query status returned partial or failed: {response.status}")

        return records

