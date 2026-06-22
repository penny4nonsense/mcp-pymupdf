"""Tests for mcp_pymupdf.server."""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from mcp_pymupdf.server import (
    read_pdf,
    get_page,
    get_metadata,
    _is_url,
    _get_pdf_path,
    _extract_pages,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_BYTES,
)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def make_mock_page(text: str = "Sample page text.") -> MagicMock:
    """Build a mock pymupdf page."""
    page = MagicMock()
    page.get_text.return_value = text
    return page


def make_mock_doc(
    pages: list[str] = None,
    page_count: int = None,
    metadata: dict = None,
) -> MagicMock:
    """Build a mock pymupdf document."""
    if pages is None:
        pages = ["Sample page text."]
    doc = MagicMock()
    doc.page_count = page_count if page_count is not None else len(pages)
    doc.metadata = metadata or {
        "title": "Test Paper",
        "author": "Test Author",
        "subject": "",
        "keywords": "",
        "creator": "",
        "producer": "",
        "creationDate": "2024-01-01",
    }
    doc.__getitem__ = lambda self, i: make_mock_page(pages[i] if i < len(pages) else "")
    return doc


def make_mock_response(content: bytes = b"%PDF test") -> MagicMock:
    """Build a mock requests response."""
    response = MagicMock()
    response.headers = {"content-type": "application/pdf"}
    response.raise_for_status = MagicMock()
    response.iter_content.return_value = [content]
    return response


# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

class TestConstants:
    def test_default_max_pages(self):
        assert DEFAULT_MAX_PAGES == 50

    def test_default_max_bytes(self):
        assert DEFAULT_MAX_BYTES == 200_000


# ------------------------------------------------------------------ #
# _is_url()                                                            #
# ------------------------------------------------------------------ #

class TestIsUrl:
    def test_http_is_url(self):
        assert _is_url("http://example.com/paper.pdf") is True

    def test_https_is_url(self):
        assert _is_url("https://example.com/paper.pdf") is True

    def test_local_path_is_not_url(self):
        assert _is_url("/path/to/file.pdf") is False

    def test_relative_path_is_not_url(self):
        assert _is_url("paper.pdf") is False

    def test_empty_string_is_not_url(self):
        assert _is_url("") is False


# ------------------------------------------------------------------ #
# _get_pdf_path()                                                      #
# ------------------------------------------------------------------ #

