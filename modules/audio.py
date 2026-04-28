"""Модуль: аудио (приоритет 40)."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from analyzer import AUDIO_EXTS
from config import ANALYSIS_AUDIO_TRANSCRIBE_SECONDS
from metadata import read_audio_metadata

logger = logging.getLogger(__name__)


class AudioAnalyzer(BaseAnalyzer):
    """Аудио: метаданные → whisper транскрипция → AI анализ."""

    @property
    def priority(self) -> int:
        return 40

    @property
    def name(self) -> str:
        return "audio"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        return Path(filepath).suffix.lower().lstrip(".") in AUDIO_EXTS

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)
        info.audio_metadata = read_audio_metadata(filepath)

        # Транскрипция через Whisper (только первые N секунд)
        transcript = ""
        if localai:
            logger.info(f"  → Транскрипция аудио (первые {ANALYSIS_AUDIO_TRANSCRIBE_SECONDS}с, whisperx-tiny)...")
            transcript = self._transcribe_audio(filepath, localai, duration=ANALYSIS_AUDIO_TRANSCRIBE_SECONDS)
            info.audio_transcript = transcript
            logger.info(f"  ← Транскрипт: {len(transcript)} символов")

        # AI-анализ по транскрипту
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        if info.audio_metadata:
            meta_summary = info.audio_metadata.summary()
            if meta_summary:
                context += f", Метаданные: {meta_summary}"

        ai_result = {}
        if localai and transcript:
            ai_result = localai.analyze_content(
                text_content=transcript,
                file_context=context,
                existing_categories=existing_categories,
            )

        if ai_result:
            info.ai_category = ai_result.get("category", "Аудио")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            # Fallback: только по метаданным
            info.ai_category = "Аудио"
            if info.audio_metadata:
                info.ai_description = info.audio_metadata.summary()
            else:
                info.ai_description = f"Аудио {info.extension.upper()}"

        return info

    def _transcribe_audio(self, filepath: str, localai, duration: int = 60) -> str:
        """Транскрибировать первые N секунд аудио через whisper."""
        tmp_audio = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_audio = tmp.name

            r = subprocess.run(
                ["ffmpeg", "-y", "-ss", "0", "-t", str(duration),
                 "-i", filepath, "-vn", "-ac", "1", "-ar", "16000", tmp_audio],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0 or not os.path.exists(tmp_audio):
                return ""

            transcript = localai.transcribe_audio(tmp_audio)

            return transcript
        except Exception as e:
            logger.debug(f"transcribe error: {e}")
            return ""
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except Exception:
                    pass
