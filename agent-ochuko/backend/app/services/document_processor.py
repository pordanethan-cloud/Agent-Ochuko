"""
Document Processor Service for Agent Ochuko.
Handles PDF image extraction, DOCX text editing/signatories, archive decompression (.zip/.tar/.gz/.7z),
tabular data extraction (.xlsx/.csv), and direct document text parsing using PyMuPDF (fitz), python-docx, openpyxl, and Pillow.
"""
import io
import os
import csv
import shutil
import zipfile
import tarfile
import gzip
import bz2
import lzma
import logging
from typing import List, Dict, Any, Optional, Tuple
import docx
from docx.shared import Inches, Pt
from PIL import Image

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Helper methods for archive extraction, tabular processing, PDF extraction, and DOCX document editing."""

    @staticmethod
    def extract_archive(
        archive_path: str,
        output_dir: str,
        max_files: int = 150,
        max_uncompressed_bytes: int = 50 * 1024 * 1024
    ) -> Dict[str, Any]:
        """
        Safely unpacks compressed archives (.zip, .tar, .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz, .txz, .gz, .bz2, .xz)
        into output_dir with Zip-Slip path traversal protection.
        Returns manifest containing list of extracted files, directory tree, total size, and content previews.
        """
        if not os.path.exists(archive_path):
            return {"error": f"Archive not found: {archive_path}", "files": []}

        os.makedirs(output_dir, exist_ok=True)
        canonical_output = os.path.realpath(output_dir)

        extracted_files: List[str] = []
        total_bytes = 0
        file_tree: List[str] = []
        previews: Dict[str, str] = {}

        name_lower = os.path.basename(archive_path).lower()

        try:
            # 1. Zip Archives (.zip)
            if name_lower.endswith(".zip"):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    infos = zf.infolist()
                    for info in infos[:max_files]:
                        # Zip-slip prevention
                        target_path = os.path.realpath(os.path.join(output_dir, info.filename))
                        if not target_path.startswith(canonical_output):
                            logger.warning(f"Skipping path traversal attempt in zip: {info.filename}")
                            continue

                        total_bytes += info.file_size
                        if total_bytes > max_uncompressed_bytes:
                            logger.warning(f"Archive exceeded max uncompressed limit of {max_uncompressed_bytes} bytes")
                            break

                        if info.is_dir():
                            os.makedirs(target_path, exist_ok=True)
                            file_tree.append(f"📁 {info.filename}")
                        else:
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            with zf.open(info) as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())
                            extracted_files.append(info.filename)
                            file_tree.append(f"📄 {info.filename} ({info.file_size:,} bytes)")

                            # Preview text/code/config files under 30KB
                            ext = os.path.splitext(info.filename.lower())[1]
                            if ext in {".txt", ".md", ".json", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".toml", ".env", ".sh", ".sql", ".xml"} and info.file_size <= 30000:
                                try:
                                    with open(target_path, "r", encoding="utf-8", errors="replace") as f_in:
                                        previews[info.filename] = f_in.read(3000)
                                except Exception:
                                    pass

            # 2. Tar Archives (.tar, .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz, .txz)
            elif any(name_lower.endswith(sfx) for sfx in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
                mode = "r:*" if not name_lower.endswith(".tar") else "r:"
                with tarfile.open(archive_path, mode) as tf:
                    members = tf.getmembers()
                    for m in members[:max_files]:
                        target_path = os.path.realpath(os.path.join(output_dir, m.name))
                        if not target_path.startswith(canonical_output):
                            logger.warning(f"Skipping path traversal attempt in tar: {m.name}")
                            continue

                        total_bytes += m.size
                        if total_bytes > max_uncompressed_bytes:
                            break

                        if m.isdir():
                            os.makedirs(target_path, exist_ok=True)
                            file_tree.append(f"📁 {m.name}")
                        elif m.isfile():
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            f_in = tf.extractfile(m)
                            if f_in:
                                with open(target_path, 'wb') as dst:
                                    dst.write(f_in.read())
                            extracted_files.append(m.name)
                            file_tree.append(f"📄 {m.name} ({m.size:,} bytes)")

                            ext = os.path.splitext(m.name.lower())[1]
                            if ext in {".txt", ".md", ".json", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".toml", ".env", ".sh", ".sql", ".xml"} and m.size <= 30000:
                                try:
                                    with open(target_path, "r", encoding="utf-8", errors="replace") as f_pr:
                                        previews[m.name] = f_pr.read(3000)
                                except Exception:
                                    pass

            # 3. Single-file compressions (.gz, .bz2, .xz)
            elif name_lower.endswith((".gz", ".bz2", ".xz")):
                base_name = name_lower.rsplit(".", 1)[0]
                target_path = os.path.join(output_dir, os.path.basename(base_name))
                if name_lower.endswith(".gz"):
                    with gzip.open(archive_path, 'rb') as gz_in, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(gz_in, dst)
                elif name_lower.endswith(".bz2"):
                    with bz2.open(archive_path, 'rb') as bz_in, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(bz_in, dst)
                elif name_lower.endswith(".xz"):
                    with lzma.open(archive_path, 'rb') as xz_in, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(xz_in, dst)

                sz = os.path.getsize(target_path)
                fname = os.path.basename(target_path)
                extracted_files.append(fname)
                file_tree.append(f"📄 {fname} (Decompressed: {sz:,} bytes)")

            return {
                "archive_name": os.path.basename(archive_path),
                "extracted_files": extracted_files,
                "file_tree": "\n".join(file_tree[:60]) + ("\n... [and more files]" if len(file_tree) > 60 else ""),
                "previews": previews,
                "total_uncompressed_bytes": total_bytes,
                "total_files": len(extracted_files)
            }
        except Exception as e:
            logger.error(f"Archive extraction failed for {archive_path}: {e}")
            return {"error": str(e), "files": extracted_files}

    @staticmethod
    def extract_tabular_summary(file_path: str, max_rows: int = 15) -> str:
        """
        Extracts structured summaries from spreadsheet and tabular files (.xlsx, .xls, .xlsm, .csv, .tsv).
        Returns formatted Markdown table with sheet names, row counts, and column previews.
        """
        if not os.path.exists(file_path):
            return ""

        ext = os.path.splitext(file_path.lower())[1]
        lines = []

        try:
            # Excel Spreadsheets
            if ext in {".xlsx", ".xlsm"}:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                lines.append(f"📊 **Excel Workbook**: `{os.path.basename(file_path)}` ({len(wb.sheetnames)} sheets: {', '.join(wb.sheetnames)})")

                for sheetname in wb.sheetnames[:3]:
                    ws = wb[sheetname]
                    rows = list(ws.iter_rows(values_only=True, max_row=max_rows + 1))
                    if not rows:
                        continue
                    headers = [str(c or '').strip() for c in rows[0]]
                    lines.append(f"\n**Sheet: {sheetname}** (Sample Top {len(rows)-1} Rows):")
                    if headers:
                        lines.append("| " + " | ".join(headers) + " |")
                        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                        for r in rows[1:max_rows]:
                            row_vals = [str(c if c is not None else '').strip() for c in r]
                            lines.append("| " + " | ".join(row_vals) + " |")
                wb.close()

            # CSV and TSV
            elif ext in {".csv", ".tsv"}:
                delimiter = '\t' if ext == '.tsv' else ','
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    reader = csv.reader(f, delimiter=delimiter)
                    rows = [row for i, row in enumerate(reader) if i < max_rows]
                if rows:
                    lines.append(f"📊 **Tabular Data**: `{os.path.basename(file_path)}` (Sample Top {len(rows)-1} Rows):")
                    headers = [c.strip() for c in rows[0]]
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for r in rows[1:]:
                        lines.append("| " + " | ".join(c.strip() for c in r) + " |")

        except Exception as e:
            logger.debug(f"Tabular extraction note for {file_path}: {e}")
            lines.append(f"*(Tabular file `{os.path.basename(file_path)}` available in sandbox)*")

        return "\n".join(lines)

    @staticmethod
    def extract_document_text(file_path: str, max_chars: int = 25000) -> str:
        """
        Extracts native text from DOCX, PDF, RTF, or plain document formats.
        """
        if not os.path.exists(file_path):
            return ""

        ext = os.path.splitext(file_path.lower())[1]

        try:
            # Word DOCX
            if ext == ".docx":
                doc = docx.Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                text = "\n\n".join(paragraphs)
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n... [TRUNCATED] ..."
                return text

            # PDF Document
            elif ext == ".pdf":
                if fitz is None:
                    return ""
                doc = fitz.open(file_path)
                pages_text = []
                for pno in range(min(len(doc), 20)):
                    p_txt = doc[pno].get_text().strip()
                    if p_txt:
                        pages_text.append(f"--- Page {pno + 1} ---\n{p_txt}")
                doc.close()
                combined = "\n\n".join(pages_text)
                if len(combined) > max_chars:
                    combined = combined[:max_chars] + "\n... [TRUNCATED] ..."
                return combined

            # RTF / Text
            elif ext in {".txt", ".log", ".rtf", ".tex", ".env"}:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(max_chars)
                    return content

        except Exception as e:
            logger.debug(f"Document text extraction note for {file_path}: {e}")

        return ""

    @staticmethod
    def extract_images_from_pdf(pdf_path: str, output_dir: str) -> List[str]:
        """
        Extracts all embedded images from a PDF file using PyMuPDF (fitz).
        Returns list of extracted image file paths.
        """
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file not found: {pdf_path}")
            return []

        os.makedirs(output_dir, exist_ok=True)
        extracted_paths = []

        try:
            doc = fitz.open(pdf_path)
            for page_index in range(len(doc)):
                page = doc[page_index]
                image_list = page.get_images(full=True)

                for img_index, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    img_filename = f"extracted_p{page_index+1}_img{img_index+1}.{image_ext}"
                    img_path = os.path.join(output_dir, img_filename)

                    with open(img_path, "wb") as f:
                        f.write(image_bytes)

                    extracted_paths.append(img_path)
                    logger.info(f"Extracted PDF image: {img_path}")

            doc.close()
        except Exception as e:
            logger.error(f"Failed to extract images from PDF {pdf_path}: {e}")

        return extracted_paths

    @staticmethod
    def replace_signatory_in_docx(docx_path: str, output_docx_path: str, old_signatory: str, new_signatory: str, new_title: str) -> bool:
        """
        Replaces old signatory text in a DOCX document with new_signatory and new_title.
        """
        if not os.path.exists(docx_path):
            logger.error(f"DOCX file not found: {docx_path}")
            return False

        try:
            doc = docx.Document(docx_path)

            for paragraph in doc.paragraphs:
                if old_signatory.lower() in paragraph.text.lower():
                    # Replace text in runs
                    for run in paragraph.runs:
                        if old_signatory.lower() in run.text.lower():
                            run.text = run.text.replace(old_signatory, new_signatory)
                    
                    # Add title if missing
                    if new_title and new_title.lower() not in paragraph.text.lower():
                        paragraph.text = f"{new_signatory}\n{new_title}"

            doc.save(output_docx_path)
            logger.info(f"Updated signatory in DOCX: {output_docx_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to replace signatory in DOCX: {e}")
            return False

    @staticmethod
    def insert_signature_image(docx_path: str, output_docx_path: str, signature_img_path: str, target_signatory: str) -> bool:
        """
        Inserts a signature image directly above the signatory paragraph in a DOCX document.
        """
        if not os.path.exists(docx_path) or not os.path.exists(signature_img_path):
            logger.error(f"Missing input DOCX or signature image file.")
            return False

        try:
            doc = docx.Document(docx_path)
            inserted = False

            for i, paragraph in enumerate(doc.paragraphs):
                if target_signatory.lower() in paragraph.text.lower():
                    # Insert picture in paragraph right before signatory
                    p_sig = paragraph.insert_paragraph_before()
                    run = p_sig.add_run()
                    run.add_picture(signature_img_path, width=Inches(1.8))
                    inserted = True
                    break

            if not inserted and doc.paragraphs:
                # Append at bottom if target not found explicitly
                p_last = doc.add_paragraph()
                r = p_last.add_run()
                r.add_picture(signature_img_path, width=Inches(1.8))

            doc.save(output_docx_path)
            logger.info(f"Inserted signature image into DOCX: {output_docx_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert signature image: {e}")
            return False


document_processor = DocumentProcessor()
