import pytest
import pandas as pd
from types import SimpleNamespace
from databricks.sdk.service.catalog import TableType
from mcp.types import TextContent
import databricks.labs.mcp.servers.unity_catalog.tools.table_query_tool as module

# Global variable for dummy table infos used in patches
table_infos = []

class DummyTableInfo:
    def __init__(self, table_type, full_name, comment):
        self.table_type = table_type
        self.full_name = full_name
        self.comment = comment

class DummyWarehouse:
    def __init__(self, id):
        self.id = id

class DummyApiClient:
    def do(self, method, path, body):
        # Return a dummy genie space ID
        return {"id": "dummy_genie_id"}

class DummyWorkspaceClient:
    def __init__(self, table_infos):
        self._table_infos = table_infos
        self.api_client = DummyApiClient()

    @property
    def tables(self):
        return SimpleNamespace(list=lambda catalog_name, schema_name: self._table_infos)

    @property
    def warehouses(self):
        return SimpleNamespace(list=lambda: [DummyWarehouse("dummy_wh_id")])

@pytest.fixture(autouse=True)
def patch_workspace_and_genie(monkeypatch):
    # Patch WorkspaceClient to use dummy implementation closing over table_infos
    monkeypatch.setattr(module, "WorkspaceClient", lambda: DummyWorkspaceClient(table_infos))
    # Patch Genie to a simple stub that echoes the query or could be overridden per-test
    monkeypatch.setattr(module, "Genie", lambda id: SimpleNamespace(ask_question=lambda q: SimpleNamespace(result=q)))
    yield


def test_init_filters_external_and_sets_genie():
    # Prepare one managed and one external table
    internal = DummyTableInfo(TableType.MANAGED, "db.schema.t1", "comment1")
    external = DummyTableInfo(TableType.EXTERNAL, "db.schema.t2", "comment2")
    global table_infos
    table_infos = [internal, external]

    # Instantiate the tool
    tool = module.TableQueryTool("db", "schema")

    # Only the managed table should be kept
    assert len(tool.table_infos) == 1
    assert tool.table_infos[0].full_name == "db.schema.t1"

    # Genie instance should have been created with our dummy ID
    # and provide an ask_question method
    assert hasattr(tool.genie, "ask_question")


def test_result_as_str_non_dataframe():
    # Bypass __init__ and directly test the helper
    tool = module.TableQueryTool.__new__(module.TableQueryTool)
    resp = SimpleNamespace(result="hello")
    assert tool._result_as_str(resp) == "hello"


def test_result_as_str_dataframe():
    tool = module.TableQueryTool.__new__(module.TableQueryTool)
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    resp = SimpleNamespace(result=df)
    output = tool._result_as_str(resp)
    # Should include column headers and at least one row value
    assert "a" in output and "b" in output
    assert "1" in output


def test_execute_returns_textcontent(monkeypatch):
    # Override table_infos and patch to return a DataFrame result
    df = pd.DataFrame({"x": [10]})
    local_tables = [DummyTableInfo(TableType.MANAGED, "db.schema.t1", "comment")]
    monkeypatch.setattr(module, "WorkspaceClient", lambda: DummyWorkspaceClient(local_tables))
    monkeypatch.setattr(module, "Genie", lambda id: SimpleNamespace(ask_question=lambda q: SimpleNamespace(result=df)))

    tool = module.TableQueryTool("db", "schema")
    outputs = tool.execute(query="test query")

    # Should return a list with a single TextContent
    assert isinstance(outputs, list) and len(outputs) == 1
    content = outputs[0]
    assert isinstance(content, TextContent)
    # The DataFrame value should be stringified
    assert "10" in content.text


def test_list_table_search_tools():
    settings = SimpleNamespace(schema_full_name="cat.sch")
    global table_infos
    table_infos = [DummyTableInfo(TableType.MANAGED, "cat.sch.t1", "")]  

    tools = module.list_table_search_tools(settings)
    assert isinstance(tools, list) and len(tools) == 1
    assert isinstance(tools[0], module.TableQueryTool)
