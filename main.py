"""Start the MCP gateway: `python main.py [--env-file .env] [--transport http|stdio]`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import anyio
from dotenv import load_dotenv

from gateway.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcp-gateway", description="MCP gateway server")
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parent / ".env"),
        help="file of KEY=value settings; variables already set in the environment take precedence",
    )
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default="http",
        help="http: serve Streamable HTTP for remote AI clients; stdio: run as a local subprocess server",
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    load_dotenv(args.env_file)
    config = load_config()
    if args.host:
        config.gateway.host = args.host
    if args.port:
        config.gateway.port = args.port

    # Logs go to stderr so they never corrupt the stdio protocol stream.
    logging.basicConfig(
        level=config.gateway.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Per-request HTTP logs from the upstream client would repeat on every health check.
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server

        from gateway.server import Gateway, build_server

        server = build_server(Gateway(config))

        async def run_stdio() -> None:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, server.create_initialization_options())

        anyio.run(run_stdio)
        return

    import uvicorn

    from gateway.app import create_app

    if config.auth.enabled and not config.auth.api_keys:
        sys.exit("No API keys configured: set API_KEY_<NAME>=<secret> or GATEWAY_AUTH_ENABLED=false")

    uvicorn.run(
        create_app(config),
        host=config.gateway.host,
        port=config.gateway.port,
        log_level=config.gateway.log_level.lower(),
    )


if __name__ == "__main__":
    main()
