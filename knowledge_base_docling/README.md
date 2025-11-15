# Docling PDF Test Knowledge Base

**Purpose**: Testing Docling PDF integration with complex PDFs

This directory is for testing advanced PDF extraction with the Docling library.

## Test Instance Details

- **Port**: 8002 (isolated from production:8000 and test:8001)
- **Database**: `data_docling/knowledge_base.db`
- **Docker Compose**: `docker-compose.docling.yml`
- **Management Script**: `./docling-instance.sh`

## Usage

1. Add PDFs to this directory for testing
2. Start Docling instance: `./docling-instance.sh start`
3. Query via: `curl -X POST http://localhost:8002/query -H "Content-Type: application/json" -d '{"text": "query"}'`
4. Stop instance: `./docling-instance.sh stop`

## Focus Areas

Test PDFs should include:
- Complex tables
- Multi-column layouts
- Headers/footers
- Embedded images
- Mathematical formulas
- Scientific papers

## Comparison

Compare extraction quality between:
- **Standard** (PyMuPDF): Production instance on port 8000
- **Docling**: This instance on port 8002
