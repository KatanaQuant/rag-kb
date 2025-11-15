#!/bin/bash
set -e

echo "=========================================="
echo "Docling PDF Integration Test Manager"
echo "=========================================="
echo ""

# Create docling directories if they don't exist
mkdir -p knowledge_base_docling
mkdir -p data_docling

case "$1" in
  start)
    echo "Starting Docling instance on port 8002..."
    docker-compose -f docker-compose.docling.yml up --build -d
    echo ""
    echo "Waiting for service to be healthy..."
    sleep 5
    echo ""
    echo "✅ Docling instance started!"
    echo "   URL: http://localhost:8002"
    echo "   Health: http://localhost:8002/health"
    echo "   Docs: http://localhost:8002/docs"
    echo ""
    echo "Check health:"
    curl -s http://localhost:8002/health | jq || echo "Waiting for service..."
    ;;

  stop)
    echo "Stopping Docling instance..."
    docker-compose -f docker-compose.docling.yml down
    echo "✅ Docling instance stopped"
    ;;

  logs)
    echo "Showing logs (Ctrl+C to exit)..."
    docker-compose -f docker-compose.docling.yml logs -f
    ;;

  health)
    echo "Checking health..."
    curl -s http://localhost:8002/health | jq
    ;;

  query)
    if [ -z "$2" ]; then
      echo "Usage: $0 query \"your question\""
      exit 1
    fi
    echo "Querying: $2"
    curl -s -X POST http://localhost:8002/query \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$2\", \"top_k\": 3}" | jq
    ;;

  reindex)
    echo "Forcing reindex..."
    curl -s -X POST http://localhost:8002/index \
      -H "Content-Type: application/json" \
      -d '{"force_reindex": true}' | jq
    ;;

  clean)
    echo "Cleaning Docling data (keeps knowledge_base_docling/)..."
    docker-compose -f docker-compose.docling.yml down
    rm -rf data_docling
    echo "✅ Docling data cleaned"
    ;;

  nuke)
    echo "⚠️  Removing ALL Docling data including knowledge_base_docling/"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
      docker-compose -f docker-compose.docling.yml down
      rm -rf data_docling knowledge_base_docling
      echo "✅ All Docling data removed"
    else
      echo "Cancelled"
    fi
    ;;

  compare)
    echo "Comparing instances..."
    echo ""
    echo "Production (port 8000) - PyMuPDF:"
    curl -s http://localhost:8000/health | jq -r '.documents, .chunks' 2>/dev/null | paste -sd '/' - || echo "Not running"
    echo ""
    echo "Test (port 8001):"
    curl -s http://localhost:8001/health | jq -r '.documents, .chunks' 2>/dev/null | paste -sd '/' - || echo "Not running"
    echo ""
    echo "Docling (port 8002) - Docling PDF:"
    curl -s http://localhost:8002/health | jq -r '.documents, .chunks' 2>/dev/null | paste -sd '/' - || echo "Not running"
    ;;

  compare-query)
    if [ -z "$2" ]; then
      echo "Usage: $0 compare-query \"your question\""
      exit 1
    fi
    echo "Comparing query results: \"$2\""
    echo ""
    echo "========== Production (PyMuPDF) =========="
    curl -s -X POST http://localhost:8000/query \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$2\", \"top_k\": 3}" | jq
    echo ""
    echo "========== Docling (Advanced PDF) =========="
    curl -s -X POST http://localhost:8002/query \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$2\", \"top_k\": 3}" | jq
    ;;

  *)
    echo "Usage: $0 {start|stop|logs|health|query|reindex|clean|nuke|compare|compare-query}"
    echo ""
    echo "Commands:"
    echo "  start         - Start Docling instance on port 8002"
    echo "  stop          - Stop Docling instance"
    echo "  logs          - Show logs"
    echo "  health        - Check health status"
    echo "  query         - Query the Docling instance"
    echo "  reindex       - Force reindex Docling database"
    echo "  clean         - Remove Docling database (keeps KB files)"
    echo "  nuke          - Remove ALL Docling data (DB + KB files)"
    echo "  compare       - Compare production vs Docling stats"
    echo "  compare-query - Compare query results side-by-side"
    echo ""
    echo "Example workflow:"
    echo "  1. ./docling-instance.sh start"
    echo "  2. cp complex.pdf knowledge_base_docling/"
    echo "  3. ./docling-instance.sh reindex"
    echo "  4. ./docling-instance.sh compare-query \"tables in the document\""
    echo "  5. ./docling-instance.sh compare"
    echo "  6. ./docling-instance.sh stop"
    echo ""
    echo "Testing PDF extraction quality:"
    echo "  - Add same PDFs to both knowledge_base/ and knowledge_base_docling/"
    echo "  - Use compare-query to see extraction differences"
    echo "  - Focus on PDFs with tables, multi-column layouts, formulas"
    exit 1
    ;;
esac
