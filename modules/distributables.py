"""Модуль: общедоступные дистрибутивы (приоритет 20)."""

from __future__ import annotations

from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import is_executable
from config import EXECUTABLE_EXTS


class DistributablesAnalyzer(BaseAnalyzer):
    """Определяет общедоступные дистрибутивы через SearXNG."""

    @property
    def priority(self) -> int:
        return 20

    @property
    def name(self) -> str:
        return "distributables"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        ext = Path(filepath).suffix.lower().lstrip(".")
        return is_executable(filepath) or ext in EXECUTABLE_EXTS or ext == "iso"

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        searxng = existing_context.get("searxng")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)
        info.ai_category = "дистрибутив"

        if searxng:
            info.is_distributable = searxng.is_known_distributable(p.name)
        else:
            # Без SearXNG — помечаем как потенциальный дистрибутив
            info.is_distributable = True

        info.should_delete = info.is_distributable
        return info
