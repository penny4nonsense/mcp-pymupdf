"""
mcp_pymupdf.server
------------------
MCP server exposing PDF reading tools via PyMuPDF.

Tools:
    read_pdf     — extract text from a PDF (local path or URL)
    get_page     — extract text from a specific page range
    get_metadata — retrieve PDF metadata without reading full text

Run with:
    python -m mcp_pymupdf.server
    or
    mcp-pymupdf
"""

import os
import tempfile
from pathlib import Path

import pymupdf
import requests
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("mcp-pymupdf")

DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_BYTES = 200_000
DOWNLOAD_TIMEOUT = 30


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _is_url(source: str) -> bool:
    """Check if source is a URL."""
    return source.startswith("http://") or source.startswith("https://")


def _download_pdf(url: str) -> tuple[Path, bool]:
    """Download a PDF from a URL to a temp file."""
    response = requests.get(
        url,
        timeout=DOWNLOAD_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0"},
        stream=True,
    )
    response.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        for chunk in response.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        return Path(tmp.name), True
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise


def _get_pdf_path(source: str) -> tuple[Path, bool]:
    """
    Resolve source to a local path, downloading if necessary.

    Returns:
        Tuple of (path, is_temp) where is_temp indicates
        the file should be deleted after use.
    """
    if _is_url(source):
        return _download_pdf(source)
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {source}")
    return path, False


def _extract_pages(
    doc: pymupdf.Document,
    start_idx: int,
    end_idx: int,
    max_bytes: int,
) -> tuple[list[str], bool]:
    """
    Extract text from a range of pages.

    Returns:
        Tuple of (text_parts, truncated).
    """
    text_parts = []
    total_chars = 0
    truncated = False

    for i in range(start_idx, end_idx + 1):
        page = doc[i]
        text = page.get_text()
        if not text.strip():
            continue

        page_text = f"--- Page {i + 1} ---\n{text}"
        chars = len(page_text.encode("utf-8"))

        if total_chars + chars > max_bytes:
            text_parts.append(f"\n... [truncated at {max_bytes} bytes]")
            truncated = True
            break

        text_parts.append(page_text)
        total_chars += chars

    return text_parts, truncated


# ------------------------------------------------------------------ #
# Tools                                                                #
# ------------------------------------------------------------------ #

@mcp.tool()
def read_pdf(
    source: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """
    Extract text from a PDF file or URL.

    Reads up to max_pages pages and max_bytes bytes of content.
    Scanned or image-based PDFs will be flagged as unreadable.

    Args:
        source: Local file path or URL to the PDF.
        max_pages: Maximum number of pages to read. Defaults to 50.
        max_bytes: Maximum output size in bytes. Defaults to 200000.

    Returns:
        Extracted text with page markers, or an error message.
    """
    path, is_temp = None, False
    try:
        path, is_temp = _get_pdf_path(source)
        doc = pymupdf.open(str(path))

        total_pages = doc.page_count
        pages_to_read = min(max_pages, total_pages)

        header = [
            f"PDF: {source}",
            f"Pages: {total_pages} total, reading {pages_to_read}",
            "",
        ]

        text_parts, _ = _extract_pages(doc, 0, pages_to_read - 1, max_bytes)
        doc.close()

        if not text_parts:
            return (
                f"PDF: {source}\n"
                f"Pages: {total_pages}\n\n"
                "No text could be extracted. This PDF may be scanned or "
                "image-based. OCR would be required to read it."
            )

        return "\n".join(header + text_parts)

    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Error reading PDF: {e}"
    finally:
        if is_temp and path and path.exists():
            path.unlink()


@mcp.tool()
def get_page(
    source: str,
    start_page: int = 1,
    end_page: int | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """
    Extract text from a specific page range of a PDF.

    Pages are 1-indexed. If end_page is not specified, only
    start_page is read.

    Args:
        source: Local file path or URL to the PDF.
        start_page: First page to read (1-indexed). Defaults to 1.
        end_page: Last page to read (1-indexed, inclusive).
                  Defaults to start_page if not specified.
        max_bytes: Maximum output size in bytes. Defaults to 200000.

    Returns:
        Extracted text from the specified pages.
    """
    path, is_temp = None, False
    try:
        path, is_temp = _get_pdf_path(source)
        doc = pymupdf.open(str(path))

        total_pages = doc.page_count
        start_idx = max(0, start_page - 1)
        end_idx = min(
            (end_page if end_page else start_page) - 1,
            total_pages - 1,
        )

        if start_idx > total_pages - 1:
            doc.close()
            return (
                f"Page {start_page} does not exist. "
                f"PDF has {total_pages} pages."
            )

        header = [
            f"PDF: {source}",
            f"Pages {start_page}–{end_idx + 1} of {total_pages}",
            "",
        ]

        text_parts, _ = _extract_pages(doc, start_idx, end_idx, max_bytes)
        doc.close()

        if not text_parts:
            return (
                f"No text found on pages {start_page}–{end_idx + 1}. "
                "Pages may be scanned or image-based."
            )

        return "\n".join(header + text_parts)

    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Error reading PDF: {e}"
    finally:
        if is_temp and path and path.exists():
            path.unlink()


@mcp.tool()
def get_metadata(source: str) -> str:
    """
    Retrieve metadata from a PDF without reading its full text.

    Returns title, author, subject, keywords, creator, producer,
    creation date, and page count.

    Args:
        source: Local file path or URL to the PDF.

    Returns:
        Formatted metadata string.
    """
    path, is_temp = None, False
    try:
        path, is_temp = _get_pdf_path(source)
        doc = pymupdf.open(str(path))

        meta = doc.metadata
        total_pages = doc.page_count
        doc.close()

        lines = [f"PDF Metadata: {source}", ""]

        fields = {
            "Title": meta.get("title"),
            "Author": meta.get("author"),
            "Subject": meta.get("subject"),
            "Keywords": meta.get("keywords"),
            "Creator": meta.get("creator"),
            "Producer": meta.get("producer"),
            "Creation Date": meta.get("creationDate"),
            "Pages": total_pages,
        }

        has_meta = False
        for key, value in fields.items():
            if value and key != "Pages":
                lines.append(f"{key}: {value}")
                has_meta = True

        if not has_meta:
            lines.append("No metadata available.")

        lines.append(f"Pages: {total_pages}")
        return "\n".join(lines)

    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Error reading PDF metadata: {e}"
    finally:
        if is_temp and path and path.exists():
            path.unlink()


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()