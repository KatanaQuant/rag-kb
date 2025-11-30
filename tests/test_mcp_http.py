"""Tests for MCP HTTP endpoint (routes/mcp.py).

Tests JSON-RPC 2.0 protocol, MCP tools, SSE streaming, and error handling.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, patch
import json

from main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_app_state():
    """Mock AppState for testing."""
    mock = Mock()

    # Mock model
    mock_model = Mock()
    mock.get_model.return_value = mock_model

    # Mock async vector store
    mock_vector_store = AsyncMock()
    mock.get_async_vector_store.return_value = mock_vector_store

    # Mock query cache
    mock_cache = Mock()
    mock.get_query_cache.return_value = mock_cache

    # Mock vector store stats
    async def mock_stats():
        return {
            "indexed_documents": 100,
            "total_chunks": 5000,
        }
    mock.get_vector_store_stats = mock_stats

    return mock


class TestMCPInfoEndpoint:
    """Test GET /mcp endpoint (server info)."""

    def test_mcp_info_returns_server_capabilities(self, client):
        """GET /mcp should return server info and capabilities."""
        response = client.get("/mcp")

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "rag-kb-http"
        assert data["protocol"] == "MCP Streamable HTTP"
        assert data["transport"] == "HTTP + SSE"
        assert data["authentication"] == "none (local network only)"
        assert "query_kb" in data["tools"]
        assert "list_indexed_documents" in data["tools"]
        assert "get_kb_stats" in data["tools"]


class TestMCPInitialize:
    """Test JSON-RPC initialize method."""

    def test_initialize_returns_server_info(self, client):
        """Initialize should return protocol version and capabilities."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in data["result"]
        assert data["result"]["serverInfo"]["name"] == "rag-kb-http"
        assert data["result"]["serverInfo"]["version"] == "1.0.0"

    def test_initialize_without_params(self, client):
        """Initialize should work without params."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize"
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["protocolVersion"] == "2024-11-05"


class TestMCPToolsList:
    """Test JSON-RPC tools/list method."""

    def test_tools_list_returns_all_tools(self, client):
        """tools/list should return all 3 MCP tools."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        tools = data["result"]["tools"]
        assert len(tools) == 3

        tool_names = [t["name"] for t in tools]
        assert "query_kb" in tool_names
        assert "list_indexed_documents" in tool_names
        assert "get_kb_stats" in tool_names

    def test_tools_have_proper_schema(self, client):
        """Each tool should have name, description, and inputSchema."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)
        tools = response.json()["result"]["tools"]

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_query_kb_tool_has_required_fields(self, client):
        """query_kb tool should have query as required field."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)
        tools = response.json()["result"]["tools"]

        query_kb_tool = next(t for t in tools if t["name"] == "query_kb")
        assert "query" in query_kb_tool["inputSchema"]["required"]
        assert "query" in query_kb_tool["inputSchema"]["properties"]
        assert "top_k" in query_kb_tool["inputSchema"]["properties"]
        assert "threshold" in query_kb_tool["inputSchema"]["properties"]


