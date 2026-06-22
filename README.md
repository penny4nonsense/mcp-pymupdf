# mcp-pymupdf

An MCP server for reading PDFs using PyMuPDF. Supports local files and URLs.

## Installation

```bash
pip install mcp-pymupdf
```

## Tools

### `read_pdf`
Extract text from a PDF file or URL.

```json
{
  "source": "/path/to/file.pdf",
  "max_pages": 50,
  "max_bytes": 200000
}
```

### `get_page`
Extract text from a specific page range.

```json
{
  "source": "https://example.com/paper.pdf",
  "start_page": 3,
  "end_page": 8
}
```

### `get_metadata`
Retrieve PDF metadata without reading full text.

```json
{
  "source": "/path/to/file.pdf"
}
```

## Usage with Claude Desktop

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "pdf": {
      "command": "mcp-pymupdf"
    }
  }
}
```

## Notes

- Scanned or image-based PDFs cannot be read without OCR
- Mathematical notation may render as plain text approximations
- URLs are downloaded to a temp file and deleted after reading

## License

MIT