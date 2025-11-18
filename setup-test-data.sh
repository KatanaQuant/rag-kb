#!/bin/bash
# setup-test-data.sh - Initialize test data for refactoring

echo "Setting up test data..."

# Create directories
mkdir -p data_test knowledge_base_test

# Option: Copy minimal production DB (optional)
if [ -f "data/rag.db" ] && [ ! -f "data_test/rag.db" ]; then
    echo "Copying production DB for baseline tests..."
    cp data/rag.db data_test/rag.db
    echo "  ✓ Database copied"
else
    echo "  ℹ Test will create fresh database"
fi

# Knowledge base is already minimal (test_document.md)
echo "  ✓ Test knowledge base ready"

echo ""
echo "Test data setup complete!"
echo "Start testing with: ./test-runner.sh start && ./test-runner.sh test"
