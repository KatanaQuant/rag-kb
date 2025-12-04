"""MCP (Model Context Protocol) HTTP transport endpoint.

Implements Streamable HTTP transport for network-accessible MCP server.
Spec: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

Features:
- JSON-RPC 2.0 protocol over HTTP
- SSE (Server-Sent Events) for streaming responses
- No authentication (local network only)
- Same tools as stdio MCP server (query_knowledge_base, list_indexed_documents, get_kb_stats)

Usage:
- POST /mcp - Send JSON-RPC requests (returns JSON or SSE stream)
- Clients must include Accept header with application/json and text/event-stream
"""

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, AsyncGenerator
from enum import Enum
import json
import asyncio

from routes.deps import get_app_state
from operations.query_executor import QueryExecutor
from operations.document_lister import DocumentLister
from config import default_config

router = APIRouter()


# JSON-RPC 2.0 Models
class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0", pattern="^2\\.0$")
    id: Optional[int | str] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[int | str] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


# MCP Protocol Types
class ToolParameter(BaseModel):
    type: str
    description: str
    default: Optional[Any] = None


class Tool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


class ToolListResult(BaseModel):
    tools: List[Tool]


class ToolCallResult(BaseModel):
    content: List[Dict[str, str]]
    isError: bool = False


# MCP Tools Registry
TOOLS = [
    Tool(
        name="query_kb",
        description=(
            "**CHECK THIS FIRST** for technical questions, APIs, frameworks, algorithms, or domain-specific knowledge."
            "Search your personal knowledge base (books, notes, documentation) for relevant information. "
            "This is your PRIMARY source - always use it BEFORE relying on general knowledge. "
            "Returns the most semantically similar content chunks ranked by relevance. "
            "If no relevant chunks found (score < 0.3), then use general knowledge."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or question to find relevant information for",
                },
                "top_k": {
                    "type": "number",
                    "description": "Number of results to return (default: 5, max: 20)",
                    "default": 5,
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity score (0-1). Only return results above this threshold.",
                    "default": 0.0,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_indexed_documents",
        description=(
            "List all documents currently indexed in the knowledge base. "
            "Shows filenames, when they were indexed, and how many chunks each contains. "
            "Useful to see what knowledge is available."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_kb_stats",
        description=(
            "Get statistics about the knowledge base: total documents, total chunks, and embedding model used. "
            "Useful for understanding the current state of the knowledge base."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def handle_list_tools() -> ToolListResult:
    """Handle tools/list JSON-RPC method."""
    return ToolListResult(tools=TOOLS)


async def handle_call_tool(name: str, arguments: Dict[str, Any], request: Request) -> ToolCallResult:
    """Handle tools/call JSON-RPC method."""
    app_state = get_app_state(request)

    try:
        if name == "query_kb":
            query = arguments.get("query")
            if not query:
                return ToolCallResult(
                    content=[{"type": "text", "text": "Error: Query parameter is required"}],
                    isError=True,
                )

            top_k = min(arguments.get("top_k", 5), 20)
            threshold = arguments.get("threshold", 0.0)

            # Execute query using existing QueryExecutor
            from models import QueryRequest
            query_request = QueryRequest(text=query, top_k=top_k, threshold=threshold if threshold > 0 else None)
            executor = QueryExecutor(
                app_state.get_model(),
                app_state.get_async_vector_store(),
                app_state.get_query_cache(),
            )
            response = await executor.execute(query_request)

            # Format results
            result = f'Found {response.total_results} relevant chunks for: "{query}"\n\n'
            for idx, item in enumerate(response.results):
                result += f"## Result {idx + 1} (Score: {item.score:.3f})\n"
                result += f"**Source:** {item.source}"
                if item.page:
                    result += f" (Page {item.page})"
                result += f"\n\n{item.content}\n\n---\n\n"

            if response.total_results == 0:
                result = (
                    f'No relevant information found for: "{query}"\n\n'
                    "Try:\n- Rephrasing your query\n- Using different keywords\n- Checking if relevant documents are indexed"
                )

            return ToolCallResult(content=[{"type": "text", "text": result}])

        elif name == "list_indexed_documents":
            lister = DocumentLister(app_state.get_async_vector_store())
            response = await lister.list_all()

            result = f"# Indexed Documents ({response['total_documents']} total)\n\n"
            if response['total_documents'] == 0:
                result += "No documents indexed yet. Add files to the knowledge_base/ directory.\n"
            else:
                for doc in response['documents']:
                    filename = doc['file_path'].split("/")[-1]
                    result += f"- **{filename}**\n"
                    result += f"  - Indexed: {doc['indexed_at']}\n"
                    result += f"  - Chunks: {doc['chunk_count']}\n\n"

            return ToolCallResult(content=[{"type": "text", "text": result}])

        elif name == "get_kb_stats":
            stats = await app_state.get_vector_store_stats()
            model_name = default_config.model.name

            result = f"""# Knowledge Base Statistics

**Status:** healthy
**Indexed Documents:** {stats['indexed_documents']}
**Total Chunks:** {stats['total_chunks']}
**Embedding Model:** {model_name}

The knowledge base is ready for queries.
"""
            return ToolCallResult(content=[{"type": "text", "text": result}])

        else:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Error: Unknown tool: {name}"}],
                isError=True,
            )

    except Exception as e:
        return ToolCallResult(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True,
        )


async def handle_initialize(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Handle initialize JSON-RPC method."""
    return {
        "protocolVersion": "2024-11-05",  # Using stable version
        "capabilities": {
            "tools": {},  # We support tools
        },
        "serverInfo": {
            "name": "rag-kb-http",
            "version": "1.0.0",
        },
    }


async def handle_jsonrpc_request(rpc_request: JsonRpcRequest, request: Request) -> JsonRpcResponse:
    """Handle a single JSON-RPC request."""
    method = rpc_request.method
    params = rpc_request.params or {}

    try:
        if method == "initialize":
            result = await handle_initialize(params)
        elif method == "tools/list":
            result = (await handle_list_tools()).model_dump()
        elif method == "tools/call":
            tool_result = await handle_call_tool(
                params.get("name", ""),
                params.get("arguments", {}),
                request,
            )
            result = tool_result.model_dump()
        else:
            return JsonRpcResponse(
                id=rpc_request.id,
                error=JsonRpcError(
                    code=-32601,
                    message=f"Method not found: {method}",
                ),
            )

        return JsonRpcResponse(id=rpc_request.id, result=result)

    except Exception as e:
        return JsonRpcResponse(
            id=rpc_request.id,
            error=JsonRpcError(
                code=-32603,
                message=f"Internal error: {str(e)}",
            ),
        )


async def sse_generator(rpc_response: JsonRpcResponse) -> AsyncGenerator[str, None]:
    """Generate SSE events for streaming response."""
    # SSE format: "data: {json}\n\n"
    # Per JSON-RPC 2.0 spec: success responses must NOT include error field
    response_dict = rpc_response.model_dump(exclude_none=True)
    if "result" in response_dict and "error" in response_dict:
        del response_dict["error"]
    data = json.dumps(response_dict)
    yield f"data: {data}\n\n"


@router.post("/mcp")
async def mcp_endpoint(request: Request):
    """
    MCP Streamable HTTP endpoint.

    Accepts JSON-RPC 2.0 requests and returns either:
    - application/json for single responses
    - text/event-stream for SSE streaming

    Supported methods:
    - initialize: Initialize MCP session
    - tools/list: List available tools
    - tools/call: Call a tool
    """
    # Parse Accept header
    accept_header = request.headers.get("accept", "application/json")
    supports_sse = "text/event-stream" in accept_header

    # Parse JSON-RPC request
    try:
        body = await request.json()
        rpc_request = JsonRpcRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}",
                },
            },
        )

    # Handle request
    rpc_response = await handle_jsonrpc_request(rpc_request, request)

    # Return response based on client capabilities
    if supports_sse and rpc_request.method in ["tools/call"]:
        # Stream response via SSE for tool calls
        return StreamingResponse(
            sse_generator(rpc_response),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Return JSON for initialize, tools/list, or if client doesn't support SSE
        # Per JSON-RPC 2.0 spec: success responses must NOT include error field
        response_dict = rpc_response.model_dump(exclude_none=True)
        if "result" in response_dict and "error" in response_dict:
            del response_dict["error"]
        return JSONResponse(content=response_dict)


@router.get("/mcp")
async def mcp_info():
    """
    Info endpoint for MCP HTTP server.

    Returns server capabilities and connection instructions.
    """
    return {
        "name": "rag-kb-http",
        "version": "1.0.0",
        "protocol": "MCP Streamable HTTP",
        "transport": "HTTP + SSE",
        "authentication": "none (local network only)",
        "tools": [tool.name for tool in TOOLS],
        "endpoint": "/mcp",
        "usage": {
            "POST": "Send JSON-RPC 2.0 requests",
            "Accept": "application/json, text/event-stream",
        },
    }
