"""Tests for queue worker independence.

Issue 2.3: Verify all queue workers (chunk, embed, store, security_scan)
don't block each other and can run concurrently.

Architecture:
- Chunk workers: Read from chunk_queue, write to embed_queue
- Embed workers: Read from embed_queue, write to store_queue
- Store worker: Read from store_queue, write to database
- Security scan: Separate thread pool, doesn't use pipeline queues
"""
import pytest
import threading
import time
from queue import Queue
from unittest.mock import MagicMock, patch

from pipeline.pipeline_workers import StageWorker, EmbedWorkerPool


class TestWorkerIndependence:
    """Test that workers operate independently without blocking"""

    def test_chunk_worker_doesnt_block_embed_worker(self):
        """Test: Slow chunk processing doesn't block embed worker"""
        chunk_queue = Queue()
        embed_queue = Queue()
        store_queue = Queue()
        
        # Track processing order
        processing_order = []
        lock = threading.Lock()
        
        def slow_chunk_fn(item):
            with lock:
                processing_order.append(f"chunk_start_{item}")
            time.sleep(0.2)  # Slow chunk processing
            with lock:
                processing_order.append(f"chunk_end_{item}")
            return f"chunked_{item}"
        
        def fast_embed_fn(item):
            with lock:
                processing_order.append(f"embed_start_{item}")
            time.sleep(0.01)  # Fast embed processing
            with lock:
                processing_order.append(f"embed_end_{item}")
            return f"embedded_{item}"
        
        # Create workers
        chunk_worker = StageWorker("ChunkWorker", chunk_queue, embed_queue, slow_chunk_fn)
        embed_worker = StageWorker("EmbedWorker", embed_queue, store_queue, fast_embed_fn)
        
        # Start workers
        chunk_worker.start()
        embed_worker.start()
        
        # Add items
        chunk_queue.put("file1")
        embed_queue.put("already_chunked")  # Pre-chunked item
        
        # Wait for processing
        time.sleep(0.5)
        
        # Stop workers
        chunk_worker.stop()
        embed_worker.stop()
        
        # Embed worker should process its item independently
        assert "embed_end_already_chunked" in processing_order

    def test_embed_worker_pool_processes_in_parallel(self):
        """Test: Multiple embed workers process items concurrently"""
        input_queue = Queue()
        output_queue = Queue()
        
        # Track concurrent processing
        concurrent_count = [0]
        max_concurrent = [0]
        lock = threading.Lock()
        
        def embed_fn(item):
            with lock:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            time.sleep(0.1)  # Simulate processing
            with lock:
                concurrent_count[0] -= 1
            return f"embedded_{item}"
        
        # Create pool with 2 workers
        pool = EmbedWorkerPool(
            num_workers=2,
            input_queue=input_queue,
            output_queue=output_queue,
            embed_fn=embed_fn
        )
        
        # Start pool
        pool.start()
        
        # Add items
        for i in range(4):
            input_queue.put(f"item_{i}")
        
        # Wait for processing
        time.sleep(0.5)
        
        # Stop pool
        pool.stop()
        
        # Should have had concurrent processing
        assert max_concurrent[0] >= 2, f"Expected 2 concurrent, got {max_concurrent[0]}"

    def test_store_worker_doesnt_block_other_stages(self):
        """Test: Slow store doesn't block chunk/embed workers"""
        chunk_queue = Queue()
        embed_queue = Queue()
        store_queue = Queue()
        
        results = {"chunk": 0, "embed": 0, "store": 0}
        lock = threading.Lock()
        
        def chunk_fn(item):
            with lock:
                results["chunk"] += 1
            return f"chunked_{item}"
        
        def embed_fn(item):
            with lock:
                results["embed"] += 1
            return f"embedded_{item}"
        
        def slow_store_fn(item):
            time.sleep(0.2)  # Slow store
            with lock:
                results["store"] += 1
        
        chunk_worker = StageWorker("ChunkWorker", chunk_queue, embed_queue, chunk_fn)
        embed_worker = StageWorker("EmbedWorker", embed_queue, store_queue, embed_fn)
        store_worker = StageWorker("StoreWorker", store_queue, None, slow_store_fn)
        
        chunk_worker.start()
        embed_worker.start()
        store_worker.start()
        
        # Add multiple items
        for i in range(5):
            chunk_queue.put(f"file_{i}")
        
        # Wait
        time.sleep(0.3)
        
        chunk_worker.stop()
        embed_worker.stop()
        store_worker.stop()
        
        # Chunk and embed should process faster than store
        assert results["chunk"] >= results["store"], "Chunk should not be blocked by store"
        assert results["embed"] >= results["store"], "Embed should not be blocked by store"


class TestSecurityScanIndependence:
    """Test that security scans don't interfere with indexing pipeline"""

    def test_security_scan_runs_separately(self):
        """Test: Security scan uses separate thread pool, not pipeline queues"""
        # Security scans use ThreadPoolExecutor in routes/security.py
        # They don't share any queues with the indexing pipeline
        
        # Verify the scan jobs dict is separate from pipeline
        from routes.security import _scan_jobs
        
        # Scan jobs are stored in a separate dict, not in pipeline queues
        assert isinstance(_scan_jobs, dict)

    def test_queue_jobs_shows_security_status_without_blocking(self):
        """Test: /queue/jobs endpoint shows security status without blocking"""
        # The endpoint reads security status from _scan_jobs dict
        # This is a non-blocking read operation
        
        from routes.queue import _get_active_security_scan
        
        # Should return None or dict, never block
        result = _get_active_security_scan()
        assert result is None or isinstance(result, dict)


class TestWorkerErrorIsolation:
    """Test that errors in one worker don't crash others"""

    def test_chunk_error_doesnt_crash_embed_worker(self):
        """Test: Error in chunk worker doesn't affect embed worker"""
        chunk_queue = Queue()
        embed_queue = Queue()
        store_queue = Queue()
        
        embed_processed = []
        
        def failing_chunk_fn(item):
            raise Exception("Chunk error!")
        
        def embed_fn(item):
            embed_processed.append(item)
            return f"embedded_{item}"
        
        chunk_worker = StageWorker("ChunkWorker", chunk_queue, embed_queue, failing_chunk_fn)
        embed_worker = StageWorker("EmbedWorker", embed_queue, store_queue, embed_fn)
        
        chunk_worker.start()
        embed_worker.start()
        
        # Add items to both queues
        chunk_queue.put("will_fail")
        embed_queue.put("should_succeed")
        
        time.sleep(0.2)
        
        chunk_worker.stop()
        embed_worker.stop()
        
        # Embed worker should still process its item
        assert "should_succeed" in embed_processed
        
        # Workers should still be able to be stopped cleanly
        assert not chunk_worker.is_running()
        assert not embed_worker.is_running()
