import argparse

from mcp.server.mcpserver import Context, MCPServer
from starlette.applications import Starlette


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

    # @mcp.tool()
    # def multiply(a: int, b: int) -> int:
    #     """Multiply two numbers"""
    #     return a * b
    
    @mcp.tool()
    def echo(text: str) -> str:
        """Echo text back, tagged with this server's name."""
        return f"{name}: {text}"

    @mcp.tool()
    def whoami(ctx: Context) -> str:
        """Which client the gateway is calling this server for."""
        return f"{name} is serving client '{(ctx.headers or {}).get('x-mcp-client', 'unknown')}'"

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


def both_transports_app(mcp: MCPServer) -> Starlette:
    """One app serving both transports: /mcp (streamable_http) and /sse + /messages/ (sse)."""
    http_app = mcp.streamable_http_app()  # /mcp
    sse_app = mcp.sse_app()  # /sse (stream) and /messages/ (posts)
    return Starlette(
        routes=[*http_app.routes, *sse_app.routes],
        lifespan=http_app.router.lifespan_context,  # starts streamable_http's session manager
    )


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="server_5")
    parser.add_argument("--port", type=int, default=9005)
    args = parser.parse_args()
    print(f"[{args.name}] streamable_http: http://127.0.0.1:{args.port}/mcp   sse: http://127.0.0.1:{args.port}/sse")
    uvicorn.run(both_transports_app(build(args.name)), host="127.0.0.1", port=args.port)
