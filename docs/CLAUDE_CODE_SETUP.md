# Claude Code Setup for RAG-KB Priority

This guide shows how to configure Claude Code to **always prioritize your knowledge base** over general knowledge when answering questions.

---

## Why This Matters

By default, Claude Code may answer from its training data instead of checking your knowledge base first. This setup ensures:

1. **Your content takes priority** - Custom knowledge over general knowledge
2. **Automatic RAG checks** - Claude proactively searches your KB
3. **Transparent sourcing** - You know when answers come from your docs

---

## Setup Instructions

### Option 1: Project-Specific Instructions (Recommended)

Add this to your project's `.clauderc` or project instructions:

```markdown
## Knowledge Base Priority

**IMPORTANT**: Always check the RAG knowledge base BEFORE answering questions about:
- Technical concepts, APIs, or frameworks
- Code patterns or best practices
- Domain-specific knowledge (trading, finance, algorithms, etc.)
- Book content, papers, or documentation

**When to use RAG**:
1. User asks about a technical topic
2. User references a concept that might be in docs/books
3. You're about to provide a general answer to a specific question
4. User asks "how do I..." or "what is..." questions

**How to use**:
```
Use mcp__rag-kb__query_knowledge_base with:
- query: Natural language question
- top_k: 5-10 results (more for broad topics)
- threshold: 0.3 (filter weak matches)
```

**After RAG results**:
- ✅ If relevant chunks found: Base answer on KB content, cite sources
- ❌ If no relevant chunks: State "no relevant content in KB" then use general knowledge
- 🤔 If uncertain: Show user the chunks and ask if they're relevant

**Example**:
User: "How does the VIX work in trading?"
You: [Check RAG first with "VIX volatility index trading"] → [Use KB results if found]
```

### Option 2: Global Custom Instructions

Add to your global Claude Code settings (`~/.claude-code/instructions.md` or similar):

```markdown
# RAG Knowledge Base Integration

When answering technical or domain-specific questions:
1. **Always check RAG first** using mcp__rag-kb__query_knowledge_base
2. Prefer user's personal knowledge base over general training data
3. Cite sources when using KB content (e.g., "From 'Book Name', page X...")
4. If KB has no results, state that explicitly before using general knowledge

Tools:
- `query_knowledge_base` - Search user's personal docs/books/notes
- `list_indexed_documents` - See what's available in KB
- `get_kb_stats` - Check KB status (model, document count)
```

### Option 3: Enhanced MCP Tool Description

If you want to make this automatic, edit [`mcp-server/index.js`](../mcp-server/index.js):

```javascript
{
  name: "query_knowledge_base",
  description:
    "**USE THIS FIRST** for technical questions, domain knowledge, or book/doc references. " +
    "Search your personal knowledge base (books, notes, documentation) for relevant information. " +
    "This should be your PRIMARY source before using general knowledge. " +
    "Returns the most semantically similar content chunks ranked by relevance.",
  // ... rest of tool definition
}
```

---

## Verification

Test that it's working:

```bash
# Start RAG service
docker-compose up -d

# In Claude Code, ask about content you know is in your KB:
"What does Sandi Metz say about method length?"
"Explain the volatility index from my trading books"
"How does SQLite indexing work according to my docs?"
```

Claude should:
1. ✅ Use `query_knowledge_base` tool
2. ✅ Show the search query
3. ✅ Display relevant chunks
4. ✅ Answer based on KB content
5. ✅ Cite the source document

---

## Best Practices

### For Users

**Be explicit when you want RAG**:
- ✅ "Check my KB for information about..."
- ✅ "What do my trading books say about..."
- ✅ "According to my documentation..."

**Help Claude prioritize**:
- Mention book/author names you know are indexed
- Reference topics you've added to your KB
- Use `list_indexed_documents` to see what's available

### For Claude

**Proactive RAG usage**:
- Check KB for technical terms, frameworks, APIs
- Search KB when user mentions books/papers in your index
- Use KB for domain-specific questions (trading, algorithms, etc.)

**Transparency**:
- Always show when you're using KB vs general knowledge
- If KB has no results, say: "No relevant content in your knowledge base. Based on general knowledge..."
- Cite sources: "From 'SQL Performance Explained': ..."

---

## Advanced: Threshold Tuning

Adjust `threshold` parameter for different use cases:

| Threshold | Use Case | Trade-off |
|-----------|----------|-----------|
| 0.0 (default) | Exploratory search | Returns everything, may include noise |
| 0.3 | Balanced | Good mix of recall/precision |
| 0.5 | High confidence | Only very relevant results |
| 0.7 | Exact match | Very strict, may miss relevant content |

**Recommendation**: Start with `threshold: 0.3` and adjust based on results.

---

## Troubleshooting

### Claude isn't using RAG automatically

**Solution**: Add explicit project instructions (Option 1 above)

### Too many irrelevant results

**Solutions**:
- Increase `threshold` to 0.4-0.5
- Reduce `top_k` to 3-5
- Make queries more specific

### Missing relevant content

**Solutions**:
- Check if document is indexed: `list_indexed_documents`
- Lower `threshold` to 0.2
- Try different query phrasings
- Reindex if you added new content

### RAG service not responding

```bash
# Check if service is running
docker ps | grep rag-api

# Check health
curl http://localhost:8000/health

# Restart if needed
docker-compose restart rag-api
```

---

## Example Workflow

**User**: "How do I optimize SQL queries?"

**Claude (with RAG priority)**:
```
Let me check your knowledge base for SQL optimization content.
[Uses query_knowledge_base with "SQL query optimization performance"]

Found relevant content from "SQL Performance Explained - Markus Winand":
[Shows top 3-5 chunks with scores]

Based on your documentation:
1. Index Selection: ...
2. Query Planning: ...
[Answer based on KB content]

Sources:
- SQL Performance Explained - Markus Winand.txt (chunks 234, 235, 237)
```

---

## Related Documentation

- [README.md](../README.md) - Main documentation
- [VSCode Integration](../README.md#vscodeclaude-code-integration) - Setup guide
- [MCP Server](../mcp-server/) - Server implementation

---

**Last Updated**: 2025-11-14
**Version**: v0.2.0-alpha
