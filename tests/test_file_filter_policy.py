"""Tests for FileFilterPolicy - Test-Driven Development"""
import pytest
from pathlib import Path
from ingestion.file_filter import FileFilterPolicy


class TestFileFilterPolicy:
    """Test file filtering logic extracted from FileWalker"""

    @pytest.fixture
    def policy(self):
        """Create policy instance"""
        return FileFilterPolicy()

    def test_excludes_git_directory(self, policy):
        """Should exclude .git directories"""
        path = Path("/project/.git/config")
        assert policy.should_exclude(path) is True

    def test_excludes_node_modules(self, policy):
        """Should exclude node_modules"""
        path = Path("/project/node_modules/package/index.js")
        assert policy.should_exclude(path) is True

    def test_excludes_pycache(self, policy):
        """Should exclude __pycache__"""
        path = Path("/project/src/__pycache__/module.pyc")
        assert policy.should_exclude(path) is True

    def test_excludes_venv(self, policy):
        """Should exclude virtual environments"""
        assert policy.should_exclude(Path("/project/venv/lib/python.py")) is True
        assert policy.should_exclude(Path("/project/.venv/bin/activate")) is True
        assert policy.should_exclude(Path("/project/env/site-packages")) is True

    def test_excludes_build_artifacts(self, policy):
        """Should exclude build directories"""
        assert policy.should_exclude(Path("/project/dist/bundle.js")) is True
        assert policy.should_exclude(Path("/project/build/output")) is True
        assert policy.should_exclude(Path("/java/target/classes")) is True

    def test_excludes_ide_directories(self, policy):
        """Should exclude IDE config directories"""
        assert policy.should_exclude(Path("/project/.idea/workspace.xml")) is True
        assert policy.should_exclude(Path("/project/.vscode/settings.json")) is True
        assert policy.should_exclude(Path("/project/.vs/config")) is True

    def test_excludes_env_files(self, policy):
        """Should exclude environment files"""
        assert policy.should_exclude(Path("/project/.env")) is True
        assert policy.should_exclude(Path("/project/.env.local")) is True
        assert policy.should_exclude(Path("/project/.env.production")) is True

    def test_excludes_compiled_files(self, policy):
        """Should exclude compiled binaries"""
        assert policy.should_exclude(Path("/project/module.pyc")) is True
        assert policy.should_exclude(Path("/project/lib.so")) is True
        assert policy.should_exclude(Path("/project/app.dll")) is True
        assert policy.should_exclude(Path("/java/Main.class")) is True

    def test_excludes_minified_assets(self, policy):
        """Should exclude minified JS/CSS"""
        assert policy.should_exclude(Path("/assets/bundle.min.js")) is True
        assert policy.should_exclude(Path("/styles/app.min.css")) is True

    def test_excludes_secrets_files(self, policy):
        """Should exclude files with 'secrets' or 'credentials' in name"""
        assert policy.should_exclude(Path("/config/secrets.json")) is True
        assert policy.should_exclude(Path("/auth/credentials.yaml")) is True

    def test_excludes_os_artifacts(self, policy):
        """Should exclude OS-specific files"""
        assert policy.should_exclude(Path("/folder/.DS_Store")) is True
        assert policy.should_exclude(Path("/folder/Thumbs.db")) is True

    def test_excludes_problematic_directory(self, policy):
        """Should exclude 'problematic' subdirectory"""
        path = Path("/knowledge_base/problematic/bad_file.pdf")
        assert policy.should_exclude(path) is True

    def test_excludes_original_directory(self, policy):
        """Should exclude 'original' subdirectory"""
        path = Path("/knowledge_base/original/backup.epub")
        assert policy.should_exclude(path) is True

    def test_excludes_temp_pdf_files(self, policy):
        """Should exclude temporary PDF files created during processing"""
        assert policy.should_exclude(Path("/docs/file.tmp.pdf")) is True
        assert policy.should_exclude(Path("/docs/file.gs_tmp.pdf")) is True

    def test_allows_regular_python_file(self, policy):
        """Should allow regular source files"""
        path = Path("/project/src/main.py")
        assert policy.should_exclude(path) is False

    def test_allows_regular_pdf(self, policy):
        """Should allow regular PDFs"""
        path = Path("/documents/report.pdf")
        assert policy.should_exclude(path) is False

    def test_allows_markdown_file(self, policy):
        """Should allow markdown files"""
        path = Path("/docs/README.md")
        assert policy.should_exclude(path) is False

    def test_allows_nested_source_files(self, policy):
        """Should allow deeply nested source files"""
        path = Path("/project/src/components/ui/Button.tsx")
        assert policy.should_exclude(path) is False

    def test_dot_files_excluded_except_dotdot(self, policy):
        """Should exclude hidden files starting with dot (except ..)"""
        assert policy.should_exclude(Path("/project/.hidden_file")) is True
        # .. should not be excluded (it's a navigation element)
        # Note: This test verifies the existing behavior

    def test_excludes_go_vendor_directory(self, policy):
        """Should exclude Go vendor directory"""
        assert policy.should_exclude(Path("/project/vendor/github.com/pkg/errors")) is True

    def test_excludes_go_dependency_files(self, policy):
        """Should exclude Go dependency management files"""
        assert policy.should_exclude(Path("/project/go.mod")) is True
        assert policy.should_exclude(Path("/project/go.sum")) is True

    def test_excludes_go_workspace_files(self, policy):
        """Should exclude Go workspace files"""
        assert policy.should_exclude(Path("/project/go.work")) is True
        assert policy.should_exclude(Path("/project/go.work.sum")) is True

    def test_excludes_go_binaries(self, policy):
        """Should exclude compiled Go binaries"""
        assert policy.should_exclude(Path("/project/myapp.exe")) is True

    def test_allows_go_source_files(self, policy):
        """Should allow Go source files"""
        assert policy.should_exclude(Path("/project/main.go")) is False
        assert policy.should_exclude(Path("/project/pkg/server/server.go")) is False
