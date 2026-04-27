"""Модуль: общедоступные дистрибутивы (приоритет 20).

Определяет дистрибутивы ПО и установочные пакеты.
Распознает как отдельные исполняемые файлы (.exe, .msi, .dmg и т.д.),
так и распакованные дистрибутивы по наличию setup.exe, install.exe и других индикаторов.
"""

from __future__ import annotations

import os
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import is_executable
from config import EXECUTABLE_EXTS


class DistributablesAnalyzer(BaseAnalyzer):
    """Определяет общедоступные дистрибутивы через SearXNG и локальные индикаторы."""

    def __init__(self):
        self._priority = 20
        self._name = "distributables"
        # Индикаторы распакованного дистрибутива (только ключевые файлы установки)
        self.distributable_indicators = [
            'setup.exe', 'install.exe', 'installer.exe', 'autorun.inf',
            'setup.msi', 'install.msi',
        ]
        # Дополнительные расширения для дистрибутивов
        self.distributable_extensions = {'.exe', '.msi', '.dmg', '.deb', '.rpm', '.apk', '.appimage'}

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def name(self) -> str:
        return self._name

    def can_handle(self, filepath: str) -> bool:
        # Отдельные исполняемые файлы
        if is_executable(filepath):
            return True
        
        # Проверка на индикаторы дистрибутива
        file_name = os.path.basename(filepath).lower()
        if file_name in self.distributable_indicators:
            return True
        
        return False

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        searxng = existing_context.get("searxng")
        from pathlib import Path
        p = Path(filepath)
        file_name = p.name.lower()

        info = self._make_info(filepath)
        info.ai_category = "дистрибутив"

        # Проверяем, является ли файл частью распакованного дистрибутива
        if file_name in self.distributable_indicators:
            dir_path = os.path.dirname(filepath)
            # Это индикатор дистрибутива - помечаем весь каталог как проект
            info.is_part_of_project = True
            info.project_root = dir_path
            info.ai_subcategory = "Распакованный дистрибутив"
            info.algorithmic_reasoning = f"Файл {file_name} является индикатором дистрибутива в {dir_path}"
            info.is_distributable = True
            info.should_delete = True
            return info

        # Одиночный исполняемый файл
        if searxng:
            info.is_distributable = searxng.is_known_distributable(p.name)
        else:
            # Без SearXNG — помечаем как потенциальный дистрибутив
            info.is_distributable = True

        info.should_delete = info.is_distributable
        info.ai_subcategory = "Исполняемый дистрибутив"
        return info
