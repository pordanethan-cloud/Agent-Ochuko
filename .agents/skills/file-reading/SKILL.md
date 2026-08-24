---
name: file-reading
description: "Use this skill when a file has been uploaded but its content is NOT in your context — only its path at /mnt/user-data/uploads/ or local upload path is listed. This skill is a router: it tells you which tool to use for each file type (pdf, docx, xlsx, csv, json, images, archives, ebooks) so you read the right amount the right way instead of blindly running cat on a binary. Triggers: any mention of /mnt/user-data/uploads/, an uploaded_files section, a file_path tag, or a user asking about an uploaded file you have not yet read. Do NOT use this skill if the file content is already visible in your context inside a documents block — you already have it."
compatibility: "claude.ai, Claude Desktop, Cowork, Antigravity — any surface handling file uploads"
license: Proprietary. LICENSE.txt has complete terms
---

# Reading Uploaded Files

## Why this skill exists

When a user uploads a file, the file is written to disk (e.g. `/mnt/user-data/uploads/<filename>` or local workspace path) and you are told the path in an `<uploaded_files>` block or path reference. **The content is not in your context.**
You must go read it.

The naive thing — `cat /path/to/uploaded/file` — is wrong for most files:

- On a PDF it prints binary garbage.
- On a 100MB CSV it floods your context with rows you will never use.
- On a DOCX it prints the raw ZIP bytes.
- On an image it does nothing useful at all.

This skill tells you the right first move for each type, and when to hand off to a deeper skill.

## General protocol

1. **Look at the extension.** That is your dispatch key.
2. **Stat before you read.** Large files need sampling, not slurping.
   ```bash
   stat -c '%s bytes, %y' /path/to/uploads/report.pdf
   file /path/to/uploads/report.pdf
   ```
3. **Read just enough to answer the user's question.** If they asked "how many rows are in this CSV", don't load the whole thing into pandas — `wc -l` gives a fast approximation (it counts newlines, not CSV records, so it may over-count if quoted fields contain embedded newlines).
4. **If a dedicated skill exists, go read it.** The table below tells you when. The dedicated skills cover editing, creating, and advanced operations that this skill does not.

## `extract-text`

For docx, odt, epub, xlsx, pptx, rtf, and ipynb the first move is `extract-text <file>`. It emits markdown for docx/odt/epub (headings, bold, lists, links, tables), tab-separated rows under `## Sheet:` headers for xlsx, text under `## Slide N` headers for pptx, fenced code cells for ipynb, and plain text for rtf. Pass `--format <fmt>` when the extension is wrong or absent (e.g., `--format xlsx` on an `.xlsm`). If it errors on a file, `pandoc <file> -t plain` is a fallback; for xlsx/pptx, fall back to the dedicated skill's Python-based approach (openpyxl / python-pptx).

## Dispatch table

Where a dedicated skill is named below, invoke it by name if you have a Skill tool, or Read its SKILL.md (listed in your available skills, or in the same skills directory as this file).

| Extension                         | First move                                           | Dedicated skill |
| --------------------------------- | ---------------------------------------------------- | --------------- |
| `.pdf`                            | Content inventory (see PDF section)                  | `pdf` / `pdf-reading` |
| `.docx`                           | `extract-text`                                       | `docx`          |
| `.doc` (legacy)                   | Convert to `.docx` first                             | `docx`          |
| `.xlsx`                           | `extract-text`                                       | `xlsx`          |
| `.xlsm`                           | `extract-text --format xlsx`                         | `xlsx`          |
| `.xls` (legacy)                   | `pd.read_excel(engine="xlrd")` — openpyxl rejects it | `xlsx`          |
| `.ods`                            | `pd.read_excel(engine="odf")` — openpyxl rejects it  | `xlsx`          |
| `.pptx`                           | `extract-text`                                       | `pptx`          |
| `.ppt` (legacy)                   | Convert to `.pptx` first                             | `pptx`          |
| `.csv`, `.tsv`                    | `pandas` with `nrows`                                | — (below)       |
| `.json`, `.jsonl`                 | `jq` for structure                                   | — (below)       |
| `.jpg`, `.png`, `.gif`, `.webp`   | Already in your context as vision input              | — (below)       |
| `.zip`, `.tar`, `.tar.gz`         | List contents, do **not** auto-extract               | — (below)       |
| `.gz` (single file)               | `zcat \| head` — no manifest to list                 | — (below)       |
| `.epub`, `.odt`                   | `extract-text`                                       | — (below)       |
| `.rtf`                            | `extract-text`                                       | — (below)       |
| `.ipynb`                          | `extract-text`                                       | — (below)       |
| `.txt`, `.md`, `.log`, code files | `wc -c` then `head` or full `cat`                    | — (below)       |
| Unknown                           | `file` then decide                                   | —               |

---

## PDF

**Never** `cat` a PDF — it prints binary garbage.

Quick first move — get the page count and determine whether the PDF has an extractable text layer:

```bash
pdfinfo /path/to/uploads/report.pdf
pdffonts /path/to/uploads/report.pdf
```

`pdffonts` tells you whether text extraction will work before you try it:

- **No fonts listed** (empty table, just the header) → the PDF is a scan or raster export. `pdftotext` and `PdfReader.extract_text()` will return nothing useful. Go straight to page rasterization or OCR — see the `pdf` skill → "Scanned documents".
- **Fonts listed** → there is a text layer; extract it:
  ```bash
  pdftotext -f 1 -l 1 /path/to/uploads/report.pdf - | head -20
  ```

