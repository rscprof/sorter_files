"""Модуль: видео (приоритет 45)."""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo

logger = logging.getLogger(__name__)

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "3gp", "mpg", "mpeg"}


class VideoAnalyzer(BaseAnalyzer):
    """Видео: метаданные через ffprobe → AI по описанию."""

    @property
    def priority(self) -> int:
        return 45

    @property
    def name(self) -> str:
        return "video"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        return Path(filepath).suffix.lower().lstrip(".") in VIDEO_EXTS

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)

        # Метаданные через ffprobe
        duration = ""
        resolution = ""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet", "-print_format", "json",
                    "-show_format", "-show_streams", filepath
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                dur = float(fmt.get("duration", 0))
                if dur:
                    mins = int(dur // 60)
                    secs = int(dur % 60)
                    duration = f"[{mins}:{secs:02d}]"
                # Видео-поток
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        w = stream.get("width", "")
                        h = stream.get("height", "")
                        if w and h:
                            resolution = f"{w}x{h}"
                        break
        except Exception:
            pass

        size_mb = info.size / (1024 * 1024)
        meta_parts = []
        if duration:
            meta_parts.append(duration)
        if resolution:
            meta_parts.append(resolution)
        meta_parts.append(f"{size_mb:.0f}MB")
        meta_str = " ".join(meta_parts)

        info.ai_description = f"Видео {meta_str}"

        if not localai:
            info.ai_category = "Видео"
            return info

        # AI-анализ по имени и метаданным
        context = f"Имя: {p.name}, Каталог: {p.parent.name}, Метаданные: {meta_str}"
        ai_result = localai.analyze_content(
            text_content="",
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "Видео")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            if ai_result.get("description"):
                info.ai_description = ai_result["description"]
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "Видео"

        return info
