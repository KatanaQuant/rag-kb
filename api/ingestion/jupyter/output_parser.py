

from typing import List, Dict

class NotebookOutputParser:
    """Parse notebook cell outputs (text, images, errors)

    Single Responsibility: Parse outputs from notebook cells

    Extracted from JupyterExtractor._parse_outputs (CC 17)
    Refactored to reduce complexity from C(18) to A.

    Handles multiple output types:
    - stream (stdout/stderr)
    - execute_result (execution outputs)
    - display_data (rich displays)
    - error (tracebacks)
    """

    @staticmethod
    def parse_outputs(outputs: List) -> List[Dict]:
        """Parse cell outputs (text, images, errors)

        Args:
            outputs: List of notebook output objects

        Returns:
            List of parsed output dictionaries
        """
        return [NotebookOutputParser._parse_single_output(output) for output in outputs]

    @staticmethod
    def _parse_single_output(output) -> Dict:
        """Parse a single output object"""
        output_dict = {'output_type': output.output_type}

        if output.output_type == 'stream':
            NotebookOutputParser._parse_stream_output(output, output_dict)
        elif output.output_type in ('execute_result', 'display_data'):
            NotebookOutputParser._parse_data_output(output, output_dict)
        elif output.output_type == 'error':
            NotebookOutputParser._parse_error_output(output, output_dict)

        return output_dict

    @staticmethod
    def _parse_stream_output(output, output_dict: Dict):
        """Parse stream output (stdout/stderr)"""
        text = output.text if isinstance(output.text, str) else ''.join(output.text)
        output_dict['text'] = text
        output_dict['stream_name'] = output.name

    @staticmethod
    def _parse_data_output(output, output_dict: Dict):
        """Parse execution result or display data"""
        data = output.data if hasattr(output, 'data') else {}
        NotebookOutputParser._extract_text_data(data, output_dict)
        NotebookOutputParser._extract_image_data(data, output_dict)
        NotebookOutputParser._extract_html_data(data, output_dict)

    @staticmethod
    def _extract_text_data(data: Dict, output_dict: Dict):
        """Extract text/plain output"""
        if 'text/plain' in data:
            text = data['text/plain']
            output_dict['text'] = text if isinstance(text, str) else ''.join(text)

    @staticmethod
    def _extract_image_data(data: Dict, output_dict: Dict):
        """Extract image output metadata (don't include base64)"""
        if 'image/png' in data:
            output_dict['has_image'] = True
            output_dict['image_type'] = 'png'
            output_dict['image_size_bytes'] = len(data['image/png'])
        elif 'image/jpeg' in data:
            output_dict['has_image'] = True
            output_dict['image_type'] = 'jpeg'
            output_dict['image_size_bytes'] = len(data['image/jpeg'])

    @staticmethod
    def _extract_html_data(data: Dict, output_dict: Dict):
        """Extract HTML/DataFrame output"""
        if 'text/html' in data:
            output_dict['has_html'] = True

    @staticmethod
    def _parse_error_output(output, output_dict: Dict):
        """Parse error traceback"""
        traceback = output.traceback if hasattr(output, 'traceback') else []
        output_dict['error_name'] = output.ename if hasattr(output, 'ename') else 'Error'
        output_dict['error_value'] = output.evalue if hasattr(output, 'evalue') else ''
        output_dict['traceback'] = '\n'.join(traceback) if traceback else ''
