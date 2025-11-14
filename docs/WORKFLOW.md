# Code Analysis Workflow

## Use Case 1: Reverse Engineering Existing Code

### Goal
Understand how a codebase implements concepts from books you have.

### Process

1. **Export the codebase:**
   ```bash
   ./export-for-analysis.sh ~/projects/mystery-app "Flask web app with trading logic" \
       > knowledge_base/codebases/mystery-app-analysis.md
   ```

2. **Add your analysis notes** directly in the markdown:
   - Document patterns you discover
   - Link to book concepts
   - Note deviations from best practices

3. **Query RAG for comparisons:**
   ```bash
   # Ask how the book explains a pattern you found
   curl -X POST http://localhost:8000/query -d '{"text": "dependency injection in OOP", "top_k": 3}'

   # Or use Claude with MCP: "Compare this code to what Sandi Metz teaches about dependencies"
   ```

### Example
```bash
# Export Flask app
./export-for-analysis.sh ~/code/legacy-api "Old Flask API to modernize" \
    > knowledge_base/codebases/legacy-api-v1.md

# Edit the file, add notes:
# "This uses global state - violates POODR chapter 3"
# "Similar to pattern on page 42 of Designing Data-Intensive Apps"

# Ingest
docker-compose restart rag-api

# Query
# "Show me Sandi Metz's advice on refactoring global state"
```

---

## Use Case 2: Book vs Implementation Comparison

### Goal
See if author's actual code matches their book's teachings.

### Process

1. **Get author's example code:**
   ```bash
   # Clone their repo
   git clone https://github.com/sandimetz/99bottles

   # Export it
   ./export-for-analysis.sh 99bottles "Sandi Metz's 99 Bottles implementation" \
       > knowledge_base/codebases/sandi-99bottles-code.md
   ```

2. **Add comparison notes:**
   ```markdown
   ### Chapter 3 Comparison

   **Book says:** "Replace conditionals with polymorphism"
   **Code does:** Uses case statement in early chapters, refactors to classes later
   **Insight:** Shows evolution of design, not just end state
   ```

3. **Query for cross-references:**
   ```bash
   # "Compare 99 Bottles book chapter 3 with the actual implementation"
   # "What does Sandi's code reveal about refactoring strategy?"
   ```

---

## Use Case 3: Regression Checking Across Projects

### Goal
Ensure you don't repeat mistakes from Project A in Project B.

### Process

1. **Document the mistake in Project A:**
   ```bash
   # Export problematic code
   ./export-for-analysis.sh ~/projects/trading-bot-v1 "First attempt, had race conditions" \
       > knowledge_base/codebases/trading-bot-v1-issues.md
   ```

2. **Add lessons learned section:**
   ```markdown
   ## Critical Issues Found

   ### Race Condition in Order Processing
   **Problem:** Lines 45-67 in order_handler.py
   **Root cause:** Shared state without locking
   **Fix applied:** Used message queue pattern
   **Source:** Designing Data-Intensive Applications, Chapter 5
   ```

3. **Export new project:**
   ```bash
   ./export-for-analysis.sh ~/projects/trading-bot-v2 "Second attempt with fixes" \
       > knowledge_base/codebases/trading-bot-v2.md
   ```

4. **Query for regression check:**
   ```bash
   # "Does trading-bot-v2 have the same race condition issues as v1?"
   # "Show me all known concurrency bugs from previous projects"
   # "What order processing patterns worked well before?"
   ```

---

## Use Case 4: Pattern Evolution Tracking

### Goal
Track how your implementation of patterns improves over time.

### Create Pattern-Specific Docs

```bash
knowledge_base/patterns/
├── authentication-evolution.md      # How you've done auth in each project
├── error-handling-patterns.md       # Different approaches tried
├── database-access-layers.md        # ORM vs raw SQL decisions
└── api-design-learnings.md          # REST patterns that worked/failed
```

### Example: Authentication Evolution
```markdown
# Authentication Pattern Evolution

## Project 1: trading-bot-v1 (2023-01)
**Approach:** Session cookies + database lookup
**Issues:** Database bottleneck, no token refresh
**Book reference:** None (made it up)

## Project 2: api-gateway (2023-06)
**Approach:** JWT tokens with Redis cache
**Improvements:** Faster, stateless
**Issues:** Token expiry UX problems
**Book reference:** Designing Data-Intensive Apps, Ch. 8 on caching

## Project 3: trading-platform (2024-01)
**Approach:** JWT + refresh tokens + Redis
**Improvements:** Solved expiry issues, added rotation
**Book reference:** OAuth 2.0 spec + OWASP guidelines
**Code location:** `knowledge_base/codebases/trading-platform-auth.md`

## Current Best Practice
- Use JWT for stateless auth
- Redis for session management
- Refresh token rotation
- Rate limiting on auth endpoints
```

---

## Recommended Structure

```
knowledge_base/
├── books/                          # Already have these
│   ├── 99-bottles-sandi-metz.txt
│   ├── practical-ood-ruby.txt
│   ├── designing-data-intensive-apps.txt
│   └── sql-performance-explained.txt
│
├── codebases/
│   ├── author-examples/            # How authors implement their own advice
│   │   ├── sandi-metz-99bottles.md
│   │   └── flask-official-examples.md
│   │
│   ├── my-projects/                # Your code evolution
│   │   ├── trading-bot-v1.md
│   │   ├── trading-bot-v2.md
│   │   └── api-gateway.md
│   │
│   └── third-party/                # Code you're studying
│       ├── open-source-project-x.md
│       └── legacy-system-analysis.md
│
├── patterns/                       # Cross-project learnings
│   ├── authentication-evolution.md
│   ├── error-handling-patterns.md
│   ├── database-patterns.md
│   └── api-design-learnings.md
│
└── regressions/                    # Known issues and fixes
    ├── concurrency-bugs.md
    ├── performance-pitfalls.md
    └── security-mistakes.md
```

---

## Query Strategies

### Reverse Engineering
- "How does this implement the strategy pattern mentioned in 99 Bottles?"
- "Compare this class design to POODR principles"

### Cross-Reference
- "What does the Designing Data-Intensive Apps book say about this caching approach?"
- "Is this error handling pattern in any of my books?"

### Regression Check
- "Have I seen this concurrency bug before in other projects?"
- "What was the fix for the race condition in trading-bot-v1?"

### Pattern Learning
- "Show all authentication implementations across my projects"
- "How has my error handling evolved over time?"

---

## Tips

1. **Be selective:** Don't dump entire codebases - export key files with context
2. **Add context:** The markdown notes you add are searchable too
3. **Link concepts:** Explicitly reference "Page 42 of POODR" in your notes
4. **Track evolution:** Keep snapshots before/after refactoring
5. **Document learnings:** Your analysis is as valuable as the code itself

---

## Example Session

```bash
# 1. You're working on a new project
cd ~/projects/new-trading-system

# 2. You write some code...

# 3. You want to check: "Have I done this before? What did the books say?"
curl -X POST http://localhost:8000/query \
  -d '{"text": "order processing concurrency patterns", "top_k": 5}'

# Returns:
# - trading-bot-v1 race condition issue (your past mistake)
# - trading-bot-v2 fix using message queue (your solution)
# - DDIA Chapter 5 on message queues (book knowledge)
# - Your patterns/concurrency-bugs.md notes

# 4. You refactor based on learnings

# 5. Export the new code with notes
./export-for-analysis.sh . "New trading system, applied lessons from v1 & v2" \
    > ../RAG/knowledge_base/codebases/trading-system-v3.md

# 6. Restart RAG to index it
docker-compose restart rag-api

# Now future you can query this experience!
```
