"""Обнаружение проектов и build-артефактов."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Optional

from config import BUILD_ARTIFACT_PATTERNS, PROJECT_INDICATORS


def is_project_directory(dirpath: str) -> bool:
    """Каталог содержит indicators проекта."""
    try:
        entries = os.listdir(dirpath)
    except OSError:
        return False
    for entry in entries:
        for indicator in PROJECT_INDICATORS:
            if indicator.startswith("*"):
                if fnmatch.fnmatch(entry, indicator):
                    return True
            elif entry == indicator:
                return True
    return False


def find_project_root(filepath: str, max_depth: int = 6) -> Optional[str]:
    """Найти корень проекта, поднимаясь вверх."""
    current = Path(filepath).resolve().parent
    for _ in range(max_depth):
        if is_project_directory(str(current)):
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def is_build_artifact(filepath: str, project_root: str = "") -> bool:
    """Файл — результат сборки/компиляции."""
    p = Path(filepath)
    if project_root:
        try:
            rel = str(p.relative_to(project_root)).lower()
        except ValueError:
            rel = p.name.lower()
    else:
        rel = p.name.lower()

    name_lower = p.name.lower()

    for lang, patterns in BUILD_ARTIFACT_PATTERNS.items():
        for pattern in patterns:
            if pattern.endswith("/"):
                dir_name = pattern.rstrip("/")
                if f"/{dir_name}/" in f"/{rel}" or rel.startswith(f"{dir_name}/"):
                    return True
            elif pattern.startswith("*"):
                if fnmatch.fnmatch(name_lower, pattern.lower()):
                    return True
            else:
                if pattern.lower() in rel:
                    return True

    # Общие паттерны
    for indicator in ("/build/", "/dist/", "/out/", "/bin/", "/obj/",
                       "/target/", "/.next/", "/.svelte-kit/",
                       "__pycache__", ".min.", ".bundle."):
        if indicator in rel:
            return True

    return False
