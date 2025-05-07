import pandas as pd
from databricks.sdk import WorkspaceClient

import io
from contextlib import redirect_stdout

from mcp.types import Tool as ToolSpec, TextContent

from databricks.labs.mcp.servers.unity_catalog.tools.base_tool import BaseTool
from databricks_ai_bridge.genie import Genie
from databricks.sdk.service.catalog import TableType
import json

_SEARCH_PAGE_SIZE = 50

class SearchTool(BaseTool):
    def __init__(self):
        input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword-based search for Databricks product entities, including data tables, vector search indexes, Genie Spaces that you can talk to via a natural language interface for data retrieval, and more.",
                }
            },
            "required": ["query"],
        }
        
        tool_spec = ToolSpec(name="search", description="Search for information in the Databricks catalog", inputSchema=input_schema)
        super().__init__(tool_spec=tool_spec)

    def execute(self, **kwargs):
        ws = WorkspaceClient()
        res = ws.api_client.do(
            "GET",
            "/api/2.0/search-midtier/unified-search",
            query={
                "query.query": kwargs["query"],
                # "filters.result_types": "TABLE",
                "page_size": _SEARCH_PAGE_SIZE,
                "query.search_mode": "HYBRID",
                # "filters.catalog_names": catalog_name,
                # "filters.schema_names": schema_name,
            }
        )
        results = res.get("results")
        return [TextContent(type="text", text=json.dumps(results))]
    
class CreateGenieSpaceTool(BaseTool):
    def __init__(self):
        input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword-based search for Databricks product entities, including data tables, vector search indexes, Genie Spaces that you can talk to via a natural language interface for data retrieval, and more.",
                }
            },
            "required": ["query"],
        }
        
        tool_spec = ToolSpec(name="search", description="Search for information in the Databricks catalog", inputSchema=input_schema)
        super().__init__(tool_spec=tool_spec)

    def execute(self, **kwargs):
        ws = WorkspaceClient()
        res = ws.api_client.do(
            "GET",
            "/api/2.0/search-midtier/unified-search",
            query={
                "query.query": kwargs["query"],
                # "filters.result_types": "TABLE",
                "page_size": _SEARCH_PAGE_SIZE,
                "query.search_mode": "HYBRID",
                # "filters.catalog_names": catalog_name,
                # "filters.schema_names": schema_name,
            }
        )
        results = res.get("results")
        return [TextContent(type="text", text=json.dumps(results))]


CREATE_GENIE_SPACE_TOOL = CreateGenieSpaceTool()
SEARCH_TOOL = SearchTool()

