"""Тесты duplicates.py."""

import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from duplicates import detect_and_handle_duplicates
from models import FileInfo, ProcessingState


def make_file_info(path: str, file_hash: str = "", **kwargs) -> FileInfo:
    """Хелпер для создания FileInfo."""
    defaults = dict(
        original_path=path,
        filename=Path(path).name,
        extension=Path(path).suffix.lstrip("."),
        size=100,
        mime_type="text/plain",
    )
    defaults.update(kwargs)
    if file_hash:
        defaults["file_hash"] = file_hash
    return FileInfo(**defaults)


class TestDetectDuplicates:
    def test_no_duplicates(self):
        files = [
            make_file_info("/tmp/file1.txt", "hash1"),
            make_file_info("/tmp/file2.txt", "hash2"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)
        for fi in result:
            assert fi.is_duplicate is False

    def test_detects_duplicates(self):
        files = [
            make_file_info("/tmp/orig.txt", "same_hash"),
            make_file_info("/tmp/copy.txt", "same_hash"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        # Один из файлов помечен на удаление (duplicate_action == "delete")
        deleted = [f for f in result if f.duplicate_action == "delete"]
        assert len(deleted) >= 1, "Хотя бы один файл должен быть помечен на удаление"

    def test_three_duplicates(self):
        files = [
            make_file_info("/tmp/a.txt", "h"),
            make_file_info("/tmp/b.txt", "h"),
            make_file_info("/tmp/c.txt", "h"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        # Хотя бы один файл помечен на удаление
        deleted = [f for f in result if f.duplicate_action == "delete"]
        assert len(deleted) >= 1, "Хотя бы один файл должен быть помечен на удаление"

    def test_no_hash_skipped(self):
        files = [
            make_file_info("/tmp/a.txt", ""),
            make_file_info("/tmp/b.txt", ""),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)
        # Файлы без хеша не считаются дубликатами
        for fi in result:
            assert fi.is_duplicate is False

    def test_empty_input(self):
        state = ProcessingState()
        result = detect_and_handle_duplicates([], state)
        assert result == []
