"""Тесты projects.py."""

import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from projects import (
    is_project_directory, find_project_root, is_build_artifact,
    get_directory_listing, PROJECT_INDICATORS, PROJECT_EXCLUDE_DIRS,
    BUILD_ARTIFACT_PATTERNS,
)


class TestIsProjectDirectory:
    def test_with_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").touch()
        assert is_project_directory(str(tmp_path))

    def test_with_package_json(self, tmp_path):
        (tmp_path / "package.json").touch()
        assert is_project_directory(str(tmp_path))

    def test_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert is_project_directory(str(tmp_path))

    def test_with_makefile(self, tmp_path):
        (tmp_path / "Makefile").touch()
        assert is_project_directory(str(tmp_path))

    def test_empty_dir(self, tmp_path):
        assert not is_project_directory(str(tmp_path))

    def test_nonexistent(self):
        assert not is_project_directory("/nonexistent/dir/xyz")

    def test_only_text_files(self, tmp_path):
        (tmp_path / "readme.txt").touch()
        (tmp_path / "notes.txt").touch()
        assert not is_project_directory(str(tmp_path))


class TestFindProjectRoot:
    def test_finds_immediate_parent(self, tmp_path):
        # Создаём проект
        (tmp_path / "requirements.txt").touch()
        subdir = tmp_path / "src"
        subdir.mkdir()
        test_file = subdir / "main.py"
        test_file.touch()

        root = find_project_root(str(test_file))
        assert root == str(tmp_path)

    def test_excluded_dir_skipped(self, tmp_path):
        # html — excluded dir
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        (html_dir / "package.json").touch()

        # Файл рядом с html
        test_file = tmp_path / "test.py"
        test_file.touch()

        # Не должен найти html как корень проекта
        root = find_project_root(str(test_file))
        assert root is None

    def test_no_project(self, tmp_path):
        (tmp_path / "file.txt").touch()
        assert find_project_root(str(tmp_path / "file.txt")) is None


class TestIsBuildArtifact:
    @pytest.mark.parametrize("rel_path", [
        ("__pycache__/module.pyc"),
        ("build/Debug/app.exe"),
        ("bin/Release/app.dll"),
        ("output.min.js"),
        ("script.min.js.map"),
        (".DS_Store"),
        ("Thumbs.db"),
        ("file.log"),
        ("file.tmp"),
        ("file~"),
    ])
    def test_build_artifacts(self, rel_path):
        assert is_build_artifact(rel_path, "/project")

    @pytest.mark.parametrize("rel_path", [
        "src/main.py",
        "README.md",
        "tests/test_main.py",
        "docs/index.html",
        "requirements.txt",
        "config.json",
    ])
    def test_not_build_artifacts(self, rel_path):
        assert not is_build_artifact(rel_path, "/project")


class TestGetDirectoryListing:
    def test_empty_dir(self, tmp_path):
        listing = get_directory_listing(str(tmp_path))
        assert listing == ""

    def test_single_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        listing = get_directory_listing(str(tmp_path))
        assert "test.txt" in listing
        assert "📄" in listing

    def test_directory_structure(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("a" * 100)
        (subdir / "file2.txt").write_text("b" * 200)

        listing = get_directory_listing(str(tmp_path))
        assert "file1.txt" in listing
        assert "subdir/" in listing
        assert "file2.txt" in listing

    def test_max_entries(self, tmp_path):
        # Создаём больше файлов чем max_entries
        for i in range(60):
            (tmp_path / f"file_{i}.txt").touch()

        listing = get_directory_listing(str(tmp_path), max_entries=50)
        assert "ещё 10 записей" in listing

    def test_nonexistent(self):
        listing = get_directory_listing("/nonexistent/xyz")
        assert "недоступно" in listing
