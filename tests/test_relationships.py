"""Тесты relationships.py."""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from relationships import find_related_in_directory
from models import FileInfo, ImageMetadata


def make_fi(path: str, **kwargs) -> FileInfo:
    defaults = dict(
        original_path=path,
        filename=Path(path).name,
        extension=Path(path).suffix.lstrip("."),
        size=100,
        mime_type="text/plain",
    )
    defaults.update(kwargs)
    return FileInfo(**defaults)


class TestFindRelatedInDirectory:
    def test_same_directory_different_ext(self, tmp_path):
        # Файлы в одном каталоге с разным расширением
        f1 = tmp_path / "report.xlsx"
        f2 = tmp_path / "report.pdf"
        f1.touch()
        f2.touch()

        all_files = [str(f1), str(f2)]
        related = find_related_in_directory(str(f1), all_files)
        assert str(f2) in related

    def test_different_directories(self, tmp_path):
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir()
        d2.mkdir()

        f1 = d1 / "file.txt"
        f2 = d2 / "file.txt"
        f1.touch()
        f2.touch()

        all_files = [str(f1), str(f2)]
        related = find_related_in_directory(str(f1), all_files)
        assert len(related) == 0  # Разные каталоги

    def test_same_file_excluded(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        related = find_related_in_directory(str(f), [str(f)])
        assert len(related) == 0  # Тот же файл не считается связанным

    def test_multiple_related(self, tmp_path):
        files = []
        for ext in ["txt", "pdf", "docx"]:
            f = tmp_path / f"report.{ext}"
            f.touch()
            files.append(str(f))

        related = find_related_in_directory(files[0], files)
        assert len(related) == 2  # Два других файла
