"""Модуль: PHP-файлы (приоритет 65 — перед documents)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import extract_text
from projects import find_project_root

logger = logging.getLogger(__name__)


class PhpAnalyzer(BaseAnalyzer):
    """Анализ PHP-файлов: проекты vs одиночные скрипты."""

    @property
    def priority(self) -> int:
        return 65

    @property
    def name(self) -> str:
        return "php"

    def can_handle(self, filepath: str) -> bool:
        ext = Path(filepath).suffix.lower().lstrip(".")
        if ext != "php":
            return False
        # Проверяем, что файл содержит PHP-код
        text = extract_text(filepath)
        return "<?php" in text or "<?" in text

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        p = Path(filepath)

        info = self._make_info(filepath)
        text = extract_text(filepath)

        # Проверяем, является ли файл частью проекта
        project_root = find_project_root(filepath)
        is_project_part = False
        php_files = []

        if project_root:
            # Проверяем, есть ли в проекте другие PHP-файлы
            php_files = self._find_php_files_in_project(project_root)
            if len(php_files) > 1:
                is_project_part = True
                logger.info(f"PHP-файл {filepath} является частью проекта {project_root} ({len(php_files)} PHP-файлов)")
        else:
            # Нет явных индикаторов проекта — проверяем каталог на наличие index.php и других PHP-файлов
            parent_dir = p.parent
            php_in_parent = self._find_php_files_in_directory(parent_dir)
            
            # Если есть index.php и ещё хотя бы один PHP-файл — считаем это проектом
            has_index = any("index.php" in f.lower() for f in php_in_parent)
            if has_index and len(php_in_parent) > 1:
                is_project_part = True
                project_root = str(parent_dir)
                php_files = php_in_parent
                logger.info(f"PHP-файл {filepath} является частью проекта {project_root} (наличие index.php + {len(php_files)} PHP-файлов)")

        if is_project_part:
            # Файл является частью проекта — копируем проект целиком
            info.is_part_of_project = True
            info.project_root = project_root
            info.ai_category = "PHP-проект"
            info.ai_description = f"Часть PHP-проекта в {project_root}"
            info.algorithmic_reasoning = f"Обнаружено {len(php_files)} PHP-файлов в проекте" + (" с index.php" if not find_project_root(filepath) else "")
            return info

        # Одиночный PHP-файл — категоризируем через AI
        if not localai:
            info.ai_category = "PHP-скрипт"
            info.ai_description = f"Одиночный PHP-файл, AI недоступен"
            return info

        # AI-анализ содержимого
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        ai_result = localai.analyze_content(
            text_content=text,
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "PHP-скрипт")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "PHP-скрипт"
            info.ai_description = f"Одиночный PHP-файл без ответа AI"

        return info

    def _find_php_files_in_project(self, project_root: str, max_files: int = 50) -> list[str]:
        """Найти PHP-файлы в проекте."""
        php_files = []
        project_path = Path(project_root)

        # Исключаем build-директории
        exclude_dirs = {
            "vendor", "node_modules", "__pycache__", ".git", "build", "dist",
            "target", "bin", "obj", ".next", ".svelte-kit", "var", "cache",
            "tmp", "storage", "logs",
        }

        for root, dirs, files in os.walk(project_path):
            # Пропускаем исключаемые директории
            dirs[:] = [d for d in dirs if d.lower() not in exclude_dirs]

            for filename in files:
                if filename.lower().endswith(".php"):
                    php_files.append(os.path.join(root, filename))
                    if len(php_files) >= max_files:
                        return php_files

        return php_files

    def _find_php_files_in_directory(self, dirpath: str, max_files: int = 50) -> list[str]:
        """Найти PHP-файлы в указанном каталоге (без рекурсии)."""
        php_files = []
        try:
            entries = os.listdir(dirpath)
        except OSError:
            return php_files

        for entry in entries:
            if entry.lower().endswith(".php"):
                php_files.append(os.path.join(dirpath, entry))
                if len(php_files) >= max_files:
                    break

        return php_files
