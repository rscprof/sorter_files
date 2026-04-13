"""Модуль: изображения (приоритет 60).

Двухэтапный подход:
1. qwen3-vl-4b-instruct описывает изображение → текст
2. Qwen3.5-35B-A3B-APEX-Mini.gguf классифицирует по тексту
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import is_image, image_to_jpeg
from metadata import read_image_metadata

logger = logging.getLogger(__name__)


class ImagesAnalyzer(BaseAnalyzer):
    """Изображения: EXIF → JPEG конвертация → VL describe → Mini classify."""

    @property
    def priority(self) -> int:
        return 60

    @property
    def name(self) -> str:
        return "images"

    def can_handle(self, filepath: str) -> bool:
        return is_image(filepath)

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)
        info.image_metadata = read_image_metadata(filepath)

        if not localai:
            info.ai_category = "Изображения"
            info.ai_description = "Изображение, AI недоступен"
            return info

        # Конвертация в JPEG если нужно
        temp_jpeg_path = ""
        image_for_vl = filepath
        ext_lower = info.extension.lower()
        if ext_lower not in ("jpg", "jpeg"):
            logger.info(f"  → Конвертация {ext_lower.upper()} → JPEG...")
            temp_jpeg_path = image_to_jpeg(filepath)
            image_for_vl = temp_jpeg_path
            if temp_jpeg_path != filepath:
                logger.info(f"  ← Готово: {Path(temp_jpeg_path).name}")

        # Этап 1: VL-модель описывает изображение
        logger.info(f"  → VL-модель описывает изображение...")
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        if info.image_metadata:
            md = info.image_metadata
            parts = []
            if md.camera_make:
                parts.append(f"{md.camera_make} {md.camera_model or ''}")
            if md.date_taken:
                parts.append(md.date_taken[:16].replace("T", " "))
            if parts:
                context += f", EXIF: {', '.join(parts)}"

        description = localai.describe_image(image_for_vl, context=context)

        if not description:
            logger.info(f"  ⚠ VL-модель не смогла описать изображение")
            info.ai_category = "Изображения"
            info.ai_description = "Изображение, не удалось описать"
            # Очистка
            if temp_jpeg_path and temp_jpeg_path != filepath:
                try:
                    os.remove(temp_jpeg_path)
                except Exception:
                    pass
            return info

        logger.info(f"  ← Описание: {description[:150]}...")

        # Этап 2: Mini-модель классифицирует по описанию
        ai_result = localai.analyze_content(
            text_content=description,
            file_context=context,
            existing_categories=existing_categories,
        )

        # Очистка временного JPEG
        if temp_jpeg_path and temp_jpeg_path != filepath:
            try:
                os.remove(temp_jpeg_path)
            except Exception:
                pass

        if ai_result:
            info.ai_category = ai_result.get("category", "Изображения")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", description[:150])
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "Изображения"
            info.ai_description = description[:150]

        return info
