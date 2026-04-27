"""Модуль: документы с текстом (приоритет 70)."""

from __future__ import annotations

import logging
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import extract_text

logger = logging.getLogger(__name__)


class DocumentsAnalyzer(BaseAnalyzer):
    """Файлы с извлекаемым текстом: TXT, DOCX, XLSX, PPTX, PDF с текстом, код и т.д."""

    @property
    def priority(self) -> int:
        return 75

    @property
    def name(self) -> str:
        return "documents"

    def can_handle(self, filepath: str) -> bool:
        text = extract_text(filepath)
        return bool(text) and not text.startswith("[") and len(text) >= 10

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)
        text = extract_text(filepath)

        if not localai:
            info.ai_category = "Документы"
            info.ai_description = f"Документ {info.extension.upper()}, AI недоступен"
            return info

        # AI-анализ
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        ai_result = localai.analyze_content(
            text_content=text,
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "Документы")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "Документы"
            info.ai_description = f"Документ {info.extension.upper()} без ответа AI"

        return info
