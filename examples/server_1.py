import argparse
from mcp.server.mcpserver import MCPServer


def build(name: str) -> MCPServer:
    mcp = MCPServer(name)

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @mcp.tool()
    def echo(text: str) -> str:
        """Echo text back, tagged with this server's name."""
        return f"{name}: {text}"

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
    parser.add_argument("--name", default="server_1")
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()
    uvicorn.run(build(args.name).streamable_http_app(), host="127.0.0.1", port=args.port)
