"""Модуль: PDF-сканы (приоритет 50)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import extract_text, pdf_to_images

logger = logging.getLogger(__name__)


class PdfScansAnalyzer(BaseAnalyzer):
    """PDF без текста — конвертируем в JPEG → мультимодальный AI с OCR."""

    @property
    def priority(self) -> int:
        return 50

    @property
    def name(self) -> str:
        return "pdf_scans"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        ext = Path(filepath).suffix.lower().lstrip(".")
        if ext != "pdf":
            return False
        # Проверяем есть ли текст
        text = extract_text(filepath)
        return not text or len(text) < 50

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)

        if not localai:
            info.ai_category = "PDF (скан)"
            info.ai_description = "PDF без текста, AI недоступен"
            return info

        # Конвертируем PDF → JPEG
        logger.info(f"  → PDF без текста, конвертирую в JPEG...")
        pdf_images = pdf_to_images(filepath, max_pages=3)
        if not pdf_images:
            info.ai_category = "PDF (скан)"
            info.ai_description = "Не удалось конвертировать PDF в изображения"
            return info

        logger.info(f"  ← Создано {len(pdf_images)} JPEG, VL-модель описывает...")

        # Этап 1: VL-модель описывает первый кадр
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        description = localai.describe_image(pdf_images[0], context=context)

        # Очистка временных файлов
        for img in pdf_images:
            try:
                os.remove(img)
            except Exception:
                pass

        if not description:
            info.ai_category = "PDF (скан)"
            info.ai_description = "VL-модель не смогла описать PDF-скан"
            return info

        logger.info(f"  ← Описание: {description[:200]}...")

        # Этап 2: Mini-модель классифицирует по описанию
        ai_result = localai.analyze_content(
            text_content=description,
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "Документы")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", description[:150])
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "PDF (скан)"
            info.ai_description = description[:150]

        return info
