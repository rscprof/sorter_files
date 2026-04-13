"""Общие фикстуры и настройки для тестов."""

import os
import sys
import pytest

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_file(tmp_path):
    """Создаёт тестовый текстовый файл."""
    f = tmp_path / "sample.txt"
    f.write_text("Hello World\nLine 2\nLine 3")
    return str(f)


@pytest.fixture
def sample_zip(tmp_path):
    """Создаёт тестовый zip-архив."""
    import zipfile
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file1.txt", "content1")
        zf.writestr("file2.txt", "content2")
        zf.writestr("subdir/file3.txt", "nested content")
    return str(zip_path)
