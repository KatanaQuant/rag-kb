# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for security REST API endpoints

Tests for:
- POST /api/security/scan - Start security scan job (non-blocking)
- GET /api/security/scan/{job_id} - Get scan job status
- GET /api/security/scan - List all scan jobs
- GET /api/security/rejected - List rejected files
- GET /api/security/quarantine - List quarantined files
- POST /api/security/quarantine/restore - Restore quarantined file
- POST /api/security/quarantine/purge - Purge old quarantined files
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import time


@pytest.fixture
def client():
    """Create test client with mocked dependencies"""
    from main import app
    client = TestClient(app)
    yield client


@pytest.fixture
def temp_kb_dir():
    """Create temporary knowledge base directory"""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


def wait_for_scan_completion(client, job_id: str, timeout: float = 5.0) -> dict:
    """Poll scan status until complete or timeout

    Args:
        client: Test client
        job_id: Scan job ID
        timeout: Max seconds to wait

    Returns:
        Final scan status response
    """
    start = time.time()
    while time.time() - start < timeout:
        response = client.get(f"/api/security/scan/{job_id}")
        data = response.json()
        if data['status'] in ('completed', 'failed'):
            return data
        time.sleep(0.1)
    return data  # Return last status on timeout


class TestSecurityScanEndpoint:
    """Test POST /api/security/scan endpoint (non-blocking with job tracking)"""

    def test_scan_returns_job_id(self, client, temp_kb_dir):
        """POST /api/security/scan should return job_id immediately"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            response = client.post("/api/security/scan")

            assert response.status_code == 200
            data = response.json()
            assert 'job_id' in data
            assert 'status' in data
            assert data['status'] == 'pending'

    def test_scan_empty_kb_returns_zero_files(self, client, temp_kb_dir):
        """Scan with no files should return zero counts when complete"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Start scan
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']

            # Wait for completion
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            assert status['result']['total_files'] == 0
            assert status['result']['clean_files'] == 0
            assert status['result']['critical_count'] == 0
            assert status['result']['warning_count'] == 0

    def test_scan_status_endpoint(self, client, temp_kb_dir):
        """GET /api/security/scan/{job_id} should return status"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Start scan
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']

            # Check status
            response = client.get(f"/api/security/scan/{job_id}")
            assert response.status_code == 200
            data = response.json()
            assert 'job_id' in data
            assert 'status' in data
            assert 'progress' in data
            assert 'total_files' in data
            assert 'message' in data

    def test_scan_status_not_found(self, client):
        """GET /api/security/scan/{job_id} should return 404 for unknown job"""
        response = client.get("/api/security/scan/nonexistent")
        assert response.status_code == 404

    def test_list_scan_jobs(self, client, temp_kb_dir):
        """GET /api/security/scan should list all jobs"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Start a scan
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']

            # List jobs
            response = client.get("/api/security/scan")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # Our job should be in the list
            job_ids = [j['job_id'] for j in data]
            assert job_id in job_ids

    def test_scan_returns_expected_structure(self, client, temp_kb_dir):
        """Scan result should have correct structure"""
        # Create test file
        test_file = temp_kb_dir / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        with patch('routes.security.default_config') as mock_config, \
             patch('pipeline.security_scanner.FileTypeValidator') as mock_validator_cls:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Mock validator to return clean result
            mock_validator = Mock()
            mock_validator.validate.return_value = Mock(
                is_valid=True,
                severity=None,
                matches=[],
                reason='',
                validation_check=''
            )
            mock_validator_cls.return_value = mock_validator

            # Start scan and wait
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            result = status['result']

            # Verify response structure
            assert 'total_files' in result
            assert 'clean_files' in result
            assert 'critical_count' in result
            assert 'warning_count' in result
            assert 'critical_findings' in result
            assert 'warning_findings' in result
            assert 'auto_quarantine' in result
            assert 'message' in result

    def test_scan_with_auto_quarantine_false(self, client, temp_kb_dir):
        """Scan with auto_quarantine=False should not quarantine"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Start scan
            response = client.post(
                "/api/security/scan",
                json={"auto_quarantine": False}
            )
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            assert status['result']['auto_quarantine'] is False

    def test_scan_with_auto_quarantine_true_default(self, client, temp_kb_dir):
        """Scan should default to auto_quarantine=True"""
        with patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Start scan
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            assert status['result']['auto_quarantine'] is True

    def test_scan_categorizes_critical_findings(self, client, temp_kb_dir):
        """Scan should categorize CRITICAL findings correctly"""
        test_file = temp_kb_dir / "malware.pdf"
        test_file.write_bytes(b"malicious content")

        from ingestion.validation_result import SecuritySeverity

        with patch('routes.security.default_config') as mock_config, \
             patch('pipeline.security_scanner.FileTypeValidator') as mock_validator_cls, \
             patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('pipeline.security_scanner.FileHasher') as mock_hasher_cls:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Mock validator to return CRITICAL result
            mock_validator = Mock()
            mock_validator.validate.return_value = Mock(
                is_valid=False,
                severity=SecuritySeverity.CRITICAL,
                matches=[],
                reason='Virus detected',
                validation_check='ClamAVStrategy'
            )
            mock_validator_cls.return_value = mock_validator

            # Mock quarantine manager
            mock_qm = Mock()
            mock_qm.quarantine_file.return_value = True
            mock_qm_cls.return_value = mock_qm

            # Mock hasher
            mock_hasher = Mock()
            mock_hasher.hash_file.return_value = 'abc123'
            mock_hasher_cls.return_value = mock_hasher

            # Start scan and wait
            response = client.post(
                "/api/security/scan",
                json={"auto_quarantine": False}  # Disable to avoid DB issues
            )
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            result = status['result']
            assert result['critical_count'] >= 1
            assert len(result['critical_findings']) >= 1
            assert result['critical_findings'][0]['severity'] == 'CRITICAL'

    def test_scan_categorizes_warning_findings(self, client, temp_kb_dir):
        """Scan should categorize WARNING findings correctly"""
        test_file = temp_kb_dir / "suspicious.pdf"
        test_file.write_bytes(b"suspicious content")

        from ingestion.validation_result import SecuritySeverity

        with patch('routes.security.default_config') as mock_config, \
             patch('pipeline.security_scanner.FileTypeValidator') as mock_validator_cls, \
             patch('pipeline.security_scanner.FileHasher') as mock_hasher_cls:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Mock validator to return WARNING result
            mock_validator = Mock()
            mock_validator.validate.return_value = Mock(
                is_valid=False,
                severity=SecuritySeverity.WARNING,
                matches=[],
                reason='YARA match',
                validation_check='YARAStrategy'
            )
            mock_validator_cls.return_value = mock_validator

            # Mock hasher
            mock_hasher = Mock()
            mock_hasher.hash_file.return_value = 'def456'
            mock_hasher_cls.return_value = mock_hasher

            # Start scan and wait
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            result = status['result']
            assert result['warning_count'] >= 1
            assert len(result['warning_findings']) >= 1
            assert result['warning_findings'][0]['severity'] == 'WARNING'


class TestRejectedFilesEndpoint:
    """Test GET /api/security/rejected endpoint"""

    def test_list_rejected_returns_list(self, client):
        """Rejected endpoint should return list"""
        with patch('routes.security.DatabaseFactory') as mock_factory, \
             patch('routes.security.default_config') as mock_config:
            mock_config.database.path = ':memory:'

            # Mock tracker to return empty list
            mock_tracker = Mock()
            mock_tracker.get_rejected_files.return_value = []
            mock_factory.create_progress_tracker.return_value = mock_tracker

            response = client.get("/api/security/rejected")

            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_list_rejected_with_files(self, client):
        """Rejected endpoint should return file details"""
        with patch('routes.security.DatabaseFactory') as mock_factory, \
             patch('routes.security.default_config') as mock_config:
            mock_config.database.path = ':memory:'

            # Mock rejected file
            mock_rejected = Mock()
            mock_rejected.file_path = '/app/kb/malware.pdf'
            mock_rejected.error_message = 'Validation failed (ClamAVStrategy): Virus detected'
            mock_rejected.last_updated = '2025-11-26T10:00:00'
            mock_rejected.started_at = '2025-11-26T09:00:00'

            mock_tracker = Mock()
            mock_tracker.get_rejected_files.return_value = [mock_rejected]
            mock_factory.create_progress_tracker.return_value = mock_tracker

            response = client.get("/api/security/rejected")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['filename'] == 'malware.pdf'
            assert data[0]['validation_check'] == 'ClamAVStrategy'


class TestQuarantineEndpoint:
    """Test GET /api/security/quarantine endpoint"""

    def test_list_quarantine_returns_list(self, client, temp_kb_dir):
        """Quarantine endpoint should return list"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            mock_qm = Mock()
            mock_qm.list_quarantined.return_value = []
            mock_qm_cls.return_value = mock_qm

            response = client.get("/api/security/quarantine")

            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_list_quarantine_with_files(self, client, temp_kb_dir):
        """Quarantine endpoint should return file details"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            # Mock quarantined file
            mock_quarantined = Mock()
            mock_quarantined.original_path = '/app/kb/virus.pdf'
            mock_quarantined.reason = 'Virus detected'
            mock_quarantined.validation_check = 'ClamAVStrategy'
            mock_quarantined.file_hash = 'abc123'
            mock_quarantined.quarantined_at = '2025-11-26T10:00:00'
            mock_quarantined.can_restore = True
            mock_quarantined.restored = False
            mock_quarantined.restored_at = None

            mock_qm = Mock()
            mock_qm.list_quarantined.return_value = [mock_quarantined]
            mock_qm_cls.return_value = mock_qm

            response = client.get("/api/security/quarantine")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['filename'] == 'virus.pdf.REJECTED'
            assert data[0]['validation_check'] == 'ClamAVStrategy'
            assert data[0]['can_restore'] is True


class TestQuarantineRestoreEndpoint:
    """Test POST /api/security/quarantine/restore endpoint"""

    def test_restore_success(self, client, temp_kb_dir):
        """Restore should return success for valid file"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            mock_metadata = Mock()
            mock_metadata.original_path = '/app/kb/file.pdf'

            mock_qm = Mock()
            mock_qm._read_metadata.return_value = mock_metadata
            mock_qm.restore_file.return_value = True
            mock_qm_cls.return_value = mock_qm

            response = client.post(
                "/api/security/quarantine/restore",
                json={"filename": "file.pdf.REJECTED", "force": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['message'] == 'File restored successfully'

    def test_restore_not_found(self, client, temp_kb_dir):
        """Restore should return 404 for missing file"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            mock_qm = Mock()
            mock_qm._read_metadata.return_value = None
            mock_qm_cls.return_value = mock_qm

            response = client.post(
                "/api/security/quarantine/restore",
                json={"filename": "nonexistent.pdf.REJECTED", "force": False}
            )

            assert response.status_code == 404


class TestQuarantinePurgeEndpoint:
    """Test POST /api/security/quarantine/purge endpoint"""

    def test_purge_dry_run(self, client, temp_kb_dir):
        """Purge with dry_run should not delete"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            mock_qm = Mock()
            mock_qm.purge_old_files.return_value = 5
            mock_qm_cls.return_value = mock_qm

            response = client.post(
                "/api/security/quarantine/purge",
                json={"older_than_days": 30, "dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['files_purged'] == 5
            assert data['dry_run'] is True
            assert 'Would purge' in data['message']

    def test_purge_actual(self, client, temp_kb_dir):
        """Purge without dry_run should delete"""
        with patch('routes.security.QuarantineManager') as mock_qm_cls, \
             patch('routes.security.default_config') as mock_config:
            mock_config.paths.knowledge_base = str(temp_kb_dir)

            mock_qm = Mock()
            mock_qm.purge_old_files.return_value = 3
            mock_qm_cls.return_value = mock_qm

            response = client.post(
                "/api/security/quarantine/purge",
                json={"older_than_days": 30, "dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['files_purged'] == 3
            assert data['dry_run'] is False
            assert 'Purged' in data['message']


class TestSecurityFindingResponse:
    """Test SecurityFinding response model"""

    def test_finding_has_all_fields(self, client, temp_kb_dir):
        """Security findings should have all expected fields"""
        test_file = temp_kb_dir / "test.pdf"
        test_file.write_bytes(b"test")

        from ingestion.validation_result import SecuritySeverity, SecurityMatch

        with patch('routes.security.default_config') as mock_config, \
             patch('pipeline.security_scanner.FileTypeValidator') as mock_validator_cls, \
             patch('pipeline.security_scanner.FileHasher') as mock_hasher_cls:
            mock_config.paths.knowledge_base = str(temp_kb_dir)
            mock_config.database.path = ':memory:'

            # Mock validator with matches
            mock_match = Mock()
            mock_match.rule_name = 'TestRule'
            mock_match.severity = SecuritySeverity.WARNING
            mock_match.context = 'test context'

            mock_validator = Mock()
            mock_validator.validate.return_value = Mock(
                is_valid=False,
                severity=SecuritySeverity.WARNING,
                matches=[mock_match],
                reason='Test reason',
                validation_check='TestStrategy'
            )
            mock_validator_cls.return_value = mock_validator

            mock_hasher = Mock()
            mock_hasher.hash_file.return_value = 'abc123def456'
            mock_hasher_cls.return_value = mock_hasher

            # Start scan and wait
            response = client.post("/api/security/scan")
            job_id = response.json()['job_id']
            status = wait_for_scan_completion(client, job_id)

            assert status['status'] == 'completed'
            result = status['result']

            if result['warning_findings']:
                finding = result['warning_findings'][0]
                assert 'file_path' in finding
                assert 'filename' in finding
                assert 'severity' in finding
                assert 'reason' in finding
                assert 'validation_check' in finding
                assert 'file_hash' in finding
                assert 'matches' in finding
