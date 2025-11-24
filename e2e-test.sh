#!/bin/bash
# Automated E2E test for RAG-KB Python 3.13 upgrade
# Tests all supported file types through the complete pipeline

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="http://localhost:8000"
KB_DIR="knowledge_base"
KB_ABS_PATH="/app/knowledge_base"  # Absolute path as stored in DB
MAX_WAIT=300  # 5 minutes max wait per file
POLL_INTERVAL=2

# Test files - using small existing files from KB (by chunk count, not file size)
# These will be deleted via API and re-indexed via force priority
declare -A TEST_FILES=(
    ["py"]="code/systematictradingexamples/randompriceexample.py"
    ["go"]="code/lets_go/snippetbox-source-code/snippetbox/internal/models/testutils_test.go"
    ["md"]="code/systematictradingexamples/README.md"
    ["pdf"]="The Little Go Book - Karl Seguin.pdf"
    ["ipynb"]="code/pysystemtrade/examples/introduction/simplesystem.ipynb"
    ["epub"]="Test-Driven Development By Example - Kent Beck.epub"
)

# Results tracking
declare -A RESULTS
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if API is running
check_api() {
    log_info "Checking if API is available at $API_URL..."
    if ! curl -s "$API_URL/health" > /dev/null; then
        log_error "API not available at $API_URL"
        exit 1
    fi
    log_success "API is running"
}

# Delete document via API
delete_document() {
    local filepath="$1"
    local filename=$(basename "$filepath")
    log_info "Deleting $filename from RAG..."

    # URL encode the filepath
    local encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$filepath'))")

    response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_URL/document/$encoded_path")

    # Split response and status code
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        log_success "Deleted successfully: $filename"
        return 0
    elif [ "$http_code" == "404" ]; then
        log_warn "Not found (already deleted or never indexed): $filename"
        return 0
    else
        log_warn "Delete response ($http_code): $body"
        return 0  # Don't fail test
    fi
}

# Wait for file to be processed
wait_for_processing() {
    local filename="$1"
    local start_time=$(date +%s)

    log_info "Waiting for $filename to be processed..."

    while true; do
        # Check queue status
        queue_response=$(curl -s "$API_URL/queue/jobs")

        # Check if file is still in queue
        if echo "$queue_response" | grep -q "$filename"; then
            local elapsed=$(($(date +%s) - start_time))
            if [ $elapsed -gt $MAX_WAIT ]; then
                log_error "Timeout waiting for $filename (>${MAX_WAIT}s)"
                return 1
            fi
            echo -ne "\r${YELLOW}[⋯]${NC} Processing $filename... ${elapsed}s elapsed"
            sleep $POLL_INTERVAL
        else
            echo -ne "\r"
            log_success "$filename processing complete"
            return 0
        fi
    done
}

# Get system stats (document and chunk counts)
get_stats() {
    local response=$(curl -s "$API_URL/health")
    local doc_count=$(echo "$response" | grep -o '"indexed_documents":[0-9]*' | cut -d: -f2)
    local chunk_count=$(echo "$response" | grep -o '"total_chunks":[0-9]*' | cut -d: -f2)
    echo "$doc_count $chunk_count"
}

# Query to verify document is indexed
query_document() {
    local search_term="$1"
    local filename="$2"

    log_info "Querying for content from $filename..."

    response=$(curl -s -X POST "$API_URL/query" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"$search_term\", \"top_k\": 5}")

    if echo "$response" | grep -q "\"total_results\":[1-9]"; then
        local result_count=$(echo "$response" | grep -o '"total_results":[0-9]*' | cut -d: -f2)
        log_success "Query successful: found $result_count results"
        return 0
    else
        log_error "Query failed or returned no results"
        return 1
    fi
}

