

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

        if KernelLanguageDetector._is_python(kernel_lower):
            return 'python'
        if KernelLanguageDetector._is_r(kernel_lower):
            return 'r'
        if KernelLanguageDetector._is_julia(kernel_lower):
            return 'julia'
        if KernelLanguageDetector._is_javascript(kernel_lower):
            return 'javascript'
        return 'python'  # Default for unknown kernels

    @staticmethod
    def _is_python(kernel_lower: str) -> bool:
        """Check if kernel is Python"""
        return 'python' in kernel_lower

    @staticmethod
    def _is_r(kernel_lower: str) -> bool:
        """Check if kernel is R"""
        return kernel_lower in ('ir', 'r')

    @staticmethod
    def _is_julia(kernel_lower: str) -> bool:
        """Check if kernel is Julia"""
        return 'julia' in kernel_lower

    @staticmethod
    def _is_javascript(kernel_lower: str) -> bool:
        """Check if kernel is JavaScript"""
        return 'javascript' in kernel_lower or 'node' in kernel_lower
