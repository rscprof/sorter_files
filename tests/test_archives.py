"""Тесты archives.py."""

import os
import zipfile
import tarfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from archives import extract_archive


class TestExtractZip:
    def test_extract_simple(self, tmp_path):
        # Создаём тестовый zip
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file1.txt", "content1")
            zf.writestr("file2.txt", "content2")

        extracted = extract_archive(str(zip_path), str(tmp_path / "extracted"))
        assert len(extracted) == 2
        assert (tmp_path / "extracted" / "file1.txt").exists()

    def test_extract_with_subdir(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("subdir/file.txt", "nested content")

        extracted = extract_archive(str(zip_path), str(tmp_path / "extracted"))
        assert len(extracted) == 1
        assert (tmp_path / "extracted" / "subdir" / "file.txt").exists()


class TestExtractTar:
    def test_extract_tar(self, tmp_path):
        tar_path = tmp_path / "test.tar"
        with tarfile.open(tar_path, "w") as tf:
            f1 = tmp_path / "file1.txt"
            f1.write_text("content1")
            tf.add(str(f1), arcname="file1.txt")

        extracted = extract_archive(str(tar_path), str(tmp_path / "extracted"))
        assert len(extracted) >= 1

    def test_extract_tgz(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            f1 = tmp_path / "file1.txt"
            f1.write_text("content")
            tf.add(str(f1), arcname="file1.txt")

        extracted = extract_archive(str(tar_path), str(tmp_path / "extracted"))
        assert len(extracted) >= 1


class TestExtractNonexistent:
    def test_nonexistent_archive(self, tmp_path):
        extracted = extract_archive(str(tmp_path / "nonexistent.zip"), str(tmp_path / "extracted"))
        assert extracted == []

    def test_invalid_file(self, tmp_path):
        # Создаём файл который не архив
        f = tmp_path / "not_an_archive.xyz"
        f.write_text("not an archive")
        extracted = extract_archive(str(f), str(tmp_path / "extracted"))
        assert extracted == []
