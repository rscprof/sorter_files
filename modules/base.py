"""Базовый класс анализатора файлов."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from models import FileInfo


class BaseAnalyzer(ABC):
    """
    Базовый анализатор файлов.
    
    Каждый анализатор определяет, может ли он обработать файл (can_handle),
    и если да — возвращает результат (analyze).
    
    Анализаторы вызываются orchestrator-ом в порядке priority (от меньшего к большему).
    Первый подходящий анализатор обрабатывает файл.
    """

    @property
    @abstractmethod
    def priority(self) -> int:
        """Приоритет анализатора. Меньше = раньше вызывается."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Название анализатора (для логов)."""
        ...

    @abstractmethod
    def can_handle(self, filepath: str) -> bool:
        """Может ли этот анализатор обработать файл?"""
        ...

    @abstractmethod
    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        """
        Проанализировать файл и вернуть FileInfo.
        
        existing_context — данные, собранные предыдущими анализаторами:
          - categories: {category: {subcategories}}
          - state: ProcessingState
          - localai: LocalAIClient
          - searxng: SearXNGClient
        """
        ...

    @staticmethod
    def _make_info(filepath: str, **kwargs) -> FileInfo:
        """Создать FileInfo с заполненными базовыми полями."""
        p = Path(filepath)
        ext = p.suffix.lower().lstrip(".")
        import os
        size = os.path.getsize(filepath)
        import mimetypes
        mime, _ = mimetypes.guess_type(filepath)

        return FileInfo(
            original_path=filepath,
            filename=p.name,
            extension=ext,
            size=size,
            mime_type=mime or "unknown",
            **kwargs,
        )
