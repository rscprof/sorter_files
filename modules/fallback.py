"""Модуль: fallback (приоритет 999 — последний)."""

from __future__ import annotations

from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo


class FallbackAnalyzer(BaseAnalyzer):
    """
    Fallback — всегда может обработать файл.
    Классифицирует по расширению и имени.
    """

    @property
    def priority(self) -> int:
        return 999

    @property
    def name(self) -> str:
        return "fallback"

    def can_handle(self, filepath: str) -> bool:
        return True  # Всегда подходит

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        from pathlib import Path
        p = Path(filepath)
        ext = info_extension(filepath)

        info = self._make_info(filepath)
        info.ai_category = "Неразобранное"
        info.ai_description = f"Файл {ext.upper()}, не удалось определить содержимое"
        return info


def info_extension(filepath: str) -> str:
    from pathlib import Path
    return Path(filepath).suffix.lower().lstrip(".") or "без расширения"
