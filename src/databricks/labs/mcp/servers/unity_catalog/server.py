import logging
import collections
import json
import io
from contextlib import redirect_stdout

from mcp.server import NotificationOptions, Server
from mcp.server.fastmcp import FastMCP, Image

from mcp.server.stdio import stdio_server
from mcp.types import Tool as ToolSpec, TextContent
from databricks.labs.mcp.servers.unity_catalog.tools import (
    list_all_tools,
    Content,
)

from databricks_ai_bridge.genie import Genie

from databricks.sdk import WorkspaceClient
from databricks.labs.mcp.servers.unity_catalog.cli import get_settings

from databricks.labs.mcp.servers.unity_catalog.tools.base_tool import BaseTool
from databricks.labs.mcp._version import __version__ as VERSION

# The logger instance for this module.
LOGGER = logging.getLogger(__name__)


def _warn_if_duplicate_tool_names(tools: list[BaseTool]):
    tool_names = [tool.tool_spec.name for tool in tools]
    duplicate_tool_names = [
        item for item, count in collections.Counter(tool_names).items() if count > 1
    ]
    if duplicate_tool_names:
        LOGGER.warning(
            f"Duplicate tool names detected: {duplicate_tool_names}. For each duplicate tool name, "
            f"picking one of the tools with that name. This can happen if your UC schema "
            f"contains a function and a vector search index with the same name"
        )


def get_tools_dict(settings) -> dict[str, BaseTool]:
    """
    Returns a dictionary of all tools with their names as keys and tool objects as values.
    """
    # TODO: if LLM tool name length limits allow, dedup tool names by tool type
    # (e.g. function name and vector search index name)
    all_tools = list_all_tools(settings=get_settings())
    _warn_if_duplicate_tool_names(all_tools)
    return {
        tool.tool_spec.name: tool for tool in list_all_tools(settings=get_settings())
    }


def start() -> None:
    # server = Server(name="mcp-unitycatalog", version=VERSION)
    server = FastMCP(name="mcp-unitycatalog", version=VERSION)
    tools_dict = get_tools_dict(settings=get_settings())


    
    @server.tool()
    def run_sql(sql: str) -> str:
        """
        Run a stateless, read-only SQL query in Databricks.
        
        Can be used to also query metadata, e.g. 
        1. To discover tables and other data sources
        via commands like `SHOW CATALOGS`, `SHOW SCHEMAS in <catalog_name>`, `SHOW TABLES IN <catalog_name>.<schema_name>`, etc.
        2. To understand the schema of a table, e.g. `DESCRIBE TABLE <table>` or `DESCRIBE TABLE EXTENDED <table>` to enable generating subsequent SQL queries.


        Note that each command execution is a separate Databricks SQL statement, and that the session state is not retained between command executions.

        :param sql: The SQL query to run
        :return: The result of the SQL query
        """
        w = WorkspaceClient()
        warehouse_id = w.warehouses.list()[0].id
        return w.statement_execution.execute_statement(sql, warehouse_id)    
    

    @server.tool()
    def create_genie_space(name: str, table_full_names: list[str]) -> str:
        """ 
        Create a new genie space.
        Genie spaces are powerful AI-driven SQL generators for Unity Catalog tables, and can answer questions about the data in the specified
        set of tables.

        :param name: The name of the genie space
        :param table_full_names: List of full names of the tables ([catalog.schema.table0, catalog.schema.table1, ...]) to include in the genie space
        :return: The ID of the new genie space
        """
        w = WorkspaceClient()
        warehouse_id = w.warehouses.list()[0].id

        create_genie_resp = w.api_client.do(
            "POST",
            "/api/2.0/data-rooms",
            body={
                "display_name": name,
                "warehouse_id": warehouse_id,
                "table_identifiers": table_full_names,
            },
        )
        return create_genie_resp["id"]

    @server.tool()
    def ask_genie(query: str, genie_space_id: str) -> list[str]:
        """
        Ask a genie space a natural language English question about data. 
        Genie spaces are powerful AI-driven SQL generators for Unity Catalog tables, and can answer questions about the data in the tables.
        To get the genie space ID, create a new genie space or search for existing genie spaces.

        :param query: The question to ask the genie space
        :param genie_space_id: The ID of the genie space to ask the question
        :return: The answer to the question
        """
        genie = Genie(genie_space_id)
        f = io.StringIO()
        with redirect_stdout(f):
            return genie.ask_question(query)

    # @server.tool()
    # def search_databricks(query: str) -> str:
    #     """
    #     Search for information (data sources, existing genie spaces, tables, vector search indexes, etc.) in Databricks

    #     :param query: The keyword query to use to search the Databricks product
    #     :return: A list of results  
    #     """
    #     ws = WorkspaceClient()
    #     res = ws.api_client.do(
    #         "GET",
    #         "/api/2.0/search-midtier/unified-search",
    #         query={
    #             "query.query": query,
    #             # "filters.result_types": "TABLE",
    #             "page_size": 25,
    #             "query.search_mode": "HYBRID",
    #             # "filters.catalog_names": catalog_name,
    #             # "filters.schema_names": schema_name,
    #         }
    #     )
    #     results = res.get("results")
    #     return [TextContent(type="text", text=json.dumps(results))]
    
    server.run()

    # options = server.create_initialization_options(
    #     notification_options=NotificationOptions(
    #         resources_changed=True, tools_changed=True
    #     )
    # )
    # async with stdio_server() as (read_stream, write_stream):
    #     await server.run(read_stream, write_stream, options, raise_exceptions=True)
