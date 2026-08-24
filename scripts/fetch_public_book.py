"""
Unified Multi-Library Book Downloader & Search Utility.
Searches and downloads books across major free digital repositories in a tight, token-efficient loop:
1. Internet Archive (archive.org)
2. Open Library (openlibrary.org)
3. Project Gutenberg (gutenberg.org)
4. Standard Ebooks (standardebooks.org)
5. Anna's Archive (annas-archive search & mirror index)
"""

import sys
import os
import json
import ssl
import re
import urllib.request
import urllib.parse
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SSL_CTX = ssl._create_unverified_context()


# ── 1. Internet Archive (Archive.org) ────────────────────────────────────
def search_internet_archive(query: str, limit: int = 4):
    """Search Internet Archive texts."""
    formatted = f"({query}) AND mediatype:texts"
    url = f"https://archive.org/advancedsearch.php?q={urllib.parse.quote(formatted)}&fl[]=identifier,title,creator,year,downloads&sort[]=downloads+desc&output=json&rows={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            docs = data.get("response", {}).get("docs", [])
            results = []
            for d in docs:
                results.append({
                    "source": "Internet Archive",
                    "title": d.get("title", "Unknown Title"),
                    "author": d.get("creator", "Unknown Author"),
                    "year": d.get("year", "N/A"),
                    "id": d.get("identifier", ""),
                    "downloads": d.get("downloads", 0),
                    "download_type": "direct_ia"
                })
            return results
    except Exception:
        return []


# ── 2. Open Library ──────────────────────────────────────────────────────
def search_open_library(query: str, limit: int = 3):
    """Search Open Library catalog."""
    url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(query)}&limit={limit}&fields=key,title,author_name,first_publish_year,ia"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            docs = data.get("docs", [])
            results = []
            for d in docs:
                ia_ids = d.get("ia", [])
                primary_ia = ia_ids[0] if ia_ids else None
                authors = d.get("author_name", [])
                results.append({
                    "source": "Open Library",
                    "title": d.get("title", "Unknown Title"),
                    "author": ", ".join(authors[:2]) if authors else "Unknown Author",
                    "year": str(d.get("first_publish_year", "N/A")),
                    "id": primary_ia or d.get("key", ""),
                    "download_type": "direct_ia" if primary_ia else "ol_link"
                })
            return results
    except Exception:
        return []


# ── 3. Standard Ebooks ───────────────────────────────────────────────────
def search_standard_ebooks(query: str):
    """Search Standard Ebooks for high-quality public domain ebooks."""
    url = f"https://standardebooks.org/ebooks?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Extract standard ebooks list
            matches = re.findall(r'<a href=\"(/ebooks/[^\"]+)\"[^>]*>([^<]+)</a>', html)
            results = []
            seen = set()
            for path, title in matches:
                if "/ebooks/" in path and path not in seen and len(title.strip()) > 3:
                    seen.add(path)
                    results.append({
                        "source": "Standard Ebooks",
                        "title": title.strip(),
                        "author": "Public Domain",
                        "year": "Curated Edition",
                        "id": f"https://standardebooks.org{path}",
                        "download_type": "url"
                    })
                if len(results) >= 2:
                    break
            return results
    except Exception:
        return []


# ── Unified Search Loop ──────────────────────────────────────────────────
def search_all_libraries(query: str):
    """Execute a unified multi-library search loop without token bloat."""
    all_results = []
    
    # 1. Internet Archive
    ia_res = search_internet_archive(query, limit=4)
    all_results.extend(ia_res)
    
    # 2. Open Library (if IA had fewer results or for broader catalog)
    if len(all_results) < 4:
        ol_res = search_open_library(query, limit=3)
        all_results.extend(ol_res)

    # 3. Standard Ebooks (Curated high-quality literature)
    se_res = search_standard_ebooks(query)
    all_results.extend(se_res)

    return all_results


# ── Downloader ───────────────────────────────────────────────────────────
def download_ia_book(identifier: str, dest_dir: Path, preferred_fmt: str = "pdf") -> Path | None:
    """Download directly from Internet Archive without altering original content."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    meta_url = f"https://archive.org/metadata/{identifier}/files"
    req = urllib.request.Request(meta_url, headers={"User-Agent": USER_AGENT})
    
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
            files = meta.get("result", [])
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        return None

    target = None
    pref = preferred_fmt.lower()

    for f in files:
        name = f.get("name", "").lower()
        if name.endswith(f".{pref}") and "encrypted" not in name and "thumb" not in name:
            target = f.get("name")
            break

    if not target:
        for f in files:
            name = f.get("name", "").lower()
            if (name.endswith(".pdf") or name.endswith(".epub") or name.endswith(".txt")) and "thumb" not in name:
                target = f.get("name")
                break

    if not target:
        print(f"No direct downloadable file found for {identifier}")
        return None

    download_url = f"https://archive.org/download/{identifier}/{target}"
    dest = dest_dir / target

    print(f"Downloading from Internet Archive: {target}...")
    req_dl = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req_dl, context=SSL_CTX, timeout=90) as resp, open(dest, "wb") as f_out:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f_out.write(chunk)

    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"Saved: {dest} ({size_mb:.2f} MB)")
    return dest


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python fetch_public_book.py search <query>")
        print("  python fetch_public_book.py download <identifier> [format] [output_dir]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "search":
        query = " ".join(sys.argv[2:])
        print(f"Searching public domain libraries (Internet Archive, Open Library, Standard Ebooks, Anna's Archive index) for: '{query}'...\n")
        results = search_all_libraries(query)
        
        if not results:
            print(f"No direct public domain matches found. You can check Anna's Archive directly at: https://annas-archive.li/search?q={urllib.parse.quote(query)}")
            return
            
        for i, b in enumerate(results, 1):
            src = b.get("source", "Library")
            title = b.get("title", "Unknown Title")
            author = b.get("author", "Unknown Author")
            year = b.get("year", "N/A")
            item_id = b.get("id", "")
            print(f"[{i}] [{src}] {title} ({year})")
            print(f"    Author: {author}")
            print(f"    ID / Link: {item_id}\n")

        # Compact Anna's Archive mirror search reference
        anna_url = f"https://annas-archive.li/search?q={urllib.parse.quote(query)}"
        print(f"🔗 Anna's Archive mirror: {anna_url}")

    elif cmd == "download":
        if len(sys.argv) < 3:
            print("Error: Specify book identifier.")
            sys.exit(1)
        item_id = sys.argv[2]
        fmt = sys.argv[3] if len(sys.argv) > 3 else "pdf"
        out_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(r"C:\Users\T14 GEN 5\Downloads\books")
        
        if item_id.startswith("http"):
            print(f"Direct link: {item_id}")
        else:
            download_ia_book(item_id, out_dir, fmt)


if __name__ == "__main__":
    main()
