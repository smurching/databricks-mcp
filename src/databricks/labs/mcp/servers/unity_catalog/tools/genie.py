import functools
import time
import json
import logging
from typing import Union
from pydantic import BaseModel, Field
from pydantic.json import pydantic_encoder

from databricks.sdk import WorkspaceClient
from mcp.types import TextContent, Tool as ToolSpec

from databricks.labs.mcp.servers.unity_catalog.tools.base_tool import BaseTool
from databricks_ai_bridge.genie import Genie


# Logger
LOGGER = logging.getLogger(__name__)


def dump_json(maybe_model: Union[BaseModel, list, dict, None]) -> str:
    if maybe_model is None:
        return ""
    elif isinstance(maybe_model, list) or isinstance(maybe_model, dict):
        return json.dumps(maybe_model, default=pydantic_encoder, separators=(",", ":"))
    else:
        return maybe_model.model_dump_json(by_alias=True, exclude_unset=True)


# --- Input Schemas ---


class AskQuestionInput(BaseModel):
    space_id: str = Field(..., description="The ID of the Genie space.")
    content: str = Field(..., description="The text to ask the Genie space.")



def _ask_question(client, args) -> list[TextContent]:
    model = AskQuestionInput.model_validate(args)
    result = Genie(model.space_id).ask_question(model.content)
    return [
        TextContent(
            type="text",
            text=result,
        )
    ]


def _create_message(client, args) -> list[TextContent]:
    model = CreateMessageInput.model_validate(args)
    message = client.genie.create_message_and_wait(
        model.space_id, model.conversation_id, model.content
    )
    return [
        TextContent(
            type="text",
            text=dump_json(
                {
                    "message_id": message.message_id,
                    "content": message.content,
                    "status": message.status.value if message.status else None,
                    "attachments": getattr(message, "attachments", None),
                    "conversation_id": message.conversation_id,
                }
            ),
        )
    ]


def _get_message(client, args) -> list[TextContent]:
    model = GetMessageInput.model_validate(args)
    message = client.genie.get_message(
        model.space_id, model.conversation_id, model.message_id
    )
    return [
        TextContent(
            type="text",
            text=dump_json(
                {
                    "message_id": message.message_id,
                    "content": message.content,
                    "status": message.status.value if message.status else None,
                    "conversation_id": message.conversation_id,
                    "space_id": model.space_id,
                    "attachments": getattr(message, "attachments", None),
                    "error": getattr(message, "error", None),
                }
            ),
        )
    ]


def _get_attachment_query_result(client, args) -> list[TextContent]:
    model = GetAttachmentQueryResultInput.model_validate(args)
    result = client.genie.get_message_attachment_query_result(
        model.space_id, model.conversation_id, model.message_id, model.attachment_id
    )
    return [
        TextContent(
            type="text",
            text=dump_json(
                result.statement_response.as_dict()
                if result.statement_response
                else {"error": "No statement response found."}
            ),
        )
    ]


def _execute_attachment_query(client, args) -> list[TextContent]:
    model = ExecuteAttachmentQueryInput.model_validate(args)
    result = client.genie.execute_message_attachment_query(
        model.space_id, model.conversation_id, model.message_id, model.attachment_id
    )
    return [
        TextContent(
            type="text",
            text=dump_json(
                result.statement_response.as_dict()
                if result.statement_response
                else {"error": "No statement response found."}
            ),
        )
    ]


def _get_space(client, args) -> list[TextContent]:
    model = GetSpaceInput.model_validate(args)
    space = client.genie.get_space(model.space_id)
    return [
        TextContent(
            type="text",
            text=dump_json(
                {
                    "space_id": model.space_id,
                    "title": space.title,
                    "description": getattr(space, "description", None),
                }
            ),
        )
    ]


def _generate_download_query_result(client, args) -> list[TextContent]:
    model = GenerateDownloadInput.model_validate(args)
    result = client.genie.generate_download_full_query_result(
        model.space_id, model.conversation_id, model.message_id, model.attachment_id
    )
    return [
        TextContent(
            type="text",
            text=dump_json(
                {
                    "transient_statement_id": result.transient_statement_id,
                    "status": result.status.value if result.status else None,
                }
            ),
        )
    ]


def _poll_message_until_complete(client, args) -> list[TextContent]:
    model = PollMessageUntilCompleteInput.model_validate(args)
    genie_api = client.genie
    start_time = time.time()
    elapsed = 0
    poll_count = 0

    while elapsed < model.timeout_seconds:
        message = genie_api.get_message(
            model.space_id, model.conversation_id, model.message_id
        )
        status = message.status.value if message.status else "UNKNOWN"
        poll_count += 1

        if status in ["COMPLETED", "FAILED", "QUERY_RESULT_EXPIRED", "CANCELLED"]:
            return [
                TextContent(
                    type="text",
                    text=dump_json(
                        {
                            "message_id": message.message_id,
                            "status": status,
                            "poll_count": poll_count,
                            "elapsed_time": elapsed,
                        }
                    ),
                )
            ]

        time.sleep(model.poll_interval_seconds)
        elapsed = time.time() - start_time

    return [
        TextContent(
            type="text",
            text=dump_json(
                {
                    "error": f"Timeout after {elapsed} seconds",
                    "message_id": model.message_id,
                    "status": status,
                    "poll_count": poll_count,
                    "elapsed_time": elapsed,
                }
            ),
        )
    ]


def _list_spaces(client, args, space_ids) -> list[TextContent]:
    results = []
    for space_id in space_ids:
        try:
            space = client.genie.get_space(space_id)
            results.append(
                {
                    "space_id": space_id,
                    "title": space.title,
                    "description": getattr(space, "description", None),
                }
            )
        except Exception as e:
            results.append({"space_id": space_id, "error": str(e)})
    return [TextContent(type="text", text=dump_json(results))]


# --- Tool Registry ---


class GenieTool(BaseTool):

    def __init__(self, name, description, input_schema, func):
        self.func = func
        tool_spec = ToolSpec(
            name=name,
            description=description,
            inputSchema=input_schema,
        )
        super().__init__(tool_spec)

    def execute(self, **kwargs):
        return self.func(client=WorkspaceClient(), args=kwargs)


def list_genie_tools(settings) -> list[GenieTool]:
    return [
        GenieTool(
            name="genie_ask_question",
            description="Start a new conversation in a Genie space.",
            input_schema=AskQuestionInput.model_json_schema(),
            func=_ask_question,
        )
    ]
