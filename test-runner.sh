#!/bin/bash
# test-runner.sh - Convenience wrapper for test commands

COMPOSE_FILE="docker-compose.test.yml"
SERVICE="rag-api-test"

case "$1" in
  start)
    echo "Starting test container..."
    docker-compose -f $COMPOSE_FILE up -d --build
    echo ""
    echo "Test container started on port 8001"
    echo "Run tests with: ./test-runner.sh test"
    ;;
  stop)
    echo "Stopping test container..."
    docker-compose -f $COMPOSE_FILE down
    ;;
  test)
    shift
    echo "Running tests: $@"
    docker-compose -f $COMPOSE_FILE exec -T $SERVICE python -m pytest tests/ -v "$@"
    ;;
  coverage)
    echo "Running tests with coverage..."
    docker-compose -f $COMPOSE_FILE exec -T $SERVICE \
      python -m pytest tests/ -v --cov=. --cov-report=term-missing
    ;;
  watch)
    echo "Starting watch mode..."
    docker-compose -f $COMPOSE_FILE exec $SERVICE \
      bash -c "pip install -q pytest-watch && ptw -- tests/ -v"
    ;;
  shell)
    echo "Opening shell in test container..."
    docker-compose -f $COMPOSE_FILE exec $SERVICE /bin/bash
    ;;
  rebuild)
    echo "Rebuilding test container..."
    docker-compose -f $COMPOSE_FILE down
    docker-compose -f $COMPOSE_FILE up -d --build --force-recreate
    ;;
  *)
    echo "Test Runner - Safe refactoring with continuous verification"
    echo ""
    echo "Usage: $0 {start|stop|test|coverage|watch|shell|rebuild}"
    echo ""
    echo "Commands:"
    echo "  start                          Start test container"
    echo "  test [args]                    Run all tests (or specific with args)"
    echo "  coverage                       Run with coverage report"
    echo "  watch                          Continuous testing (auto-rerun on save)"
    echo "  shell                          Open shell in container"
    echo "  rebuild                        Force rebuild container"
    echo "  stop                           Stop test container"
    echo ""
    echo "Examples:"
    echo "  $0 start                              # Start test container"
    echo "  $0 test                               # Run all tests"
    echo "  $0 test tests/test_ingestion.py      # Run specific file"
    echo "  $0 test -k TextChunker                # Run tests matching pattern"
    echo "  $0 coverage                           # Run with coverage"
    echo "  $0 watch                              # Watch mode for refactoring"
    exit 1
    ;;
esac
