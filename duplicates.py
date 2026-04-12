"""Управление дубликатами."""

from __future__ import annotations

import os
from pathlib import Path

from models import FileInfo, ProcessingState


def detect_and_handle_duplicates(
    file_infos: list[FileInfo],
    state: ProcessingState,
) -> list[FileInfo]:
    """
    Найти дубликаты по хешу и принять решение для каждого.

    Логика:
    - Если файл уже обработан (есть в state) — пропускаем
    - Если несколько файлов с одинаковым хешом:
      - Если один из них в проекте — оставляем все (часть проекта)
      - Если один в архиве/бэкапе — удаляем остальные
      - Иначе — оставляем самый старый, остальные помечаем на удаление
    """
    # Группируем по хешу
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

        # Это дубликат
        fi.is_duplicate = True
        action = _decide_action(fi, group)
        fi.duplicate_action = action

        if action == "delete":
            # Указываем оригинал
            original = _find_original(group)
            fi.duplicate_of = original.original_path
            fi.should_delete = True
        elif action == "keep_as_project_part":
            fi.is_part_of_project = True

        state.register_duplicate(fi.file_hash, fi.original_path)
        results.append(fi)

    return results


def _decide_action(target: FileInfo, group: list[FileInfo]) -> str:
    """Решить что делать с дубликатом."""
    # Есть ли файлы из проектов?
    project_files = [f for f in group if f.is_part_of_project or f.project_root]
    if project_files:
        return "keep_as_project_part"

    # Есть ли в архивах/бэкапах?
    archive_keywords = ["_архивы", "_backup", "backup", "archive", "gz/", "tar/"]
    archive_files = [f for f in group if any(kw in f.original_path.lower() for kw in archive_keywords)]
    if archive_files:
        # Файл из архива — оригинал, остальные удаляем
        if target in archive_files:
            return "keep"
        return "delete"

    # Оставляем самый старый файл
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