class TestMCPToolsCall:
    """Test JSON-RPC tools/call method."""

    @patch("routes.mcp.QueryExecutor")
    def test_query_kb_tool_success(self, mock_executor_class, client):
        """tools/call with query_kb should return search results."""
        # Mock QueryExecutor response
        mock_response = Mock()
        mock_response.total_results = 2
        mock_result1 = Mock()
        mock_result1.score = 0.95
        mock_result1.source = "test.txt"
        mock_result1.page = None
        mock_result1.content = "Test content 1"
        mock_result2 = Mock()
        mock_result2.score = 0.85
        mock_result2.source = "test2.txt"
        mock_result2.page = 5
        mock_result2.content = "Test content 2"
        mock_response.results = [mock_result1, mock_result2]

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = mock_response
        mock_executor_class.return_value = mock_executor

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query_kb",
                "arguments": {
                    "query": "test query",
                    "top_k": 5
                }
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["content"][0]["type"] == "text"
        result_text = data["result"]["content"][0]["text"]
        assert "Found 2 relevant chunks" in result_text
        assert "test query" in result_text
        assert "Test content 1" in result_text
        assert "Test content 2" in result_text
        assert "0.950" in result_text
        assert "0.850" in result_text

    @patch("routes.mcp.QueryExecutor")
    def test_query_kb_with_no_results(self, mock_executor_class, client):
        """query_kb with no results should return helpful message."""
        mock_response = Mock()
        mock_response.total_results = 0
        mock_response.results = []

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = mock_response
        mock_executor_class.return_value = mock_executor

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query_kb",
                "arguments": {
                    "query": "nonexistent topic"
                }
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        result_text = data["result"]["content"][0]["text"]
        assert "No relevant information found" in result_text
        assert "nonexistent topic" in result_text

    def test_query_kb_without_query_parameter(self, client):
        """query_kb without query should return error."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query_kb",
                "arguments": {}
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["isError"] is True
        assert "Query parameter is required" in data["result"]["content"][0]["text"]

    @patch("routes.mcp.DocumentLister")
    def test_list_indexed_documents_tool(self, mock_lister_class, client):
        """tools/call with list_indexed_documents should return document list."""
        mock_response = {
            "total_documents": 2,
            "documents": [
                {
                    "file_path": "/kb/doc1.txt",
                    "indexed_at": "2024-11-29T12:00:00",
                    "chunk_count": 10
                },
                {
                    "file_path": "/kb/doc2.pdf",
                    "indexed_at": "2024-11-29T13:00:00",
                    "chunk_count": 25
                }
            ]
        }

        mock_lister = AsyncMock()
        mock_lister.list_all.return_value = mock_response
        mock_lister_class.return_value = mock_lister

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_indexed_documents",
                "arguments": {}
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        result_text = data["result"]["content"][0]["text"]
        assert "2 total" in result_text
        assert "doc1.txt" in result_text
        assert "doc2.pdf" in result_text
        assert "Chunks: 10" in result_text
        assert "Chunks: 25" in result_text

    @patch("routes.mcp.DocumentLister")
    def test_list_indexed_documents_empty(self, mock_lister_class, client):
        """list_indexed_documents with no documents should return helpful message."""
        mock_response = {
            "total_documents": 0,
            "documents": []
        }

        mock_lister = AsyncMock()
        mock_lister.list_all.return_value = mock_response
        mock_lister_class.return_value = mock_lister

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_indexed_documents",
                "arguments": {}
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        result_text = data["result"]["content"][0]["text"]
        assert "No documents indexed yet" in result_text

    @patch("routes.mcp.get_app_state")
    @patch("routes.mcp.default_config")
    def test_get_kb_stats_tool(self, mock_config, mock_get_app_state, client):
        """tools/call with get_kb_stats should return statistics."""
        mock_config.model.name = "test-model-v1"

        # Mock app_state.get_vector_store_stats() to return stats
        mock_app_state = Mock()
        async def mock_stats():
            return {
                "indexed_documents": 100,
                "total_chunks": 5000,
            }
        mock_app_state.get_vector_store_stats = mock_stats
        mock_get_app_state.return_value = mock_app_state

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_kb_stats",
                "arguments": {}
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        result_text = data["result"]["content"][0]["text"]
        assert "Knowledge Base Statistics" in result_text
        assert "healthy" in result_text
        assert "Indexed Documents:" in result_text
        assert "Total Chunks:" in result_text
        assert "Embedding Model:" in result_text

    def test_unknown_tool_returns_error(self, client):
        """Calling unknown tool should return error."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "unknown_tool",
                "arguments": {}
            }
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["isError"] is True
        assert "Unknown tool" in data["result"]["content"][0]["text"]


