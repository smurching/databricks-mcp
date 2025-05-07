import pandas as pd
from databricks.sdk import WorkspaceClient

import io
from contextlib import redirect_stdout

from mcp.types import Tool as ToolSpec, TextContent

from databricks.labs.mcp.servers.unity_catalog.tools.base_tool import BaseTool
from databricks_ai_bridge.genie import Genie
from databricks.sdk.service.catalog import TableType


_MAX_TABLES_PER_GENIE_SPACE = 25
_MAX_TABLE_COMMENT_LENGTH = 128
_MAX_TOTAL_TABLE_DESCRIPTION_LENGTH = 1024

class TableQueryTool(BaseTool):
    def __init__(self, catalog_name: str, schema_name: str):
        raw_table_infos = WorkspaceClient().tables.list(
            catalog_name=catalog_name, schema_name=schema_name
        )
        table_infos = [
            t for t in raw_table_infos if t.table_type != TableType.EXTERNAL
        ][:_MAX_TABLES_PER_GENIE_SPACE]
        self.table_infos = table_infos

        self._workspace_client = WorkspaceClient()
        warehouse_id = self._workspace_client.warehouses.list()[0].id

        create_genie_resp = self._workspace_client.api_client.do(
            "POST",
            "/api/2.0/data-rooms",
            body={
                "display_name": f"tmp_{catalog_name}__{schema_name}",
                "warehouse_id": warehouse_id,
                "table_identifiers": [t.full_name for t in table_infos],
            },
        )
        self.genie = Genie(create_genie_resp["id"])

        # Create a description of the tables available for querying
        table_descriptions = []
        for table in table_infos:
            truncated_comment = table.comment[:_MAX_TABLE_COMMENT_LENGTH] if table.comment else ""
            table_descriptions.append(f"{table.full_name}: {truncated_comment}")

        tables_str = ", ".join(table_descriptions)[:_MAX_TOTAL_TABLE_DESCRIPTION_LENGTH]

        # Define the input schema for the tool
        input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": f"A natural language query about data in the following tables: {tables_str}. Databricks will extract the necessary insights from the tables in order to answer the question. Do not use SQL, use only plain English, and do not assume any knowledge of the conversation so far (treat this like a single turn tool for asking a question)",
                }
            },
            "required": ["query"],
        }

        tool_spec = ToolSpec(
            name=f"query_tables_{catalog_name}__{schema_name}",
            description=(
                "Powerful AI-driven SQL generator for Unity Catalog tables. "
                "Just ask in plain English—this tool will automatically handle complex joins, filters, aggregations, time-series analyses, cohort comparisons, "
                "and more across any of these tables: "
                f"{tables_str}"
            ),
            inputSchema=input_schema,
        )
        super().__init__(tool_spec=tool_spec)

    def _result_as_str(self, resp) -> str:
        """
        Always return the GenieResponse.result as a str.
        If it's a DataFrame, export it to a string format.
        """
        if isinstance(resp.result, pd.DataFrame):
            return resp.result.to_string(index=False)
        return str(resp.result)

    def execute(self, **kwargs):
        f = io.StringIO()
        with redirect_stdout(f):
            res = self.genie.ask_question(kwargs["query"])
            return [TextContent(type="text", text=self._result_as_str(res))]


def list_table_search_tools(settings) -> list[TableQueryTool]:
    catalog_name, schema_name = settings.schema_full_name.split(".")
    return [TableQueryTool(catalog_name, schema_name)]
