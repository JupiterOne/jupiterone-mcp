# JupiterOne MCP Server

A Model Code Predictor (MCP) server for Cursor that integrates with JupiterOne.

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/JupiterOne/jupiterone-mcp.git
cd jupiterone-mcp
```

### 2. Create and Activate a Python Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate on macOS/Linux
source .venv/bin/activate

# Activate on Windows
# .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the MCP Server

Update the `.cursor/mcp.json` file with your JupiterOne credentials:

```json
{
  "mcpServers": {
    "jupiterone": {
      "command": "/ABSOLUTE/PATH/TO/jupiterone-mcp/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/jupiterone-mcp/mcp_server.py"],
      "env": {
        "JUPITERONE_API_KEY": "your-jupiterone-api-key",
        "JUPITERONE_ACCOUNT_ID": "your-jupiterone-account-id",
        "JUPITERONE_REGION": "us"
      }
    }
  }
}
```

Make sure to:
- Replace `/ABSOLUTE/PATH/TO/` with the actual full path to the repository
- Add your JupiterOne API key and account ID
- Set the correct region (default is "us")

### 5. Use the MCP Server in Your Projects

To use this MCP server in another project:

1. Copy the `.cursor` directory to your target project:
   ```bash
   cp -r /path/to/jupiterone-mcp/.cursor /path/to/your/project/
   ```

2. If you already have a `.cursor/mcp.json` file in your target project, merge the contents:
   ```json
   {
     "mcpServers": {
       "jupiterone": {
         "command": "/ABSOLUTE/PATH/TO/jupiterone-mcp/.venv/bin/python",
         "args": ["/ABSOLUTE/PATH/TO/jupiterone-mcp/mcp_server.py"],
         "env": {
           "JUPITERONE_API_KEY": "your-jupiterone-api-key",
           "JUPITERONE_ACCOUNT_ID": "your-jupiterone-account-id",
           "JUPITERONE_REGION": "us"
         }
       },
       // Keep any existing MCP servers here
     }
   }
   ```
You should get a prompt in the bottom left of cursor that a new MCP server has been discovered, and asking if you want to install it. Click yes.
## Usage

Once configured, you can use JupiterOne queries directly within Cursor through the MCP interface. The server provides the `run_j1_query` tool that accepts JupiterOne Query Language (J1QL) queries.

Example usage in Cursor:
```
You can now run JupiterOne queries by asking Cursor something like:
"Can you show me all my AWS accounts in JupiterOne?"
```

## Troubleshooting

- Ensure your virtual environment is activated when manually running the server
- Check that all paths in the `.cursor/mcp.json` file are absolute paths
- Verify your JupiterOne API key and account ID are correct
- Make sure the MCP server is running before using it in Cursor