"""An MCP client that talks only to the gateway, never to the upstream servers directly.

    python examples/sample_client.py
    python examples/sample_client.py --url http://127.0.0.1:8080/mcp --key <api key>

The key defaults to GATEWAY_API_KEY, falling back to API_KEY_ADMIN from the project's .env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import anyio
from dotenv import load_dotenv
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


def connect(url: str, key: str) -> Client:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {key}"})
    return Client(streamable_http_client(url, http_client=http_client))


async def run(url: str, key: str) -> None:
    async with connect(url, key) as client:
        print(f"Connected to gateway: {url}\n")

        tools = (await client.list_tools()).tools
        print(f"Tools ({len(tools)}):")
        for tool in tools:
            print(f"  {tool.name:<28} {tool.description}")

        print("\nCalling tools through the gateway:")
        result = await client.call_tool("sample__add", {"a": 2, "b": 3})
        print(f"  sample__add(a=2, b=3)          -> {result.content[0].text}")
        result = await client.call_tool("sample__echo", {"text": "hello gateway"})
        print(f"  sample__echo('hello gateway')  -> {result.content[0].text}")

        resources = (await client.list_resources()).resources
        print(f"\nResources ({len(resources)}):")
        for resource in resources:
            contents = (await client.read_resource(str(resource.uri))).contents
            print(f"  {resource.uri} -> {contents[0].text}")

        templates = (await client.list_resource_templates()).resource_templates
        print(f"\nResource templates ({len(templates)}):")
        for template in templates:
            print(f"  {template.uri_template}")
        greeting = await client.read_resource("sample://greeting/Ada")
        print(f"  sample://greeting/Ada -> {greeting.contents[0].text}")

        prompts = (await client.list_prompts()).prompts
        print(f"\nPrompts ({len(prompts)}):")
        for prompt in prompts:
            print(f"  {prompt.name}")
        prompt = await client.get_prompt("sample__summarize", {"topic": "MCP gateways"})
        print(f"  sample__summarize(topic='MCP gateways') -> {prompt.messages[0].content.text}")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Call MCP tools through the gateway")
    parser.add_argument("--url", default=os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080/mcp"))
    parser.add_argument("--key", default=os.environ.get("GATEWAY_API_KEY") or os.environ.get("API_KEY_ADMIN"))
    args = parser.parse_args()
    if not args.key:
        parser.error("no API key: pass --key or set GATEWAY_API_KEY")
    try:
        anyio.run(run, args.url, args.key)
    except Exception as exc:  # noqa: BLE001 - connection errors arrive wrapped in ExceptionGroups
        sys.exit(f"Gateway request failed ({_root_cause(exc)}). Is the gateway running at {args.url}, and is the API key valid?")


def _root_cause(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup):
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


if __name__ == "__main__":
    main()
