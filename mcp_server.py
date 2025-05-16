from typing import Any, Dict, List
import os
import time
import json
import requests
from requests.adapters import HTTPAdapter, Retry
from mcp.server.fastmcp import FastMCP
import re

# Initialize FastMCP server
mcp = FastMCP("jupiterone")

# Constants
JUPITERONE_API_KEY = os.getenv("JUPITERONE_API_KEY")
JUPITERONE_ACCOUNT_ID = os.getenv("JUPITERONE_ACCOUNT_ID")
JUPITERONE_REGION = os.getenv("JUPITERONE_REGION", "us")
JUPITERONE_API_URL = f"https://graphql.{JUPITERONE_REGION}.jupiterone.io"

# Create a session with retry logic
def create_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 502, 503, 504],
        allowed_methods=["POST", "GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def make_jupiterone_query(query: str) -> Dict[str, Any]:
    """Make a query against JupiterOne using direct HTTP requests."""
    response = {
        "query": query,
        "success": False,
        "results": [],
        "metadata": {
            "timestamp": time.time(),
            "count": 0
        }
    }
    
    try:
        session = create_session()
        headers = {
            "Authorization": f"Bearer {JUPITERONE_API_KEY}",
            "JupiterOne-Account": JUPITERONE_ACCOUNT_ID,
            "Content-Type": "application/json",
        }
        
        all_query_results = []
        current_cursor = None
        
        # Check if the query has a LIMIT clause
        has_limit = bool(re.search(r'\bLIMIT\s+\d+\b', query, re.IGNORECASE))
        
        while True:
            # Prepare query payload following the exact structure from client.py
            query_gql = """
            query QueryV1($query: String!, $cursor: String, $deferredResponse: DeferredResponseOption) {
              queryV1(query: $query, cursor: $cursor, deferredResponse: $deferredResponse) {
                url
              }
            }
            """
            
            variables = {
                "query": query,
                "deferredResponse": "FORCE",
                "cursor": current_cursor
            }
            
            payload = {
                "query": query_gql,
                "variables": variables,
                "flags": {"variableResultSize": True}
            }
            
            # Get the download URL
            url_response = session.post(
                JUPITERONE_API_URL,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            # Handle HTTP errors
            if url_response.status_code != 200:
                if url_response.status_code == 401:
                    response["error"] = "401: Unauthorized. Please supply a valid account id and API token."
                elif url_response.status_code in [429, 503]:
                    response["error"] = "Rate limit exceeded. Please try again later."
                elif url_response.status_code == 504:
                    response["error"] = "Gateway Timeout."
                elif url_response.status_code == 500:
                    response["error"] = "JupiterOne API internal server error."
                else:
                    response["error"] = f"HTTP Error {url_response.status_code}: {url_response.text}"
                return response
            
            # Handle GraphQL errors
            response_json = url_response.json()
            if "errors" in response_json:
                errors = response_json["errors"]
                error_messages = []
                
                for error in errors:
                    error_message = error.get("message", "Unknown error")
                    
                    # Special handling for J1QL parsing errors
                    if "Error parsing query" in error_message:
                        # Extract useful information from parsing error
                        error_data = {
                            "type": "J1QL_PARSING_ERROR",
                            "message": "Error parsing J1QL query"
                        }
                        
                        # Extract line and column info if available
                        line_col_match = re.search(r"at line (\d+) column (\d+)", error_message)
                        if line_col_match:
                            error_data["line"] = int(line_col_match.group(1))
                            error_data["column"] = int(line_col_match.group(2))
                        
                        # Extract the unexpected token
                        token_match = re.search(r"Unexpected token \"([^\"]+)\"", error_message)
                        if token_match:
                            error_data["unexpected_token"] = token_match.group(1)
                        
                        # Extract the query line with the error
                        query_line_match = re.search(r"\n> \d+ \| (.+)\n", error_message)
                        if query_line_match:
                            error_data["query_line"] = query_line_match.group(1)
                            
                            # Add pointer to the error position
                            pointer_match = re.search(r"\n    \| (\^+)", error_message)
                            if pointer_match:
                                error_data["pointer"] = pointer_match.group(1)
                        
                        # Add common syntax suggestions based on token type
                        if token_match:
                            token = token_match.group(1)
                            if token == "=":
                                error_data["suggestion"] = "In J1QL, property filtering should use 'WITH' clause instead of 'WHERE' for entity properties"
                            elif token == "\"":
                                error_data["suggestion"] = "J1QL requires single quotes (') for string values, not double quotes (\")"
                            elif token == "WHRE" or token == "WEHRE" or token == "WHER":
                                error_data["suggestion"] = "Did you mean 'WHERE'?"
                            elif token == "WIH" or token == "WIT" or token == "WIHT":
                                error_data["suggestion"] = "Did you mean 'WITH'?"
                            # Incorrect order of WITH and AS
                            elif token == "WITH" and "AS" in query and query.find("AS") < query.find("WITH"):
                                error_data["suggestion"] = "In J1QL, 'WITH' must come before 'AS'"
                        
                        response["error"] = error_data
                        return response
                    
                    error_messages.append(error_message)
                
                response["error"] = f"GraphQL errors: {', '.join(error_messages)}"
                return response
            
            # Extract download URL and fetch results
            try:
                download_url = response_json['data']['queryV1']['url']
                
                # Poll the download URL until results are ready
                while True:
                    download_response = session.get(download_url, timeout=60)
                    if download_response.status_code != 200:
                        response["error"] = f"Failed to fetch query results: {download_response.status_code}"
                        return response
                    
                    download_data = download_response.json()
                    status = download_data.get('status')
                    
                    if status != 'IN_PROGRESS':
                        break
                    
                    time.sleep(0.2)  # Sleep 200 milliseconds between checks
                
                # Add results to the collection
                if 'data' in download_data:
                    # Process the results for easier consumption by LLMs
                    processed_results = []
                    for item in download_data['data']:
                        # For entity results with nested structures, flatten important properties
                        if 'entity' in item and 'properties' in item:
                            # Create a processed version with common properties at the top level
                            processed_item = {
                                "id": item.get("id"),
                                "type": item["entity"].get("_type"),
                                "class": item["entity"].get("_class", []),
                                "name": item["entity"].get("displayName"),
                                "integrationName": item["entity"].get("_integrationName"),
                                "properties": item["properties"]
                            }
                            processed_results.append(processed_item)
                        else:
                            # For other result types (aggregations, property values, etc.)
                            processed_results.append(item)
                    
                    all_query_results.extend(processed_results)
                    
                    # Update metadata with information about pagination
                    if 'cursor' in download_data:
                        response["metadata"]["has_more"] = True
                    else:
                        response["metadata"]["has_more"] = False
                        
                else:
                    # If there's no data but no error, it might be an empty result
                    if download_data.get('error'):
                        response["error"] = f"Query error: {download_data.get('error')}"
                        return response
                
                # If query has a LIMIT clause, we only need the first page
                # since variableResultSize should return up to the limit in one page
                if has_limit:
                    break
                
                # Otherwise check for more pages
                if 'cursor' in download_data and download_data['cursor']:
                    current_cursor = download_data['cursor']
                else:
                    break
                    
            except (KeyError, json.JSONDecodeError) as e:
                response["error"] = f"Failed to process query response: {str(e)}"
                return response
        
        # Update response with successful results
        response["success"] = True
        response["results"] = all_query_results
        response["metadata"]["count"] = len(all_query_results)
        return response
        
    except requests.RequestException as e:
        response["error"] = f"Request failed: {str(e)}"
        return response
    except Exception as e:
        response["error"] = f"Unexpected error: {str(e)}"
        return response

@mcp.tool()
async def run_j1_query(query: str) -> Any:
    """Run a query against JupiterOne.

    Args:
        query: The query to run against JupiterOne.
    """
    result = make_jupiterone_query(query)
    return result

@mcp.prompt()
def j1ql_guide() -> str:
    """JupiterOne Query Language (J1QL) Guide for creating valid queries.
    
    This prompt provides comprehensive guidelines for constructing J1QL queries.
    """
    return """
### JupiterOne Query Language (J1QL) Guide

> **CRITICAL:** Follow this guide strictly. Any deviation may result in query failure. Do not use operators not documented here.

#### Core Concepts

**Entity and Relationship Structure**
- **Entities**: Assets in your environment with specific classes and types
  - **Entity Class**: Always `TitleCase` (e.g., `User`, `Host`, `Application`)
  - **Entity Type**: Always `snake_case` (e.g., `aws_iam_user`, `github_user`)
- **Relationships**: Connections between entities
  - **Relationship Class**: Always `ALLCAPS` (e.g., `HAS`, `USES`, `PROTECTS`)
- **Default Returns**: Queries return the first entity after FIND unless explicitly modified with RETURN

#### MANDATORY Query Structure

```
FIND <entity> [WITH <property_filter>] [AS <alias>]
  [THAT <relationship> [<direction>] <entity> [WITH <property_filter>] [AS <alias>]]
  [WHERE <condition>]
  [RETURN <field_selection>]
  [ORDER BY <field>]
  [SKIP <number>]
  [LIMIT <number>]
```

#### ⚠️ CRITICAL SYNTAX RULES ⚠️ ALL QUERIES MUST ADHERE TO THESE RULES

1. **Alias Placement**: Aliases MUST follow the WITH statement when filtering
   ✅ `FIND Device WITH name~='TEST' AS dev`
   ❌ `FIND Device AS dev WITH name~='TEST'`

2. **String Values**: ALWAYS use single quotes for strings, NEVER double quotes
   ✅ `name ~= 'john'`
   ❌ `name ~= "john"`

3. **WITH vs WHERE**: Use WITH for entity properties, WHERE only for relationship properties or cross-entity comparisons
   ✅ `FIND User WITH active = true`
   ✅ `FIND User AS u THAT HAS Device AS d WHERE u.active = true AND d.platform = 'darwin'`
   ❌ `FIND User WHERE active = true`

4. **LIMIT Usage**: ALWAYS include LIMIT (5-100) or use COUNT for discovery
   ✅ `FIND User LIMIT 50`
   ✅ `FIND User AS u RETURN u._type, count(u)`
   ❌ `FIND User` (no limit specified)

5. **Relationship Direction**: Direction arrows MUST follow the relationship verb
   ✅ `FIND User THAT HAS >> Device`
   ❌ `FIND User THAT >> HAS Device`

6. **Optional Traversals**: Use parentheses and question mark
   ✅ `FIND User AS u (THAT IS Person AS p)?`
   ❌ `FIND User AS u THAT IS? Person AS p`

7. **Using Aggregates For Discovery**: Alias COUNT and use ORDER BY
   ✅ `FIND * AS ent RETURN ent._class, COUNT(ent) AS cnt ORDER BY cnt DESC LIMIT 50`
   ❌ `FIND * AS ent RETURN ent._class, COUNT(ent) LIMIT 50`

#### Entity Selection

**Finding by class or type**:
```j1ql
FIND User LIMIT 10                 # Find entities with _class = 'User'
FIND aws_iam_user LIMIT 10         # Find entities with _type = 'aws_iam_user'
FIND * WITH _type='aws_instance' LIMIT 10  # Filter any entity by type
```

**Finding multiple entity types**:
```j1ql
FIND (User | Host) LIMIT 10        # Find entities with _class = 'User' OR _class = 'Host'
```

#### Property Filtering (WITH)

**Basic property filtering**:
```j1ql
FIND User WITH active = true LIMIT 10
FIND DataStore WITH encrypted = false LIMIT 10
```

**WITH filtering with alias** (CORRECT ORDER):
```j1ql
FIND User WITH active = true AS u LIMIT 10
FIND DataStore WITH encrypted = false AS ds LIMIT 10
```

**WITH filtering with alias AND Advanced filtering** (CORRECT ORDER):
```j1ql
FIND User WITH accountCount > 0 AS u RETURN u.displayName
FIND DataStore WITH name~='ROOT' OR name=/iam/i AS ds RETURN ds.name, ds.encrypted LIMIT 10
```

#### String Comparisons

J1QL comparison operators:
- `=` : equals (exact match)
- `!=` : not equals
- `~=` : contains
- `^=` : starts with
- `$=` : ends with
- `!~=` : does not contain
- `!^=` : does not start with
- `!$=` : does not end with

```j1ql
FIND User WITH username ~= 'john' LIMIT 10
FIND Host WITH name ^= 'web' LIMIT 10
```

#### Case-Insensitive Matching (Regex)

```j1ql
FIND User WITH username=/john/ LIMIT 10  # Case-insensitive match
```

#### Traversing Relationships (THAT)

**Important: Don't assume relationship VERBS, either do discovery to determine the correct relationship or use the wild card relationship "THAT RELATES TO"**

**Any relationship traversal (i.e. wildcard)**:
```j1ql
FIND User THAT RELATES TO Application LIMIT 10
```

**Basic traversal**:
```j1ql
FIND User THAT HAS Device LIMIT 10
```

#### Discovery Techniques (ALWAYS USE THESE FIRST)

FIRST:
**Identify entity classes and counts**:
```j1ql
FIND * AS ent RETURN ent._class, COUNT(ent) AS cnt ORDER BY cnt DESC LIMIT 50
```

SECOND:
**Discover properties on an entity**:
```j1ql
FIND User AS ent RETURN ent.* LIMIT 100
```

THIRD:
**Find how entities are related**:
```j1ql
FIND User THAT RELATES TO AS rel * AS ent RETURN rel._class, ent._type, COUNT(ent) AS cnt ORDER BY cnt DESC LIMIT 50
```

#### Example Queries

```j1ql
# Find all active users
FIND User WITH active=true LIMIT 50

# Find devices with a specific operating system
FIND Device WITH platform='darwin' LIMIT 50

# Find users that have devices
FIND User THAT HAS Device LIMIT 50

# Get counts of entity types
FIND * AS ent RETURN ent._type, COUNT(ent) AS cnt ORDER BY cnt DESC LIMIT 50
```
"""

if __name__ == "__main__":
    mcp.run(transport='stdio')
