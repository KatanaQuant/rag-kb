"""Kernel language detector - extracted from JupyterExtractor

POODR Phase 2: God Class Decomposition
- Extracted from JupyterExtractor
- Single Responsibility: Map kernel names to programming languages
- Reduces JupyterExtractor complexity
"""


class KernelLanguageDetector:
    """Detect programming language from Jupyter kernel name

    Single Responsibility: Language detection

    Maps Jupyter kernel names (python3, ir, julia-1.6, etc.)
    to standardized language names for code chunking.
    """

    @staticmethod
    def detect_language(kernel_name: str) -> str:
        """Detect programming language from kernel name

        Args:
            kernel_name: Jupyter kernel name (e.g., 'python3', 'ir', 'julia-1.6')

        Returns:
            Language name for code chunking

        Examples:
            'python3' → 'python'
            'ir' → 'r'
            'julia-1.6' → 'julia'
            'unknown-kernel' → 'python' (default)
        """
        kernel_lower = kernel_name.lower()

        if 'python' in kernel_lower:
            return 'python'
        elif kernel_lower in ('ir', 'r'):  # IR is the R kernel
            return 'r'
        elif 'julia' in kernel_lower:
            return 'julia'
        elif 'javascript' in kernel_lower or 'node' in kernel_lower:
            return 'javascript'
        else:
            # Unknown kernel, default to python
            return 'python'
