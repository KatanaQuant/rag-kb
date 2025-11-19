"""Notebook output parser - extracted from JupyterExtractor

POODR Phase 2: God Class Decomposition
- Extracted from JupyterExtractor (CC 17 method - highest complexity!)
- Single Responsibility: Parse notebook cell outputs
- Reduces JupyterExtractor complexity
"""

from typing import List, Dict


class NotebookOutputParser:
    """Parse notebook cell outputs (text, images, errors)

    Single Responsibility: Parse outputs from notebook cells

    Extracted from JupyterExtractor._parse_outputs (CC 17)
    This was the highest complexity method in the codebase.

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
        parsed = []

        for output in outputs:
            output_dict = {'output_type': output.output_type}

            if output.output_type == 'stream':
                # stdout/stderr text
                text = output.text if isinstance(output.text, str) else ''.join(output.text)
                output_dict['text'] = text
                output_dict['stream_name'] = output.name

            elif output.output_type == 'execute_result' or output.output_type == 'display_data':
                # Execution results or display outputs
                data = output.data if hasattr(output, 'data') else {}

                # Text output
                if 'text/plain' in data:
                    text = data['text/plain']
                    output_dict['text'] = text if isinstance(text, str) else ''.join(text)

                # Image output (preserve as metadata)
                if 'image/png' in data:
                    output_dict['has_image'] = True
                    output_dict['image_type'] = 'png'
                    # Don't include base64 data - too large. Just note it exists.
                    output_dict['image_size_bytes'] = len(data['image/png'])

                if 'image/jpeg' in data:
                    output_dict['has_image'] = True
                    output_dict['image_type'] = 'jpeg'
                    output_dict['image_size_bytes'] = len(data['image/jpeg'])

                # HTML/DataFrame output
                if 'text/html' in data:
                    output_dict['has_html'] = True

            elif output.output_type == 'error':
                # Error traceback
                traceback = output.traceback if hasattr(output, 'traceback') else []
                output_dict['error_name'] = output.ename if hasattr(output, 'ename') else 'Error'
                output_dict['error_value'] = output.evalue if hasattr(output, 'evalue') else ''
                output_dict['traceback'] = '\n'.join(traceback) if traceback else ''

            parsed.append(output_dict)

        return parsed
