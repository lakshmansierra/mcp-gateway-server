"""AI agent (GPT-4.1 via SAP Gen AI Hub) that uses MCP tools through the gateway.

The agent never knows where the MCP servers are. It connects to the gateway with
SERVER_2_KEY, a key the gateway accepts for server_2 only, so the model only sees
and calls server_2's tools.

    python examples/client_2/client.py
"""

import json
import os
import asyncio
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.load import dumps as lc_dumps
from langchain_core.tools import StructuredTool
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from _prompt.agentic_math_func_prompt import HUMAN_AGENTIC_PROMPT
from _util.file_ops import write_json
from _llm.models_llm import agentic_transformer_func_llm

load_dotenv()
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080/mcp")
GATEWAY_API_KEY = os.getenv("SERVER_2_KEY")


def connect_gateway() -> Client:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {GATEWAY_API_KEY}"})
    return Client(streamable_http_client(GATEWAY_URL, http_client=http_client))


async def load_gateway_tools(client: Client) -> list[StructuredTool]:
    """Turn every tool the gateway offers this key into a LangChain tool that calls back through the gateway."""

    def as_langchain_tool(mcp_tool) -> StructuredTool:
        async def call(**arguments: Any) -> str:
            result = await client.call_tool(mcp_tool.name, arguments)
            text = "\n".join(getattr(c, "text", str(c)) for c in result.content)
            return f"Error: {text}" if result.is_error else text

        return StructuredTool.from_function(
            coroutine=call,
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            args_schema=mcp_tool.input_schema,
        )

    return [as_langchain_tool(t) for t in (await client.list_tools()).tools]


async def agentic_math_func(num_1: int, num_2: int) -> Any:
    try:
        prompt = {
            "instructions": HUMAN_AGENTIC_PROMPT.format(num_1, num_2)
        }

        async with connect_gateway() as client:
            tools = await load_gateway_tools(client)
            print("---> tools from gateway:", [t.name for t in tools])

            agent = create_agent(
                model=agentic_transformer_func_llm,
                tools=tools,
            )
            response = await agent.ainvoke({
                "messages": [
                    HumanMessage(content=json.dumps(prompt, indent=2))
                ]
            })

        for message in response["messages"]:
            for call in getattr(message, "tool_calls", []) or []:
                print(f"---> model called {call['name']}({call['args']})")
        print("---> final answer:", response["messages"][-1].content)

        write_json(json_value=str(response), json_file_name="agentic_math_func_response.json")

        lc_response = lc_dumps(response)
        write_json(json_value=json.loads(lc_response), json_file_name="agentic_math_func_lc_response.json")
        write_json(json_value={"metadata": lc_response}, json_file_name="metadata_response.json")
        parsed = "success"

    except Exception as e:
        while isinstance(e, BaseExceptionGroup):
            e = e.exceptions[0]
        parsed = f"error: {e}"

    finally:
        return parsed


print(asyncio.run(agentic_math_func(1, 3)))
