"""Управление дубликатами."""

from __future__ import annotations

import os
from pathlib import Path

from models import FileInfo, ProcessingState

# Типичные файлы проектов, которые могут совпадать и это нормально.
# Не считаем их дубликатами для целей удаления.
TYPICAL_PROJECT_FILES: set[str] = {
    "__init__.py",
    "package-lock.json",
    ".npmrc",
    ".eslintrc.json", ".eslintrc.js",
    ".prettierrc", ".prettierrc.json",
    ".editorconfig",
    ".gitignore", ".gitattributes",
    ".dockerignore", ".env.example",
    "LICENSE", "LICENSE.md", "LICENSE.txt",
    "COPYING", "README.md", "CHANGELOG.md",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
    ".gitkeep", ".keep",
}


def _is_protected(fi: FileInfo) -> bool:
    """Файл защищён от удаления как дубликат."""
    if fi.is_part_of_project:
        return True
    if Path(fi.filename).name in TYPICAL_PROJECT_FILES:
        return True
    return False


def detect_and_handle_duplicates(
    file_infos: list[FileInfo],
    state: ProcessingState,
) -> list[FileInfo]:
    """
    Найти дубликаты по SHA-256 хешу и принять решение.

    Правила:
    - Защищённые файлы (проекты, типичные файлы) — НИКОГДА не дубликаты
    - Файлы из архивов/бэкапов — оригиналы, остальные удаляются
    - Иначе — самый старый файл остаётся, остальные на удаление
    """
    hash_groups: dict[str, list[FileInfo]] = {}
    for fi in file_infos:
        if not fi.file_hash:
            continue
        hash_groups.setdefault(fi.file_hash, []).append(fi)

    results = []
    for fi in file_infos:
        if not fi.file_hash:
            results.append(fi)
            continue

        # Защищённые — никогда не дубликаты
        if _is_protected(fi):
            results.append(fi)
            continue

        # Уже обработан?
        if state.is_already_processed(fi.file_hash):
            prev = state.get_processed_info(fi.file_hash)
            if prev:
                fi.target_path = prev.get("target_path", "")
                fi.duplicate_action = prev.get("duplicate_action", "skip")
                results.append(fi)
                continue

        group = hash_groups.get(fi.file_hash, [])
        if len(group) <= 1:
            results.append(fi)
            continue

        # Убираем защищённые из группы — они не участвуют
        unprotected = [f for f in group if not _is_protected(f)]

        if len(unprotected) <= 1:
            # Только один незащищённый — не дубликат
            results.append(fi)
            continue

        if fi not in unprotected:
            results.append(fi)
            continue

        # Это дубликат
        fi.is_duplicate = True
        action = _decide_action(fi, unprotected)
        fi.duplicate_action = action

        if action == "delete":
            original = _find_original(unprotected)
            fi.duplicate_of = original.original_path
            fi.should_delete = True

        state.register_duplicate(fi.file_hash, fi.original_path)
        results.append(fi)

    return results


def _decide_action(target: FileInfo, group: list[FileInfo]) -> str:
    """Решить что делать с дубликатом.
    
    group — только незащищённые файлы.
    """
    # Файлы из архивов — оригиналы
    archive_keywords = ["_архивы", "_backup", "backup", "archive"]
    archive_files = [f for f in group if any(kw in f.original_path.lower() for kw in archive_keywords)]
    if archive_files:
        return "keep" if target in archive_files else "delete"

    # Самый старый файл — оригинал
    try:
        with_mtime = []
        for f in group:
            if os.path.exists(f.original_path):
                with_mtime.append((f, os.path.getmtime(f.original_path)))
        if with_mtime:
            with_mtime.sort(key=lambda x: x[1])
            oldest = with_mtime[0][0]
            if target.original_path != oldest.original_path:
                return "delete"
    except Exception:
        pass

    return "delete"


def _find_original(group: list[FileInfo]) -> FileInfo:
    """Найти оригинал (самый старый файл)."""
    try:
        with_mtime = []
        for f in group:
            if os.path.exists(f.original_path):
                with_mtime.append((f, os.path.getmtime(f.original_path)))
        if with_mtime:
            with_mtime.sort(key=lambda x: x[1])
            return with_mtime[0][0]
    except Exception:
        pass
    return group[0]
