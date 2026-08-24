---
name: public-library-books
description: "Search and download free public domain and open-access books across digital libraries (Internet Archive, Open Library, Standard Ebooks, Anna's Archive). Use when a user asks to find, look up, download, or fetch a book. Runs in a token-efficient loop and presents original book files directly without unnecessary OCR or reconstruction."
compatibility: "All platforms"
license: MIT
---

# Multi-Library Public Books Fetcher

## Architecture & Principles
1. **Multi-Source Library Loop**:
   - **Internet Archive**: Over 40 million texts, scans, public domain editions.
   - **Open Library**: Catalog cross-indexing millions of works with borrow/download identifiers.
   - **Standard Ebooks**: Curated, beautifully typeset classical public domain ebooks.
   - **Anna's Archive**: Meta-search engine indexing open books, papers, and archive backups.
2. **Token Efficiency**: Returns compact, structured 3–5 line search summaries (<150 tokens) instead of multi-megabyte JSON context bloat.
3. **Direct Presentation**: Downloads and serves the original book files directly (PDF, EPUB, TXT). **Never triggers OCR or reconstruction** unless specifically asked.

## Usage

### 1. Multi-Library Search
```bash
python scripts/fetch_public_book.py search "<title / author / keywords>"
```

### 2. Direct Download & Present
```bash
python scripts/fetch_public_book.py download <identifier> [format] [output_dir]
```
- `identifier`: The book ID returned from search.
- `format`: `pdf` (default), `epub`, or `txt`.
- `output_dir`: Defaults to `C:\Users\T14 GEN 5\Downloads\books`.

### 3. Agent Protocol
1. Run search via `fetch_public_book.py search "<query>"`.
2. Present the top matches concisely with source names and IDs.
3. Download the requested title and give the user the direct clickable local path.
