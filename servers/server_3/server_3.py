import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root, so project imports work when run as a file

from mcp.server.mcpserver import Context, MCPServer

from servers._server_auth import client_of, protect, token_owner


def build(name: str) -> MCPServer:
    mcp = MCPServer(name)

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    @mcp.tool()
    def subtract(a: int, b: int) -> int:
        """Subtract b from a"""
        return a - b

    @mcp.tool()
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers"""
        return a * b
    
    @mcp.tool()
    def echo(text: str) -> str:
        """Echo text back, tagged with this server's name."""
        return f"{name}: {text}"

    @mcp.tool()
    def whoami(ctx: Context) -> str:
        """Which client the gateway is calling this server for."""
        return f"{name} is serving client '{client_of(ctx)}' (let in by the {token_owner(ctx)} token)"

    @mcp.tool()
    def delete_everything() -> str:
        """A dangerous tool, useful for testing exclude_tools."""
        return "deleted"

    @mcp.resource(f"{name}://info")
    def info() -> str:
        """Static info about this server."""
        return f"This is the '{name}' sample server."

    @mcp.resource(f"{name}://greeting/{{who}}")
    def greeting(who: str) -> str:
        """Templated resource."""
        return f"Hello {who} from {name}"

    @mcp.prompt()
    def summarize(topic: str) -> str:
        """Ask for a summary of a topic."""
        return f"Summarize {topic} in three bullet points."

    return mcp


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="server_3")
    parser.add_argument("--port", type=int, default=9003)
    parser.add_argument("--token", help="token callers must send; defaults to <NAME>_HEADER_AUTHORIZATION from .env")
    args = parser.parse_args()
    app = protect(build(args.name).streamable_http_app(), args.name, args.token)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
