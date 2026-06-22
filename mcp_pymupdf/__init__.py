"""
mcp-pymupdf
-----------
MCP server for reading PDFs using PyMuPDF.

Exposes three tools:
    read_pdf     — extract text from a PDF (local path or URL)
    get_page     — extract text from a specific page range
    get_metadata — retrieve PDF metadata without reading full text
"""

__version__ = "0.1.0"
__author__ = "Jason Parker"
__license__ = "MIT"