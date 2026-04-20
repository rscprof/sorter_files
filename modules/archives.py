"""Модуль: архивы (приоритет 30)."""

from __future__ import annotations

from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import is_archive


class ArchivesAnalyzer(BaseAnalyzer):
    """Определяет архивы для распаковки.
    
    Также проверяет, не является ли архив общедоступным дистрибутивом
    (например, tarball с исходниками проекта).
    """

    @property
    def priority(self) -> int:
        return 30

    @property
    def name(self) -> str:
        return "archives"

    def can_handle(self, filepath: str) -> bool:
        return is_archive(filepath)

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        from pathlib import Path
        p = Path(filepath)
        ext = p.suffix.lower().lstrip(".")
        
        # Для составных расширений типа .tar.gz, .tar.bz2 и т.п.
        # проверяем полное имя файла
        stem = p.stem  # например, "project-1.0.tar" для "project-1.0.tar.gz"
        filename_for_check = p.name

        info = self._make_info(filepath)
        info.is_archive = True
        info.ai_category = "архив"
        info.ai_description = f"Архив {ext}, требует распаковки"
        
        # Проверяем, не является ли архив общедоступным дистрибутивом
        searxng = existing_context.get("searxng")
        if searxng:
            info.is_distributable = searxng.is_known_distributable(filename_for_check)
            if info.is_distributable:
                info.should_delete = True
                info.ai_description = f"Публичный дистрибутив (архив {ext})"
        else:
            # Без SearXNG — не помечаем автоматически, пусть распакуется и анализируется содержимое
            info.is_distributable = False
        
        return info