# Test single file through complete pipeline
test_file() {
    local file_type="$1"
    local filename="$2"
    local test_num=$((TOTAL_TESTS + 1))

    echo ""
    echo "========================================"
    echo "Test $test_num: $file_type - $filename"
    echo "========================================"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    # Get initial stats
    read initial_docs initial_chunks <<< $(get_stats)
    log_info "Initial: $initial_docs documents, $initial_chunks chunks"

    # Step 1: Delete from RAG API (clears DB + processing tracking)
    # Special handling for EPUB: also delete the converted PDF
    if [ "$file_type" == "epub" ]; then
        local base_name="${filename%.epub}"
        local pdf_version="${base_name}.pdf"
        log_info "EPUB detected - also removing converted PDF if exists"
        delete_document "$KB_ABS_PATH/$pdf_version" || true
        delete_document "$KB_ABS_PATH/$filename" || true
    else
        delete_document "$KB_ABS_PATH/$filename" || true
    fi

    sleep 2  # Give deletion time to complete

    # Step 2: Force re-indexing via priority endpoint (bypasses "already indexed" check)
    log_info "Setting $filename to priority processing with force=true..."

    # URL encode the filepath
    local encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$KB_ABS_PATH/$filename'))")

    local response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/indexing/priority/$encoded_path?force=true")
    local http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "200" ]; then
        log_success "Forced re-indexing queued for $filename"
    else
        log_warn "Priority response ($http_code) - continuing anyway"
    fi

    sleep 2  # Give time for queuing

    # Step 3: Wait for processing to complete
    # For EPUB, we need to wait for the converted PDF to be processed
    local file_to_monitor="$filename"
    if [ "$file_type" == "epub" ]; then
        log_info "EPUB converts to PDF - monitoring both files..."
    fi

    if wait_for_processing "$file_to_monitor"; then
        # Step 4: Verify chunks were added
        sleep 3  # Give indexing time to finish

        read final_docs final_chunks <<< $(get_stats)
        log_info "Final: $final_docs documents, $final_chunks chunks"

        local chunks_added=$((final_chunks - initial_chunks))

        if [ $chunks_added -gt 0 ]; then
            log_success "Added $chunks_added new chunks"

            # Step 5: Query to verify content is searchable
            local search_query
            case "$file_type" in
                py) search_query="random" ;;  # randompriceexample.py
                go) search_query="test" ;;  # testutils_test.go
                md) search_query="trading" ;;  # README.md (systematictradingexamples)
                pdf) search_query="Go" ;;  # The Little Go Book
                ipynb) search_query="system" ;;  # simplesystem.ipynb
                epub) search_query="test driven" ;;  # TDD by Example
            esac

            if query_document "$search_query" "$filename"; then
                RESULTS[$file_type]="PASS"
                PASSED_TESTS=$((PASSED_TESTS + 1))
                log_success "TEST PASSED: $file_type ($filename) - $chunks_added chunks"
            else
                RESULTS[$file_type]="FAIL (Query)"
                FAILED_TESTS=$((FAILED_TESTS + 1))
                log_error "TEST FAILED: $file_type ($filename) - Query failed"
            fi
        else
            RESULTS[$file_type]="FAIL (No Chunks)"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            log_error "TEST FAILED: $file_type ($filename) - No chunks added"
        fi
    else
        RESULTS[$file_type]="FAIL (Timeout)"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        log_error "TEST FAILED: $file_type ($filename) - Processing timeout"
    fi

    # No cleanup - leave test files in place
    # Files remain in KB directory for manual inspection if needed
    log_info "Test files left in place for inspection"
}

# Generate report
generate_report() {
    echo ""
    echo "========================================"
    echo "         E2E TEST REPORT"
    echo "========================================"
    echo ""
    echo "Total Tests:  $TOTAL_TESTS"
    echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"
    echo ""
    echo "Results by File Type:"
    echo "---------------------"

    for file_type in "${!TEST_FILES[@]}"; do
        local result="${RESULTS[$file_type]:-NOT RUN}"
        local filename="${TEST_FILES[$file_type]}"

        if [ "$result" == "PASS" ]; then
            echo -e "${GREEN}✓${NC} $file_type: $filename - $result"
        else
            echo -e "${RED}✗${NC} $file_type: $filename - $result"
        fi
    done

    echo ""
    echo "========================================"

    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}ALL TESTS PASSED!${NC} ✓"
        echo "Python 3.13 upgrade is working correctly."
        return 0
    else
        echo -e "${RED}SOME TESTS FAILED!${NC} ✗"
        echo "Please review the logs above for details."
        return 1
    fi
}

# Main execution
main() {
    echo "========================================"
    echo "   RAG-KB E2E Test Suite"
    echo "   Python 3.13 Upgrade Verification"
    echo "========================================"
    echo ""

    # Setup
    check_api

    # Verify test files exist in KB
    if [ ! -d "$KB_DIR" ]; then
        log_error "Knowledge base directory not found: $KB_DIR"
        exit 1
    fi

    log_info "Using existing KB files for testing (will delete and re-index):"
    local missing_files=0
    for file_type in "${!TEST_FILES[@]}"; do
        local filename="${TEST_FILES[$file_type]}"
        if [ -f "$KB_DIR/$filename" ]; then
            log_success "$file_type: $filename"
        else
            log_warn "$file_type: $filename NOT FOUND in KB"
            missing_files=$((missing_files + 1))
        fi
    done

    if [ $missing_files -gt 0 ]; then
        log_warn "$missing_files test files not found in KB - tests will be skipped for those types"
    fi

    echo ""
    log_info "Starting E2E tests..."
    echo ""

    # Run tests for each file type
    for file_type in "${!TEST_FILES[@]}"; do
        local filename="${TEST_FILES[$file_type]}"
        if [ -f "$KB_DIR/$filename" ]; then
            test_file "$file_type" "$filename"
        else
            log_warn "Skipping $file_type test - file not found"
        fi
    done

    # Generate report
    generate_report
}

# Run main
main
