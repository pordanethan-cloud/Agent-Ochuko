import os
import io
import zipfile
import tarfile
import tempfile
import pytest
from app.services.document_processor import DocumentProcessor


def test_extract_archive_zip():
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "test.zip")
        out_dir = os.path.join(tmpdir, "extracted")

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hello.txt", "Hello World Ochuko")
            zf.writestr("src/main.py", "print('hello')")
            # Potential path traversal attempt to test Zip-Slip security
            zf.writestr("../evil.txt", "malicious content")

        res = DocumentProcessor.extract_archive(zip_path, out_dir)

        assert "error" not in res
        assert "hello.txt" in res["extracted_files"]
        assert "src/main.py" in res["extracted_files"]
        # Evil path should have been blocked
        assert not os.path.exists(os.path.join(tmpdir, "evil.txt"))
        assert os.path.exists(os.path.join(out_dir, "hello.txt"))
        assert "hello.txt" in res["file_tree"]
        assert "hello.txt" in res["previews"]
        assert res["previews"]["hello.txt"] == "Hello World Ochuko"


def test_extract_archive_tar():
    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = os.path.join(tmpdir, "test.tar.gz")
        out_dir = os.path.join(tmpdir, "extracted")

        with tarfile.open(tar_path, "w:gz") as tf:
            data = b"Sample text inside tar"
            ti = tarfile.TarInfo("data/sample.txt")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))

        res = DocumentProcessor.extract_archive(tar_path, out_dir)

        assert "error" not in res
        assert "data/sample.txt" in res["extracted_files"]
        assert os.path.exists(os.path.join(out_dir, "data", "sample.txt"))


def test_extract_tabular_summary_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "data.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Name,Age,Role\nAlice,30,Engineer\nBob,25,Designer\n")

        summary = DocumentProcessor.extract_tabular_summary(csv_path)

        assert "data.csv" in summary
        assert "| Name | Age | Role |" in summary
        assert "| Alice | 30 | Engineer |" in summary


def test_extract_document_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "doc.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("This is document content.")

        text = DocumentProcessor.extract_document_text(txt_path)
        assert text == "This is document content."
