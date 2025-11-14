#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const RAG_API_URL = process.env.RAG_API_URL || "http://localhost:8000";

// MCP Server
const server = new Server(
  {
    name: "rag-kb",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Tool: Query knowledge base
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "query_knowledge_base",
        description:
          "⚠️ **CHECK THIS FIRST** for technical questions, APIs, frameworks, algorithms, or domain-specific knowledge. " +
          "Search your personal knowledge base (books, notes, documentation) for relevant information. " +
          "This is your PRIMARY source - always use it BEFORE relying on general knowledge. " +
          "Returns the most semantically similar content chunks ranked by relevance. " +
          "If no relevant chunks found (score < 0.3), then use general knowledge.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "The search query or question to find relevant information for",
            },
            top_k: {
              type: "number",
              description: "Number of results to return (default: 5, max: 20)",
              default: 5,
            },
            threshold: {
              type: "number",
              description: "Minimum similarity score (0-1). Only return results above this threshold.",
              default: 0.0,
            },
          },
          required: ["query"],
        },
      },
      {
        name: "list_indexed_documents",
        description:
          "List all documents currently indexed in the knowledge base. " +
          "Shows filenames, when they were indexed, and how many chunks each contains. " +
          "Useful to see what knowledge is available.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "get_kb_stats",
        description:
          "Get statistics about the knowledge base: total documents, total chunks, and embedding model used. " +
          "Useful for understanding the current state of the knowledge base.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "query_knowledge_base": {
        const { query, top_k = 5, threshold = 0.0 } = args;

        if (!query) {
          throw new Error("Query parameter is required");
        }

        const response = await fetch(`${RAG_API_URL}/query`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: query,
            top_k: Math.min(top_k, 20),
            threshold: threshold > 0 ? threshold : null,
          }),
        });

        if (!response.ok) {
          throw new Error(`RAG API error: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();

        // Format results for Claude
        let result = `Found ${data.total_results} relevant chunks for: "${query}"\n\n`;

        data.results.forEach((item, idx) => {
          result += `## Result ${idx + 1} (Score: ${item.score.toFixed(3)})\n`;
          result += `**Source:** ${item.source}`;
          if (item.page) result += ` (Page ${item.page})`;
          result += `\n\n${item.content}\n\n---\n\n`;
        });

        if (data.total_results === 0) {
          result = `No relevant information found for: "${query}"\n\nTry:\n- Rephrasing your query\n- Using different keywords\n- Checking if relevant documents are indexed`;
        }

        return {
          content: [
            {
              type: "text",
              text: result,
            },
          ],
        };
      }

      case "list_indexed_documents": {
        const response = await fetch(`${RAG_API_URL}/documents`);

        if (!response.ok) {
          throw new Error(`RAG API error: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();

        let result = `# Indexed Documents (${data.total_documents} total)\n\n`;

        if (data.documents.length === 0) {
          result += "No documents indexed yet. Add files to the knowledge_base/ directory.\n";
        } else {
          data.documents.forEach((doc) => {
            const filename = doc.file_path.split("/").pop();
            result += `- **${filename}**\n`;
            result += `  - Indexed: ${doc.indexed_at}\n`;
            result += `  - Chunks: ${doc.chunk_count}\n\n`;
          });
        }

        return {
          content: [
            {
              type: "text",
              text: result,
            },
          ],
        };
      }

      case "get_kb_stats": {
        const response = await fetch(`${RAG_API_URL}/health`);

        if (!response.ok) {
          throw new Error(`RAG API error: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();

        const result = `# Knowledge Base Statistics

**Status:** ${data.status}
**Indexed Documents:** ${data.indexed_documents}
**Total Chunks:** ${data.total_chunks}
**Embedding Model:** ${data.model}

The knowledge base is ${data.status === "healthy" ? "ready" : "not ready"} for queries.
`;

        return {
          content: [
            {
              type: "text",
              text: result,
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("RAG-KB MCP server running on stdio");
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
