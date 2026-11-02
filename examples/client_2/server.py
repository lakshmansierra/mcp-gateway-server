from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="math-tools",
    host="0.0.0.0",
    port=3000,
    streamable_http_path="/mcp/math_tools"
)

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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
