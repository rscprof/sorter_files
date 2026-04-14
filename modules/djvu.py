"""Модуль: DJVU документы (приоритет 49).

DJVU конвертируется в JPEG через ddjvu → VL-описание → AI классификация.
Аналогично PDF-сканам, но для DJVU формата.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo

logger = logging.getLogger(__name__)


class DjvuAnalyzer(BaseAnalyzer):
    """DJVU документы → JPEG → VL-описание → AI классификация."""

    @property
    def priority(self) -> int:
        return 49

    @property
    def name(self) -> str:
        return "djvu"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        return Path(filepath).suffix.lower().lstrip(".") in ("djvu", "djv")

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)

        if not localai:
            info.ai_category = "Документы"
            info.ai_description = "DJVU документ, AI недоступен"
            return info

        # Конвертируем DJVU → JPEG через ddjvu
        logger.info(f"  → Конвертация DJVU → JPEG...")
        jpeg_path = self._djvu_to_jpeg(filepath)
        if not jpeg_path:
            # Fallback: пробуем извлечь текст
            text = self._extract_djvu_text(filepath)
            if text:
                logger.info(f"  ← Извлечён текст: {len(text)} символов")
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
                    info.ai_description = "DJVU документ с текстом"
                return info

            info.ai_category = "Документы"
            info.ai_description = "DJVU документ, не удалось конвертировать"
            return info

        logger.info(f"  ← Создан JPEG, VL-модель описывает...")

        # Этап 1: VL-модель описывает JPEG
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        description = localai.describe_image(jpeg_path, context=context)

        # Очистка временного JPEG
        try:
            os.unlink(jpeg_path)
        except Exception:
            pass

        if not description:
            info.ai_category = "Документы"
            info.ai_description = "DJVU документ, VL-модель не смогла описать"
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
            info.ai_category = "Документы"
            info.ai_description = description[:150]

        return info

    def _djvu_to_jpeg(self, filepath: str, quality: int = 90) -> Optional[str]:
        """Конвертировать первую страницу DJVU в JPEG через ddjvu."""
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="djvu_convert_")
        jpeg_path = os.path.join(tmpdir, "page.jpg")

        try:
            # ddjvu -format=ppm -page=1 file.djvu | cjpeg > page.jpg
            # Или проще: ddjvu -format=tiff -page=1 file.djvu page.tiff
            # Но лучше: ddjvu -format=jpeg -page=1 file.djvu page.jpg
            result = subprocess.run(
                ["ddjvu", "-format=jpeg", "-page=1",
                 f"-quality={quality}", filepath, jpeg_path],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(jpeg_path):
                return jpeg_path
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"ddjvu error: {e}")
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
            return None

        # Fallback: ddjvu → ppm → jpeg через ImageMagick/Pillow
        try:
            ppm_path = os.path.join(tmpdir, "page.ppm")
            result = subprocess.run(
                ["ddjvu", "-format=ppm", "-page=1", filepath, ppm_path],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(ppm_path):
                from PIL import Image
                img = Image.open(ppm_path)
                img.save(jpeg_path, "JPEG", quality=quality)
                os.unlink(ppm_path)
                return jpeg_path
        except Exception as e:
            logger.debug(f"ddjvu ppm fallback error: {e}")

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        return None

    def _extract_djvu_text(self, filepath: str) -> str:
        """Извлечь текст из DJVU через djvutxt."""
        try:
            result = subprocess.run(
                ["djvutxt", filepath],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout[:5000]
        except (FileNotFoundError, Exception):
            pass

        # Fallback: ddjvu → pdftotext
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                pdf_path = tmp.name
            result = subprocess.run(
                ["ddjvu", "-format=pdf", filepath, pdf_path],
                capture_output=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(pdf_path):
                # Используем _extract_pdf из analyzer
                from analyzer import _extract_pdf
                text = _extract_pdf(pdf_path)
                os.unlink(pdf_path)
                return text
        except Exception:
            pass

        return ""