The reason to check `pdffonts` first is user-facing: running `pdftotext` on a scan produces an empty result, and in a visible transcript that reads as a failed first attempt before you fall back to OCR. The two-line diagnostic above costs one tool call and avoids that — you arrive at the right method on the first try, which is what a user perceives as "it just read my file."

That also shapes how to open your reply. The diagnostic commands are plumbing, not content; lead with what the user asked about. On a scanned receipt that might be "This is a 3-page scanned invoice; the amount due on page 2 is $1,845.00," and on a digitally-authored report it might be "The Q3 report runs 28 pages; revenue on p. 4 is $12.3M, up 9% YoY." What you're steering away from is the "I'll examine the PDF" / "Let me check if this is extractable" preamble — the answer to their question is the first thing they should see.

For anything beyond a quick peek — figures, tables, attachments, forms, scanned PDFs, visual inspection, or choosing a reading strategy — go read the `pdf` skill.

---

## DOCX / DOC

The `docx` skill covers editing, creating, tracked changes, images. Read it if you need any of those. For a quick look:

```bash
extract-text /path/to/uploads/memo.docx | head -200
```

Legacy `.doc` (not `.docx`) must be converted first — see the `docx` skill.

---

## XLSX / XLS / spreadsheets

The `xlsx` skill covers formulas, formatting, charts, creating. Read it if you need any of those. For a quick look at an `.xlsx`:

```bash
extract-text /path/to/uploads/data.xlsx | head -100
```

For `.xlsm`, add `--format xlsx` (same zip structure; only the extension differs). When you need a structured preview in Python:

```python
from openpyxl import load_workbook
wb = load_workbook("/path/to/uploads/data.xlsx", read_only=True)
print("Sheets:", wb.sheetnames)
ws = wb.active
for row in ws.iter_rows(max_row=5, values_only=True):
    print(row)
```

`read_only=True` matters — without it, openpyxl loads the entire workbook into memory, which breaks on large files. Do not trust `ws.max_row` in read-only mode: many non-Excel writers omit the dimension record, so it comes back `None` or wrong. If you need a row count, iterate or use pandas.

**Legacy `.xls`** — openpyxl raises `InvalidFileException`. Use:

```python
import pandas as pd
df = pd.read_excel("/path/to/uploads/old.xls", engine="xlrd", nrows=5)
```

**`.ods` (OpenDocument)** — openpyxl also rejects this. Use:

```python
import pandas as pd
df = pd.read_excel("/path/to/uploads/data.ods", engine="odf", nrows=5)
```

---

## PPTX

```bash
extract-text /path/to/uploads/deck.pptx | head -200
```

---

## CSV / TSV

**Do not** `cat` or `head` these blindly. A CSV with a 50KB quoted cell in row 1 will wreck your `head -5`. Use pandas with `nrows`:

```python
import pandas as pd
df = pd.read_csv("/path/to/uploads/data.csv", nrows=5)
print(df)
print()
print(df.dtypes)
```

Approximate row count without loading:

```bash
wc -l /path/to/uploads/data.csv
```

Full analysis only after you know the shape:

```python
df = pd.read_csv("/path/to/uploads/data.csv")
print(df.describe())
```

TSV: same, with `sep="\t"`.

---

## JSON / JSONL

Structure first, content second:

```bash
jq 'type' /path/to/uploads/data.json
jq 'if type == "array" then length elif type == "object" then keys else . end' /path/to/uploads/data.json
```

JSONL (one object per line) — do **not** `jq` the whole file; work line by line:

```bash
head -3 /path/to/uploads/data.jsonl | jq .
wc -l /path/to/uploads/data.jsonl
```

---

## Images (JPG / PNG / GIF / WEBP)

**You can already see uploaded images** if they are injected into vision inputs.

If processing the image programmatically:

```python
from PIL import Image
img = Image.open("/path/to/uploads/photo.jpg")
print(img.size, img.mode, img.format)
```

For OCR on an image (text extraction, not description):

```python
import easyocr
reader = easyocr.Reader(['en'])
print(reader.readtext('/path/to/uploads/photo.jpg', detail=0))
```

---

## Archives (ZIP / TAR / TAR.GZ)

**List first. Extract never — unless the user explicitly asks.**

```bash
unzip -l /path/to/uploads/bundle.zip
tar -tf /path/to/uploads/bundle.tar
```

If the user wants one file from inside, extract just that one:

```bash
unzip -p /path/to/uploads/bundle.zip path/inside/file.txt
```

---

## EPUB / ODT

```bash
extract-text /path/to/uploads/book.epub | head -200
```

---

## RTF / IPYNB

```bash
extract-text /path/to/uploads/notes.rtf | head -200
extract-text /path/to/uploads/notebook.ipynb | head -200
```

---

## Plain text / code / logs

Check the size first:

```bash
wc -c /path/to/uploads/app.log
```

- **Under ~20KB**: view/read is fine.
- **Over ~20KB**: `head -100` and `tail -100` to orient. If the user asked about something specific, `grep` for it.

---

## Unknown extension

```bash
file /path/to/uploads/mystery.bin
xxd /path/to/uploads/mystery.bin | head -5
```