class TestGetPdfPath:
    def test_returns_path_for_existing_file(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        path, is_temp = _get_pdf_path(str(pdf))
        assert path == pdf
        assert is_temp is False

    def test_raises_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            _get_pdf_path("/nonexistent/file.pdf")

    def test_downloads_url(self):
        with patch("mcp_pymupdf.server._download_pdf") as mock_download:
            mock_download.return_value = (Path("/tmp/test.pdf"), True)
            path, is_temp = _get_pdf_path("https://example.com/paper.pdf")
        mock_download.assert_called_once_with("https://example.com/paper.pdf")
        assert is_temp is True


# ------------------------------------------------------------------ #
# _extract_pages()                                                     #
# ------------------------------------------------------------------ #

class TestExtractPages:
    def test_returns_tuple(self):
        doc = make_mock_doc(pages=["Page one.", "Page two."])
        result = _extract_pages(doc, 0, 1, DEFAULT_MAX_BYTES)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_extracts_text(self):
        doc = make_mock_doc(pages=["Hello world."])
        parts, _ = _extract_pages(doc, 0, 0, DEFAULT_MAX_BYTES)
        assert any("Hello world." in p for p in parts)

    def test_includes_page_markers(self):
        doc = make_mock_doc(pages=["Page one.", "Page two."])
        parts, _ = _extract_pages(doc, 0, 1, DEFAULT_MAX_BYTES)
        combined = "\n".join(parts)
        assert "Page 1" in combined
        assert "Page 2" in combined

    def test_truncates_at_max_bytes(self):
        doc = make_mock_doc(pages=["x" * 100, "y" * 100])
        parts, truncated = _extract_pages(doc, 0, 1, 50)
        assert truncated is True
        assert any("truncated" in p for p in parts)

    def test_skips_empty_pages(self):
        doc = make_mock_doc(pages=["", "Real content."])
        parts, _ = _extract_pages(doc, 0, 1, DEFAULT_MAX_BYTES)
        assert not any(p.strip() == "--- Page 1 ---" for p in parts)

    def test_no_truncation_when_within_limit(self):
        doc = make_mock_doc(pages=["Short text."])
        parts, truncated = _extract_pages(doc, 0, 0, DEFAULT_MAX_BYTES)
        assert truncated is False


# ------------------------------------------------------------------ #
# read_pdf()                                                           #
# ------------------------------------------------------------------ #

class TestReadPdf:
    def test_returns_string(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Page text."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf))
        assert isinstance(result, str)

    def test_includes_source(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Page text."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf))
        assert str(pdf) in result

    def test_includes_page_text(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Hello from page one."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf))
        assert "Hello from page one." in result

    def test_includes_page_count(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["p1", "p2", "p3"], page_count=3)
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf))
        assert "3" in result

    def test_respects_max_pages(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(
            pages=["Page one.", "Page two.", "Page three."],
            page_count=3
        )
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf), max_pages=1)
        assert "Page two." not in result
        assert "Page three." not in result

    def test_handles_scanned_pdf(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["", ""])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf))
        assert "scanned" in result.lower() or "image" in result.lower()

    def test_returns_error_for_missing_file(self):
        result = read_pdf("/nonexistent/file.pdf")
        assert "not found" in result.lower() or "Error" in result

    def test_handles_pymupdf_exception(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        with patch("mcp_pymupdf.server.pymupdf.open", side_effect=Exception("corrupt")):
            result = read_pdf(str(pdf))
        assert "Error" in result

    def test_closes_document(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Text."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            read_pdf(str(pdf))
        mock_doc.close.assert_called_once()

    def test_truncates_at_max_bytes(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["x" * 100, "y" * 100], page_count=2)
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = read_pdf(str(pdf), max_bytes=50)
        assert "truncated" in result

    def test_deletes_temp_file_after_url_read(self, tmp_path):
        temp_pdf = tmp_path / "downloaded.pdf"
        temp_pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Content."])
        with patch("mcp_pymupdf.server._get_pdf_path",
                   return_value=(temp_pdf, True)), \
             patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            read_pdf("https://example.com/paper.pdf")
        assert not temp_pdf.exists()


# ------------------------------------------------------------------ #
# get_page()                                                           #
# ------------------------------------------------------------------ #

class TestGetPage:
    def test_returns_string(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["One.", "Two.", "Three."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=1, end_page=2)
        assert isinstance(result, str)

    def test_returns_specified_page(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Page one.", "Page two.", "Page three."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=2, end_page=2)
        assert "Page two." in result
        assert "Page one." not in result

    def test_defaults_to_single_page(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Page one.", "Page two."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=1)
        assert "Page one." in result

    def test_returns_error_for_out_of_range_page(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["One."], page_count=1)
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=99)
        assert "does not exist" in result

    def test_includes_page_range_info(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(
            pages=["One.", "Two.", "Three."],
            page_count=3
        )
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=1, end_page=2)
        assert "1" in result
        assert "2" in result

    def test_truncates_at_max_bytes(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["x" * 100, "y" * 100], page_count=2)
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=1, end_page=2, max_bytes=50)
        assert "truncated" in result

    def test_handles_missing_file(self):
        result = get_page("/nonexistent/file.pdf", start_page=1)
        assert "not found" in result.lower() or "Error" in result

    def test_handles_pymupdf_exception(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        with patch("mcp_pymupdf.server.pymupdf.open", side_effect=Exception("error")):
            result = get_page(str(pdf), start_page=1)
        assert "Error" in result

    def test_closes_document(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Text."])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            get_page(str(pdf), start_page=1)
        mock_doc.close.assert_called_once()

    def test_handles_scanned_pages(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["", ""])
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_page(str(pdf), start_page=1, end_page=2)
        assert "scanned" in result.lower() or "image" in result.lower()

    def test_deletes_temp_file_after_url_read(self, tmp_path):
        temp_pdf = tmp_path / "downloaded.pdf"
        temp_pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(pages=["Content."])
        with patch("mcp_pymupdf.server._get_pdf_path",
                   return_value=(temp_pdf, True)), \
             patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            get_page("https://example.com/paper.pdf", start_page=1)
        assert not temp_pdf.exists()


# ------------------------------------------------------------------ #
# get_metadata()                                                       #
# ------------------------------------------------------------------ #

class TestGetMetadata:
    def test_returns_string(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc()
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert isinstance(result, str)

    def test_includes_title(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(metadata={
            "title": "My Research Paper",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
        })
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert "My Research Paper" in result

    def test_includes_author(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(metadata={
            "title": "",
            "author": "Jason Parker",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
        })
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert "Jason Parker" in result

    def test_includes_page_count(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(page_count=25)
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert "25" in result

    def test_handles_empty_metadata(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc(metadata={
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
        })
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert "No metadata available" in result

    def test_closes_document(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc()
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            get_metadata(str(pdf))
        mock_doc.close.assert_called_once()

    def test_handles_missing_file(self):
        result = get_metadata("/nonexistent/file.pdf")
        assert "not found" in result.lower() or "Error" in result

    def test_handles_pymupdf_exception(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        with patch("mcp_pymupdf.server.pymupdf.open", side_effect=Exception("corrupt")):
            result = get_metadata(str(pdf))
        assert "Error" in result

    def test_includes_source_in_output(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc()
        with patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            result = get_metadata(str(pdf))
        assert str(pdf) in result

    def test_deletes_temp_file_after_url_read(self, tmp_path):
        temp_pdf = tmp_path / "downloaded.pdf"
        temp_pdf.write_bytes(b"fake")
        mock_doc = make_mock_doc()
        with patch("mcp_pymupdf.server._get_pdf_path",
                   return_value=(temp_pdf, True)), \
             patch("mcp_pymupdf.server.pymupdf.open", return_value=mock_doc):
            get_metadata("https://example.com/paper.pdf")
        assert not temp_pdf.exists()