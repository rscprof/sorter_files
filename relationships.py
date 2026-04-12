"""Определение связанных файлов и группировка."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from metadata import ImageMetadata
from models import FileInfo


def group_related_files(file_infos: list[FileInfo]) -> list[list[FileInfo]]:
    """
    Группирует файлы по связанности:
    1. Файлы из одного каталога анализируются вместе
    2. Фото с близкими датами/устройством/GPS группируются
    3. Файлы проектов остаются вместе
    """
    # Группировка по каталогам
    dir_groups: dict[str, list[FileInfo]] = defaultdict(list)
    for fi in file_infos:
        parent = str(Path(fi.original_path).parent)
        dir_groups[parent].append(fi)

    # Объединяем группы
    groups = []

    for dirpath, files in dir_groups.items():
        # Разбиваем на подгруппы по типу
        images = [f for f in files if f.image_metadata]
        others = [f for f in files if not f.image_metadata]

        # Фото группируем по метаданным
        if images:
            photo_groups = _cluster_photos(images)
            groups.extend(photo_groups)
        else:
            # Все файлы каталога — одна группа
            if others:
                groups.append(others)

        # Одиночки тоже добавляем
        for f in files:
            if not any(f in g for g in groups):
                groups.append([f])

    # Перекрёстные ссылки между каталогами
    # (файлы с перекрывающимися AI-keywords)
    _link_cross_directory_groups(groups)

    return groups


def _cluster_photos(images: list[FileInfo]) -> list[list[FileInfo]]:
    """Кластеризация фото по EXIF-метаданным."""
    if len(images) <= 1:
        return [images] if images else []

    # Простая жадная кластеризация
    clusters: list[list[FileInfo]] = []

    for img in images:
        if not img.image_metadata:
            clusters.append([img])
            continue

        placed = False
        for cluster in clusters:
            # Проверяем схожесть с любым фото в кластере
            for existing in cluster:
                if existing.image_metadata:
                    sim = img.image_metadata.similarity(existing.image_metadata)
                    if sim > 0.5:  # порог
                        cluster.append(img)
                        placed = True
                        break
            if placed:
                break

        if not placed:
            clusters.append([img])

    return clusters


def _link_cross_directory_groups(groups: list[list[FileInfo]]):
    """Найти связи между группами из разных каталогов."""
    # Для каждой группы собираем AI-keywords
    group_keywords: dict[int, set[str]] = {}
    for i, group in enumerate(groups):
        keywords = set()
        for fi in group:
            if fi.ai_category or fi.ai_description:
                # Ключевые слова из описания
                words = set((fi.ai_category + " " + fi.ai_subcategory + " " + fi.ai_description).lower().split())
                keywords.update(w for w in words if len(w) > 3)
        group_keywords[i] = keywords

    # Ищем пересечения
    linked = set()
    for i in group_keywords:
        for j in group_keywords:
            if i >= j:
                continue
            intersection = group_keywords[i] & group_keywords[j]
            if len(intersection) >= 3:  # 3+ общих слова
                # Объединяем группы
                groups[i].extend(groups[j])
                linked.add(j)

    # Убираем объединённые
    groups[:] = [g for i, g in enumerate(groups) if i not in linked]


def find_related_in_directory(filepath: str, all_files: list[str]) -> list[str]:
    """Найти файлы в том же каталоге, потенциально связанные."""
    p = Path(filepath)
    parent = p.parent
    related = []

    for other in all_files:
        other_p = Path(other)
        if other_p.parent == parent and other != filepath:
            related.append(other)

    return related
