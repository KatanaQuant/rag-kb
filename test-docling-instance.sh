#!/bin/bash
set -e

echo "=========================================="
echo "Docling Test Instance Manager"
echo "=========================================="
echo ""

# Create test directories if they don't exist
mkdir -p knowledge_base_test
mkdir -p data_test

case "$1" in
  start)
    echo "Starting test instance on port 8001..."
    docker-compose -f docker-compose.test.yml up --build -d
    echo ""
    echo "Waiting for service to be healthy..."
    sleep 5
    echo ""
    echo "✅ Test instance started!"
    echo "   URL: http://localhost:8001"
    echo "   Health: http://localhost:8001/health"
    echo "   Docs: http://localhost:8001/docs"
    echo ""
    echo "Check health:"
    curl -s http://localhost:8001/health | jq || echo "Waiting for service..."
    ;;

  stop)
    echo "Stopping test instance..."
    docker-compose -f docker-compose.test.yml down
    echo "✅ Test instance stopped"
    ;;

  logs)
    echo "Showing logs (Ctrl+C to exit)..."
    docker-compose -f docker-compose.test.yml logs -f
    ;;

  health)
    echo "Checking health..."
    curl -s http://localhost:8001/health | jq
    ;;

  query)
    if [ -z "$2" ]; then
      echo "Usage: $0 query \"your question\""
      exit 1
    fi
    echo "Querying: $2"
    curl -s -X POST http://localhost:8001/query \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$2\", \"top_k\": 3}" | jq
    ;;

  reindex)
    echo "Forcing reindex..."
    curl -s -X POST http://localhost:8001/index \
      -H "Content-Type: application/json" \
      -d '{"force_reindex": true}' | jq
    ;;

  clean)
    echo "Cleaning test data (keeps knowledge_base_test/)..."
    docker-compose -f docker-compose.test.yml down
    rm -rf data_test
    echo "✅ Test data cleaned"
    ;;

  nuke)
    echo "⚠️  Removing ALL test data including knowledge_base_test/"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
      docker-compose -f docker-compose.test.yml down
      rm -rf data_test knowledge_base_test
      echo "✅ All test data removed"
    else
      echo "Cancelled"
    fi
    ;;

  compare)
    echo "Comparing test vs production instances..."
    echo ""
    echo "Production (port 8000):"
    curl -s http://localhost:8000/health | jq || echo "Not running"
    echo ""
    echo "Test (port 8001):"
    curl -s http://localhost:8001/health | jq || echo "Not running"
    ;;

  *)
    echo "Usage: $0 {start|stop|logs|health|query|reindex|clean|nuke|compare}"
    echo ""
    echo "Commands:"
    echo "  start    - Start test instance on port 8001"
    echo "  stop     - Stop test instance"
    echo "  logs     - Show logs"
    echo "  health   - Check health status"
    echo "  query    - Query the test instance"
    echo "  reindex  - Force reindex test database"
    echo "  clean    - Remove test database (keeps KB files)"
    echo "  nuke     - Remove ALL test data (DB + KB files)"
    echo "  compare  - Compare production vs test stats"
    echo ""
    echo "Example workflow:"
    echo "  1. ./test-docling-instance.sh start"
    echo "  2. cp some.pdf knowledge_base_test/"
    echo "  3. ./test-docling-instance.sh reindex"
    echo "  4. ./test-docling-instance.sh query \"test question\""
    echo "  5. ./test-docling-instance.sh stop"
    exit 1
    ;;
esac
