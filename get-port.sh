#!/bin/bash
# Get the dynamically assigned port for RAG API

PORT=$(docker-compose ps -q rag-api | xargs docker inspect --format='{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}')

if [ -z "$PORT" ]; then
    echo "Error: RAG API container not running"
    exit 1
fi

echo "RAG API is running on: http://localhost:$PORT"
echo "Docs: http://localhost:$PORT/docs"
echo ""
echo "Test query:"
echo "curl -X POST http://localhost:$PORT/query -H 'Content-Type: application/json' -d '{\"text\": \"refactoring\", \"top_k\": 3}'"
