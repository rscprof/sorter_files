"""Модуль: архивы (приоритет 30)."""

from __future__ import annotations

from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import is_archive


class ArchivesAnalyzer(BaseAnalyzer):
    """Определяет архивы для распаковки."""

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
        ext = Path(filepath).suffix.lower().lstrip(".")

        info = self._make_info(filepath)
        info.is_archive = True
        info.ai_category = "архив"
        info.ai_description = f"Архив {ext}, требует распаковки"
        return info
