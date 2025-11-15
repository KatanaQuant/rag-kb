#!/usr/bin/env python3
"""
Pre-download and cache all Docling models for faster startup.
Run this inside the container to populate the model cache.
"""

from docling.document_converter import DocumentConverter
from pathlib import Path
import tempfile

def cache_all_models():
    """Download and cache all Docling models"""
    print("Initializing Docling converter to download models...")

    # Create converter - this triggers model downloads
    converter = DocumentConverter()

    # Create a dummy PDF to force loading all models
    print("Creating dummy document to trigger all model downloads...")

    # Create minimal PDF content
    dummy_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    dummy_pdf.write(b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n210\n%%EOF')
    dummy_pdf.close()

    try:
        from docling.datamodel.document import DocumentConversionInput

        # Process dummy document to trigger all model loads
        input_doc = DocumentConversionInput.from_paths([Path(dummy_pdf.name)])
        result_iter = converter.convert(input_doc)
        result = next(iter(result_iter))
        _ = result.export_to_markdown()

        print("All Docling models successfully cached!")

    except Exception as e:
        print(f"Error caching models: {e}")
    finally:
        # Cleanup
        Path(dummy_pdf.name).unlink(missing_ok=True)

if __name__ == "__main__":
    cache_all_models()
