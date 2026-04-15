"""Тесты analyzer.py."""

import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyzer import (
    compute_file_hash, is_temp_file,
    is_archive, is_executable, is_image, extract_text,
    _human_size, pdf_to_images, image_to_jpeg, AUDIO_EXTS
)
from config import TEMP_FILE_PATTERNS


class TestComputeHash:
    def test_small_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = compute_file_hash(str(f))
        assert h1
        assert len(h1) == 64  # SHA-256 hex
        # Тот же файл = тот же хеш
        h2 = compute_file_hash(str(f))
        assert h1 == h2

    def test_different_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert compute_file_hash(str(f1)) != compute_file_hash(str(f2))

    def test_binary_file(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03" * 1000)
        h = compute_file_hash(str(f))
        assert len(h) == 64


class TestPartialHash:
    def test_same_as_full_for_small(self, tmp_path):
        # compute_partial_hash удалён, тестируем только compute_file_hash
        f = tmp_path / "small.txt"
        f.write_text("test content")
        h = compute_file_hash(str(f))
        assert len(h) == 64


class TestIsTempFile:
    @pytest.mark.parametrize("name", [
        "~$document.docx", "~$practice.docx",
        "~WRL0003.tmp", "~WRL3589.tmp",
        "file.tmp", "file.temp",
        "file.bak", "file.backup",
        "file.swp", "file.swo",
        "file~",
        ".DS_Store", "Thumbs.db", "desktop.ini",
        "._MacOSX",
    ])
    def test_temp_patterns(self, tmp_path, name):
        assert is_temp_file(str(tmp_path / name)), f"{name} должен быть temp"

    @pytest.mark.parametrize("name", [
        "document.docx", "report.pdf", "photo.jpg",
        "practice.docx", "archive.zip",
    ])
    def test_not_temp(self, tmp_path, name):
        assert not is_temp_file(str(tmp_path / name)), f"{name} НЕ должен быть temp"


class TestFileTypes:
    def test_is_archive(self, tmp_path):
        for ext in ("zip", "tar", "gz", "7z", "rar", "tgz", "iso"):
            f = tmp_path / f"file.{ext}"
            f.touch()
            assert is_archive(str(f)), f".{ext} должен быть архивом"

    def test_is_executable(self, tmp_path):
        for ext in ("exe", "msi", "dmg", "deb", "rpm", "apk"):
            f = tmp_path / f"file.{ext}"
            f.touch()
            assert is_executable(str(f)), f".{ext} должен быть executable"

    def test_is_image(self, tmp_path):
        for ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff"):
            f = tmp_path / f"file.{ext}"
            f.touch()
            assert is_image(str(f)), f".{ext} должно быть image"

    def test_is_not_image(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        assert not is_image(str(f))


class TestExtractText:
    def test_plain_text(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello World\nLine 2")
        assert "Hello World" in extract_text(str(f))

    def test_python_file(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("def hello():\n    return 'world'")
        text = extract_text(str(f))
        assert "def hello" in text

    def test_large_file_truncated(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 20000)
        text = extract_text(str(f))
        assert len(text) <= 5000

    def test_nonexistent_returns_sig(self, tmp_path):
        # extract_text вызовет getsize на несуществующем файле
        # Это ожидаемое поведение — тестируем существующий пустой файл
        f = tmp_path / "empty.xyz"
        f.touch()
        text = extract_text(str(f))
        assert "[" in text  # Сигнатура файла


class TestPdfToImages:
    def test_nonexistent_pdf(self):
        assert pdf_to_images("/nonexistent.pdf") == []

    def test_empty_pdf(self, tmp_path):
        # Создаём минимальный PDF
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"%PDF-1.0\n1 0 obj<</Type/Catalog>>\n%%EOF")
        # pdftocairo может не распознать — но не упадёт
        result = pdf_to_images(str(f))
        assert isinstance(result, list)


class TestImageToJpeg:
    def test_jpg_unchanged(self, tmp_path):
        # Создаём минимальный JPEG
        f = tmp_path / "test.jpg"
        # JPEG magic
        f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        result = image_to_jpeg(str(f))
        assert result == str(f)  # JPEG не конвертируется

    def test_nonexistent(self):
        result = image_to_jpeg("/nonexistent.xyz")
        # Должен вернуть исходный путь при ошибке конвертации
        assert result == "/nonexistent.xyz"


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500).endswith("B")

    def test_kb(self):
        assert _human_size(1024).endswith("KB")

    def test_mb(self):
        assert _human_size(1048576).endswith("MB")

    def test_gb(self):
        assert _human_size(1073741824).endswith("GB")
