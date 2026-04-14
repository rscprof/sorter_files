"""Тесты duplicates.py."""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from duplicates import detect_and_handle_duplicates, _is_protected, TYPICAL_PROJECT_FILES
from models import FileInfo, ProcessingState


def make_fi(path: str, file_hash: str = "",
            is_part_of_project: bool = False, **kwargs) -> FileInfo:
    """Хелпер для создания FileInfo."""
    defaults = dict(
        original_path=path,
        filename=Path(path).name,
        extension=Path(path).suffix.lstrip("."),
        size=100,
        mime_type="text/plain",
        is_part_of_project=is_part_of_project,
    )
    defaults.update(kwargs)
    if file_hash:
        defaults["file_hash"] = file_hash
    return FileInfo(**defaults)


class TestIsProtected:
    def test_project_file(self):
        fi = make_fi("/project/src/main.py", is_part_of_project=True)
        assert _is_protected(fi)

    def test_typical_file(self):
        fi = make_fi("/project/__init__.py")
        assert _is_protected(fi)
        fi2 = make_fi("/other/LICENSE")
        assert _is_protected(fi2)

    def test_regular_file(self):
        fi = make_fi("/tmp/report.pdf")
        assert not _is_protected(fi)


class TestProjectFilesNeverDuplicates:
    """Файлы из проектов НИКОГДА не дубликаты, даже если одинаковые."""

    def test_same_file_in_two_projects(self):
        """Одинаковый файл в двух разных проектах — оба защищены."""
        files = [
            make_fi("/projectA/src/utils.py", "h1", is_part_of_project=True),
            make_fi("/projectB/src/utils.py", "h1", is_part_of_project=True),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        for fi in result:
            assert fi.is_duplicate is False
            assert fi.should_delete is False

    def test_project_file_matches_external(self):
        """Файл проекта совпадает с внешним — оба остаются."""
        files = [
            make_fi("/project/src/main.py", "h1", is_part_of_project=True),
            make_fi("/backup/main.py", "h1"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        # Файл из проекта НЕ дубликат
        project_fi = [f for f in result if f.is_part_of_project]
        assert len(project_fi) == 1
        assert project_fi[0].is_duplicate is False
        assert project_fi[0].should_delete is False

        # Внешний файл тоже НЕ дубликат (только 1 незащищённый в группе)
        external_fi = [f for f in result if not f.is_part_of_project]
        assert len(external_fi) == 1
        assert external_fi[0].is_duplicate is False

    def test_typical_files_across_projects(self):
        """Типичные файлы (__init__.py, LICENSE) — никогда не дубликаты."""
        files = []
        for name in ["__init__.py", "LICENSE", ".gitignore"]:
            files.append(make_fi(f"/project1/{name}", "h1"))
            files.append(make_fi(f"/project2/{name}", "h1"))

        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        for fi in result:
            assert fi.is_duplicate is False
            assert fi.should_delete is False


class TestRealDuplicates:
    """Настоящие дубликаты — файлы ВНЕ проектов с одинаковым хешом."""

    def test_two_external_same_hash(self):
        files = [
            make_fi("/photos/IMG_001.jpg", "h1"),
            make_fi("/backup/IMG_001.jpg", "h1"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        duplicates = [f for f in result if f.is_duplicate]
        assert len(duplicates) >= 1

    def test_three_external_same_hash(self):
        files = [
            make_fi("/a/file.txt", "h"),
            make_fi("/b/file.txt", "h"),
            make_fi("/c/file.txt", "h"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        deleted = [f for f in result if f.duplicate_action == "delete"]
        assert len(deleted) >= 1, "Хотя бы один файл должен быть помечен на удаление"

    def test_archive_file_is_original(self):
        """Файл из архива — оригинал, внешний — дубликат."""
        files = [
            make_fi("/_архивы/backup/IMG.jpg", "h1"),
            make_fi("/photos/IMG.jpg", "h1"),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)

        # Файл из архива — keep
        archive_fi = [f for f in result if "_архивы" in f.original_path]
        assert len(archive_fi) == 1
        assert archive_fi[0].duplicate_action in ("keep", "skip")

        # Внешний — delete
        photo_fi = [f for f in result if "/photos" in f.original_path]
        assert len(photo_fi) == 1
        assert photo_fi[0].is_duplicate is True


class TestEdgeCases:
    def test_no_hash_skipped(self):
        files = [
            make_fi("/tmp/a.txt", ""),
            make_fi("/tmp/b.txt", ""),
        ]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)
        for fi in result:
            assert fi.is_duplicate is False

    def test_empty_input(self):
        state = ProcessingState()
        assert detect_and_handle_duplicates([], state) == []

    def test_single_file(self):
        files = [make_fi("/tmp/file.txt", "h1")]
        state = ProcessingState()
        result = detect_and_handle_duplicates(files, state)
        assert len(result) == 1
        assert result[0].is_duplicate is False
