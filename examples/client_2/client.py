import json, os
import asyncio
from typing import Any
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from langchain.schema import HumanMessage
from langchain_core.load import dumps as lc_dumps
from _prompt.agentic_math_func_prompt import HUMAN_AGENTIC_PROMPT
from _util.file_ops import write_json
from _llm.models_llm import agentic_transformer_func_llm
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from langchain_mcp_adapters.tools import load_mcp_tools

load_dotenv()
MCP_URL = os.getenv("MCP_URL")

async def agentic_math_func(num_1: int, num_2: int) -> Any:
    try:
        prompt = {
            "instructions": HUMAN_AGENTIC_PROMPT.format(num_1, num_2)
        }

        async with streamablehttp_client(
                                            url=MCP_URL,
                                            timeout=300,           # connect/write timeout
                                            sse_read_timeout=3600  # allow 1 hour between SSE messages
                                        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()

                # Get tools
                tools = await load_mcp_tools(session)
                print("--->", type(session))
                print("--->", session)
                print("--->", type(tools))
                print("--->", tools)
                
                agent = create_react_agent(
                    model=agentic_transformer_func_llm,
                    tools=tools,
                )
                response = await agent.ainvoke({
                "messages": [
                    HumanMessage(content=json.dumps(prompt, indent=2))
                    ]
                })

        write_json(json_value = str(response), json_file_name = "agentic_math_func_response.json")
        print(type(response))
        print(response)
        
        #################################
        lc_response = lc_dumps(response)
        write_json(json_value = json.loads(lc_response), json_file_name = "agentic_math_func_lc_response.json")
        print(type(lc_response))
        print(lc_response)

        write_json(json_value = {"metadata": lc_response}, json_file_name = "metadata_response.json")
        parsed = "success"

    except Exception as e:
        parsed = f"error: {e}"
        
    finally:
        return parsed
    
print(asyncio.run(agentic_math_func(1,3)))