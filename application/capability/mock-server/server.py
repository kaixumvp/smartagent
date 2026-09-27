"""本地 Mock MCP Server（streamable HTTP），用于测试 v0.2.0 的 Provider Sync。

启动（复用 backend venv 里的 mcp）：
    backend/.venv/Scripts/python mock-server/server.py

Endpoint: http://localhost:9000/mcp
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-tools", host="0.0.0.0", port=9000, streamable_http_path="/mcp")


@mcp.tool()
def echo(text: str) -> str:
    """回显输入字符串"""
    return text


@mcp.tool()
def add(a: float, b: float) -> float:
    """两个数字相加"""
    return a + b


@mcp.tool()
def get_weather(city: str) -> str:
    """查询城市天气（模拟）"""
    return f"{city}: 晴 25°C"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
