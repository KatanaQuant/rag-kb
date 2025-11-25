"""Progress reporting for indexing operations"""

class ProgressReporter:
    """Reports indexing progress at milestone points

    Sandi Metz compliance:
    - Single responsibility: progress reporting
    - Small methods (< 5 lines each)
    - Low complexity
    """

    def show_if_needed(self, idx: int, total: int, stats: dict):
        """Show progress at milestone points"""
        if self._is_milestone(idx, total):
            self._print_progress(idx, total, stats)

    def _is_milestone(self, idx: int, total: int) -> bool:
        """Check if current index is a milestone"""
        if self._is_hundred_mark(idx) or idx == total:
            return True
        return self._is_quarter_mark(idx, total)

    def _is_hundred_mark(self, idx: int) -> bool:
        """Check if index is a hundred mark"""
        return idx % 100 == 0

    def _is_quarter_mark(self, idx: int, total: int) -> bool:
        """Check if crossing a quarter mark"""
        percentage = (idx / total) * 100
        prev_percentage = ((idx - 1) / total) * 100
        return self._crossed_quarter(percentage, prev_percentage)

    def _crossed_quarter(self, curr: float, prev: float) -> bool:
        """Check if crossed 25%, 50%, or 75%"""
        return (self._crossed_threshold(curr, prev, 25) or
                self._crossed_threshold(curr, prev, 50) or
                self._crossed_threshold(curr, prev, 75))

    def _crossed_threshold(self, curr: float, prev: float, threshold: float) -> bool:
        """Check if crossed specific percentage threshold"""
        return curr >= threshold and prev < threshold

    def _print_progress(self, idx: int, total: int, stats: dict):
        """Print progress message"""
        percentage = (idx / total) * 100
        skip_msg = self._format_skip_msg(stats)
        print(f"Progress: {idx}/{total} files ({percentage:.1f}%) - {stats['indexed']} indexed{skip_msg}, {stats['chunks']} chunks")

    def _format_skip_msg(self, stats: dict) -> str:
        """Format skip message"""
        if stats['skipped'] > 0:
            return f", {stats['skipped']} skipped"
        return ""