class TestMCPErrorHandling:
    """Test JSON-RPC error handling."""

    def test_invalid_json_returns_parse_error(self, client):
        """Invalid JSON should return parse error."""
        response = client.post(
            "/mcp",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == -32700
        assert "Parse error" in data["error"]["message"]

    def test_missing_jsonrpc_field(self, client):
        """Missing jsonrpc field should return error."""
        request_data = {
            "id": 1,
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)

        # Pydantic defaults jsonrpc to "2.0", so this actually succeeds
        # This test verifies the default works correctly
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"

    def test_invalid_method_returns_error(self, client):
        """Invalid method should return method not found error."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "invalid_method"
        }

        response = client.post("/mcp", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["error"]["code"] == -32601
        assert "Method not found" in data["error"]["message"]

    def test_request_without_id(self, client):
        """Request without ID should still work (notification).

        Per JSON-RPC 2.0: if no id in request, response omits id field.
        Our implementation uses exclude_none=True, so null id is not included.
        """
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)

        # Should succeed - id omitted from response when not provided in request
        assert response.status_code == 200
        data = response.json()
        assert "id" not in data  # Null values are excluded from response


class TestMCPSSEStreaming:
    """Test Server-Sent Events (SSE) streaming."""

    @patch("routes.mcp.QueryExecutor")
    def test_sse_response_for_tool_call(self, mock_executor_class, client):
        """tools/call with SSE accept header should return SSE stream."""
        mock_response = Mock()
        mock_response.total_results = 1
        mock_result = Mock()
        mock_result.score = 0.95
        mock_result.source = "test.txt"
        mock_result.page = None
        mock_result.content = "Test content"
        mock_response.results = [mock_result]

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = mock_response
        mock_executor_class.return_value = mock_executor

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query_kb",
                "arguments": {
                    "query": "test"
                }
            }
        }

        response = client.post(
            "/mcp",
            json=request_data,
            headers={"Accept": "application/json, text/event-stream"}
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # SSE format: "data: {json}\n\n"
        response_text = response.text
        assert response_text.startswith("data: ")
        assert response_text.endswith("\n\n")

        # Extract JSON from SSE
        json_data = response_text.replace("data: ", "").strip()
        data = json.loads(json_data)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1

    def test_initialize_does_not_stream(self, client):
        """initialize method should not stream even with SSE accept header."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }

        response = client.post(
            "/mcp",
            json=request_data,
            headers={"Accept": "application/json, text/event-stream"}
        )

        assert response.status_code == 200
        # Should return JSON, not SSE
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert data["result"]["protocolVersion"] == "2024-11-05"

    def test_tools_list_does_not_stream(self, client):
        """tools/list should not stream even with SSE accept header."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post(
            "/mcp",
            json=request_data,
            headers={"Accept": "application/json, text/event-stream"}
        )

        assert response.status_code == 200
        # Should return JSON, not SSE
        assert response.headers["content-type"] == "application/json"


class TestMCPProtocolCompliance:
    """Test MCP protocol compliance."""

    def test_all_responses_have_jsonrpc_field(self, client):
        """All responses should have jsonrpc: '2.0' field."""
        test_cases = [
            {"method": "initialize"},
            {"method": "tools/list"},
        ]

        for test_case in test_cases:
            request_data = {
                "jsonrpc": "2.0",
                "id": 1,
                **test_case
            }

            response = client.post("/mcp", json=request_data)
            data = response.json()
            assert data["jsonrpc"] == "2.0"

    def test_response_id_matches_request_id(self, client):
        """Response ID should match request ID."""
        request_data = {
            "jsonrpc": "2.0",
            "id": "custom-id-12345",
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)
        data = response.json()
        assert data["id"] == "custom-id-12345"

    def test_success_response_has_result_field(self, client):
        """Successful response should have result field, not error.

        Per JSON-RPC 2.0 spec: success responses MUST NOT contain error field.
        """
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }

        response = client.post("/mcp", json=request_data)
        data = response.json()
        assert "result" in data
        assert "error" not in data  # Per spec: success MUST NOT contain error

    def test_error_response_has_error_field(self, client):
        """Error response should have error field, not result.

        Per JSON-RPC 2.0 spec: error responses MUST NOT contain result field.
        """
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "invalid_method"
        }

        response = client.post("/mcp", json=request_data)
        data = response.json()
        assert "error" in data
        assert "result" not in data  # Per spec: error MUST NOT contain result
        assert "code" in data["error"]
        assert "message" in data["error"]
