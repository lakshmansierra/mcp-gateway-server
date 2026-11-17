"""Start the MCP gateway: `python main.py [--env-file .env] [--transport http|stdio]`.

Run it from inside this folder (`cd mcp_gateway && python main.py`) or from the project root
(`python mcp_gateway/main.py`). Settings come from mcp_gateway/.env.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
# Run as a file, Python puts this folder on the import path. Drop it (so the config/, auth/, ... folders here can't
# shadow other libraries' modules with the same names) and add the parent, so `mcp_gateway.*` imports work.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != GATEWAY_DIR]
sys.path.insert(0, str(GATEWAY_DIR.parent))

import anyio  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from mcp_gateway.config.settings import load_config  # noqa: E402


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
        help="http: serve Streamable HTTP for remote AI clients; stdio: run as a local subprocess server "
        "(default: GATEWAY_TRANSPORT from .env, else http)",
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
    if args.transport:
        config.gateway.transport = args.transport

    # Logs go to stderr so they never corrupt the stdio protocol stream.
    logging.basicConfig(
        level=config.gateway.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Per-request HTTP logs from the upstream client would repeat on every health check.
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    if config.gateway.transport == "stdio":
        from mcp.server.stdio import stdio_server

        from mcp_gateway.server.gateway import Gateway, build_server

        server = build_server(Gateway(config))

        async def run_stdio() -> None:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, server.create_initialization_options())

        anyio.run(run_stdio)
        return

    import uvicorn

    from mcp_gateway.web.app import create_app

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
