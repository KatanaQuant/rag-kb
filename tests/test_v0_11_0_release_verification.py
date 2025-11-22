"""
Verify all features from v0.11.0-alpha release are implemented
"""
import pytest
from pathlib import Path
import re


class TestGoLanguageSupport:
    """Verify Go language support is implemented"""

    def test_go_chunker_exists(self):
        """Test that GoChunker class exists"""
        go_chunker_path = Path(__file__).parent.parent / "api" / "ingestion" / "go_chunker.py"
        assert go_chunker_path.exists(), "go_chunker.py not found"

        content = go_chunker_path.read_text()
        assert "class GoChunker" in content, "GoChunker class not found"

    def test_go_file_filtering(self):
        """Test that Go file filtering is implemented"""
        file_filter_path = Path(__file__).parent.parent / "api" / "ingestion" / "file_filter.py"
        content = file_filter_path.read_text()

        # Check for Go-specific exclusions
        assert "vendor" in content, "vendor/ filtering not found"
        assert "go.mod" in content or "go.sum" in content, "Go module file filtering not found"


class TestModularArchitecture:
    """Verify modular architecture refactoring"""

    def test_extracted_services_exist(self):
        """Test that all 9 extracted service modules exist"""
        services_dir = Path(__file__).parent.parent / "api" / "api_services"
        assert services_dir.exists(), "api_services directory not found"

        required_services = [
            "model_loader.py",
            "file_walker.py",
            "document_indexer.py",
            "index_orchestrator.py",
            "query_executor.py",
            "orphan_detector.py",
            "document_lister.py",
            "document_searcher.py"
        ]

        for service in required_services:
            service_path = services_dir / service
            assert service_path.exists(), f"{service} not found in api_services/"

    def test_startup_manager_exists(self):
        """Test that StartupManager module exists"""
        startup_path = Path(__file__).parent.parent / "api" / "startup" / "manager.py"
        assert startup_path.exists(), "startup/manager.py not found"

        content = startup_path.read_text()
        assert "class StartupManager" in content, "StartupManager class not found"


class TestConcurrentProcessing:
    """Verify concurrent processing pipeline"""

    def test_pipeline_coordinator_exists(self):
        """Test that PipelineCoordinator exists"""
        pipeline_path = Path(__file__).parent.parent / "api" / "services" / "pipeline_coordinator.py"
        assert pipeline_path.exists(), "pipeline_coordinator.py not found"

        content = pipeline_path.read_text()
        assert "PipelineCoordinator" in content, "PipelineCoordinator not found"

    def test_worker_classes_exist(self):
        """Test that worker classes exist"""
        workers_path = Path(__file__).parent.parent / "api" / "services" / "pipeline_workers.py"
        assert workers_path.exists(), "pipeline_workers.py not found"

        content = workers_path.read_text()
        # Implementation uses StageWorker generic class instead of separate worker classes
        assert "StageWorker" in content, "StageWorker not found"
        assert "EmbedWorkerPool" in content, "EmbedWorkerPool not found"

    def test_pipeline_coordinator_has_three_stages(self):
        """Test that PipelineCoordinator sets up all 3 stages"""
        coord_path = Path(__file__).parent.parent / "api" / "services" / "pipeline_coordinator.py"
        content = coord_path.read_text()

        # Check for chunk, embed, and store stages
        assert "chunk_pool" in content or "_chunk_stage" in content, "Chunk stage not found"
        assert "embed_pool" in content or "_embed_stage" in content, "Embed stage not found"
        assert "store_worker" in content or "_store_stage" in content, "Store stage not found"


class TestConfiguration:
    """Verify configuration options"""

    def test_worker_configuration_in_env(self):
        """Test that worker configuration is documented"""
        env_example_path = Path(__file__).parent.parent / ".env.example"

        if env_example_path.exists():
            content = env_example_path.read_text()
            assert "CHUNK_WORKERS" in content or "EMBED_WORKERS" in content, \
                "Worker configuration not in .env.example"

    def test_docker_compose_has_worker_config(self):
        """Test that docker-compose.yml has worker environment variables"""
        docker_compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        content = docker_compose_path.read_text()

        assert "EMBEDDING_WORKERS" in content or "EMBED_WORKERS" in content, \
            "EMBED_WORKERS not in docker-compose.yml"


class TestPriorityQueue:
    """Verify priority-based queue system"""

    def test_priority_enum_exists(self):
        """Test that Priority enum exists"""
        services_path = Path(__file__).parent.parent / "api" / "services"

        # Check for Priority in services module
        for py_file in services_path.glob("*.py"):
            content = py_file.read_text()
            if "class Priority" in content or "Priority.HIGH" in content:
                return

        pytest.fail("Priority enum not found in services module")


class TestAPIEndpoints:
    """Verify new API endpoints exist"""

    def test_main_has_queue_jobs_endpoint(self):
        """Test that /queue/jobs endpoint exists"""
        main_path = Path(__file__).parent.parent / "api" / "main.py"
        content = main_path.read_text()

        assert '/queue/jobs' in content or 'queue/jobs' in content, \
            "/queue/jobs endpoint not found"

    def test_main_has_pause_resume_endpoints(self):
        """Test that pause/resume endpoints exist"""
        main_path = Path(__file__).parent.parent / "api" / "main.py"
        content = main_path.read_text()

        assert '/indexing/pause' in content or 'indexing/pause' in content, \
            "/indexing/pause endpoint not found"
        assert '/indexing/resume' in content or 'indexing/resume' in content, \
            "/indexing/resume endpoint not found"

    def test_main_has_orphan_repair_endpoint(self):
        """Test that orphan repair endpoint exists"""
        main_path = Path(__file__).parent.parent / "api" / "main.py"
        content = main_path.read_text()

        # Could be /orphans/repair or /repair-orphans
        assert '/orphans/repair' in content or 'repair-orphans' in content, \
            "Orphan repair endpoint not found"
