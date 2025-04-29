from typing import Any
import os
from mcp.server.fastmcp import FastMCP
from jupiterone import JupiterOneClient

# Initialize FastMCP server
mcp = FastMCP("jupiterone")

# Constants
JUPITERONE_API_KEY = os.getenv("JUPITERONE_API_KEY")
JUPITERONE_ACCOUNT_ID = os.getenv("JUPITERONE_ACCOUNT_ID")
JUPITERONE_REGION = os.getenv("JUPITERONE_REGION")

# Create a single client instance
j1_client = JupiterOneClient(
    account=JUPITERONE_ACCOUNT_ID,
    token=JUPITERONE_API_KEY,
    url=f"https://graphql.{JUPITERONE_REGION}.jupiterone.io"
)

def make_jupiterone_query(query: str) -> dict[str, Any] | None:
    """Make a query against JupiterOne."""
    try:
        response = j1_client.query_v1(query)
        return response
    except Exception as e:
        return e

@mcp.tool()
async def run_j1_query(query: str) -> str:
    """Run a query against JupiterOne.

    Args:
        query: The query to run against JupiterOne.
    """
    try:
        data = make_jupiterone_query(query)
        return data
    except Exception as e:
        return e

if __name__ == "__main__":
    mcp.run(transport='stdio')
