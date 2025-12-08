"""
Tests for LaTeX dependencies required for EPUB conversion.

These tests verify that all necessary LaTeX packages are available
in the Docker environment for Pandoc EPUB→PDF conversion.

Written using TDD approach to fix regression from Docker rebuild.

NOTE: These tests require Docker environment with texlive packages.
They are skipped when running locally.
"""
import subprocess
import pytest
from pathlib import Path


def _is_docker_environment():
    """Check if running inside Docker container."""
    return Path('/.dockerenv').exists() or Path('/run/.containerenv').exists()


# Skip all tests in this module if not running in Docker
pytestmark = pytest.mark.skipif(
    not _is_docker_environment(),
    reason="LaTeX tests require Docker environment with texlive packages"
)


class TestLaTeXPackages:
    """Test that required LaTeX packages are installed"""

    def test_soul_package_is_available(self):
        """soul.sty package should be available (required for some EPUBs)

        Regression: After docker-compose build --no-cache on 2025-11-22,
        the soul.sty package was missing, causing lets-go-further.epub
        to fail conversion with:
          ! LaTeX Error: File `soul.sty' not found.

        This package is required for text decorations (strikethrough, etc.)
        commonly used in technical books.
        """
        result = subprocess.run(
            ['kpsewhich', 'soul.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "soul.sty package not found. "
            "Install with: apt-get install texlive-latex-extra"
        )
        assert result.stdout.strip().endswith('soul.sty'), (
            f"Unexpected kpsewhich output: {result.stdout}"
        )

    def test_ulem_package_is_available(self):
        """ulem.sty package should be available (common text underlining)"""
        result = subprocess.run(
            ['kpsewhich', 'ulem.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "ulem.sty package not found. "
            "Install with: apt-get install texlive-latex-extra"
        )

    def test_booktabs_package_is_available(self):
        """booktabs.sty package should be available (professional tables)"""
        result = subprocess.run(
            ['kpsewhich', 'booktabs.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "booktabs.sty package not found. "
            "Install with: apt-get install texlive-latex-extra"
        )

    def test_longtable_package_is_available(self):
        """longtable.sty package should be available (multi-page tables)"""
        result = subprocess.run(
            ['kpsewhich', 'longtable.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "longtable.sty package not found. "
            "Install with: apt-get install texlive-latex-base"
        )

    def test_fancyvrb_package_is_available(self):
        """fancyvrb.sty package should be available (code blocks)"""
        result = subprocess.run(
            ['kpsewhich', 'fancyvrb.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "fancyvrb.sty package not found. "
            "Install with: apt-get install texlive-latex-base"
        )

    def test_graphicx_package_is_available(self):
        """graphicx.sty package should be available (images)"""
        result = subprocess.run(
            ['kpsewhich', 'graphicx.sty'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, (
            "graphicx.sty package not found. "
            "Install with: apt-get install texlive-latex-base"
        )


class TestPandocLaTeXIntegration:
    """Test that Pandoc can use LaTeX packages for EPUB conversion"""

    def test_pandoc_can_find_soul_package(self):
        """Pandoc should be able to compile LaTeX with soul package

        This is an integration test that verifies Pandoc can actually
        use the soul package during compilation.
        """
        # Create minimal LaTeX document using soul package
        minimal_tex = r"""
\documentclass{article}
\usepackage{soul}
\begin{document}
\st{strikethrough text}
\end{document}
"""

        # Try to compile with pdflatex (what Pandoc uses)
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', '-halt-on-error'],
            input=minimal_tex,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should not have compilation errors about missing soul.sty
        assert 'soul.sty' not in result.stderr or result.returncode == 0, (
            f"LaTeX cannot find soul.sty package.\n"
            f"stderr: {result.stderr}"
        )


class TestDockerEnvironment:
    """Test Docker environment has required tools"""

    def test_kpsewhich_is_available(self):
        """kpsewhich should be available (TeX file finder)"""
        result = subprocess.run(
            ['which', 'kpsewhich'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, "kpsewhich not found in PATH"

    def test_pdflatex_is_available(self):
        """pdflatex should be available (LaTeX compiler)"""
        result = subprocess.run(
            ['which', 'pdflatex'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, "pdflatex not found in PATH"

    def test_pandoc_is_available(self):
        """pandoc should be available (document converter)"""
        result = subprocess.run(
            ['which', 'pandoc'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, "pandoc not found in PATH"
