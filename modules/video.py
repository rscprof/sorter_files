"""Модуль: видео (приоритет 45).

Цепочка анализа:
1. Метаданные (ffprobe) + имя файла → Mini-модель
2. Если неясно → ключевые кадры → мультимодальная модель
3. Если неясно → речь (whisper, первые 60 сек) → Mini-модель
4. Объединение результатов
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo

logger = logging.getLogger(__name__)

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "3gp", "mpg", "mpeg"}


class VideoAnalyzer(BaseAnalyzer):
    """Видео: метаданные → кадры → речь → AI."""

    @property
    def priority(self) -> int:
        return 45

    @property
    def name(self) -> str:
        return "video"

    def can_handle(self, filepath: str) -> bool:
        return Path(filepath).suffix.lower().lstrip(".") in VIDEO_EXTS

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        p = Path(filepath)

        info = self._make_info(filepath)

        # 1. Метаданные через ffprobe
        probe_data = self._probe_video(filepath)
        duration = probe_data.get("duration", 0)
        resolution = probe_data.get("resolution", "")
        has_audio = probe_data.get("has_audio", False)
        size_mb = info.size / (1024 * 1024)

        meta_parts = []
        if duration:
            mins = int(duration // 60)
            secs = int(duration % 60)
            meta_parts.append(f"[{mins}:{secs:02d}]")
        if resolution:
            meta_parts.append(resolution)
        meta_parts.append(f"{size_mb:.0f}MB")
        if has_audio:
            meta_parts.append("🔊")

        context_text = f"Имя: {p.name}, Каталог: {p.parent.name}, Метаданные: {' '.join(meta_parts)}"

        if not localai:
            info.ai_category = "Видео"
            info.ai_description = f"Видео {' '.join(meta_parts)}"
            return info

        # 2. AI по метаданным + имени (Mini-модель, быстро)
        logger.info(f"  → Анализ видео по метаданным (Mini-модель)...")
        ai_result_meta = localai.analyze_content(
            text_content="",
            file_context=context_text,
            existing_categories=existing_categories,
        )

        # Проверяем достаточно ли информации
        if ai_result_meta and ai_result_meta.get("category", "") not in ("Видео", "Неразобранное", ""):
            logger.info(f"  ← Классифицировано по метаданным: {ai_result_meta.get('category')}")
            self._fill_info(info, ai_result_meta, f"Видео {' '.join(meta_parts)}")
            return info

        # 3. Ключевые кадры → VL-модель → Mini-модель
        logger.info(f"  → Извлечение ключевых кадров...")
        frames = self._extract_keyframes(filepath, num_frames=2)
        if frames:
            logger.info(f"  ← Извлечено {len(frames)} кадров, VL-модель описывает...")
            # VL-модель описывает первый кадр
            frame_desc = localai.describe_image(frames[0], context=context_text)
            # Очистка временных кадров
            import shutil
            if frames:
                try:
                    shutil.rmtree(os.path.dirname(frames[0]), ignore_errors=True)
                except Exception:
                    pass

            if frame_desc and len(frame_desc) > 20:
                logger.info(f"  ← Описание: {frame_desc[:150]}...")
                # Mini-модель классифицирует по описанию
                ai_result_frames = localai.analyze_content(
                    text_content=frame_desc,
                    file_context=context_text,
                    existing_categories=existing_categories,
                )
                if ai_result_frames and ai_result_frames.get("category", "") not in ("Видео", "Неразобранное", "Изображения", ""):
                    logger.info(f"  ← Классифицировано по кадрам: {ai_result_frames.get('category')}")
                    self._fill_info(info, ai_result_frames, f"Видео {' '.join(meta_parts)}")
                    info.ai_description = f"Видео {' '.join(meta_parts)}. Кадры: {frame_desc[:200]}"
                    return info

        # 4. Речь (Whisper, первые 60 сек) → Mini-модель
        if has_audio and duration > 5:
            logger.info(f"  → Транскрипция аудио (первые 60с, whisperx-tiny)...")
            transcript = self._transcribe_audio(filepath, localai, duration=60)
            if transcript and len(transcript) > 30:
                logger.info(f"  ← Транскрипт: {len(transcript)} символов")
                ai_result_audio = localai.analyze_content(
                    text_content=transcript[:3000],
                    file_context=context_text,
                    existing_categories=existing_categories,
                )
                if ai_result_audio and ai_result_audio.get("category", "") not in ("Видео", "Неразобранное", ""):
                    logger.info(f"  ← Классифицировано по речи: {ai_result_audio.get('category')}")
                    self._fill_info(info, ai_result_audio, f"Видео {' '.join(meta_parts)}")
                    info.ai_description = f"Видео {' '.join(meta_parts)}. Транскрипт: {transcript[:200]}"
                    return info

        # Fallback
        logger.info(f"  ← Не удалось классифицировать, fallback")
        info.ai_category = "Видео"
        info.ai_description = f"Видео {' '.join(meta_parts)}"
        return info

    def _fill_info(self, info: FileInfo, ai_result: dict, default_desc: str):
        info.ai_category = ai_result.get("category", "Видео")
        info.ai_subcategory = ai_result.get("subcategory", "")
        info.ai_suggested_name = ai_result.get("suggested_name", "")
        if ai_result.get("description"):
            info.ai_description = ai_result["description"]
        else:
            info.ai_description = default_desc
        info.ai_reasoning = ai_result.get("reasoning", "")
        info.is_distributable = ai_result.get("is_distributable", False)

    def _probe_video(self, filepath: str) -> dict:
        """Метаданные видео через ffprobe."""
        result = {}
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", filepath],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                fmt = data.get("format", {})
                result["duration"] = float(fmt.get("duration", 0))
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        w = stream.get("width", "")
                        h = stream.get("height", "")
                        if w and h:
                            result["resolution"] = f"{w}x{h}"
                    if stream.get("codec_type") == "audio":
                        result["has_audio"] = True
        except Exception as e:
            logger.debug(f"ffprobe error: {e}")
        return result

    def _extract_keyframes(self, filepath: str, num_frames: int = 2) -> list[str]:
        """Извлечь ключевые кадры из видео.
        
        Возвращает пути к временным файлам. Вызывающий ОБЯЗАН их удалить.
        Каталог НЕ удаляется автоматически.
        """
        frames = []
        tmpdir = None
        try:
            probe = self._probe_video(filepath)
            duration = probe.get("duration", 0)
            if duration < 2:
                return frames

            # Создаём временный каталог вручную (не TemporaryDirectory)
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix="vid_frames_")

            # Извлекаем кадры в 10% и 50% длительности
            timestamps = []
            if num_frames >= 1:
                timestamps.append(max(1, duration * 0.1))
            if num_frames >= 2:
                timestamps.append(duration * 0.5)
            if num_frames >= 3:
                timestamps.append(duration * 0.9)

            for i, ts in enumerate(timestamps):
                out = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
                r = subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(ts), "-i", filepath,
                     "-frames:v", "1", "-q:v", "3", "-update", "1", out],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 100:
                    frames.append(out)
        except Exception as e:
            logger.debug(f"keyframes error: {e}")
            if tmpdir:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
        return frames

    def _transcribe_audio(self, filepath: str, localai, duration: int = 60) -> str:
        """Транскрибировать первые N секунд аудио через whisper."""
        tmp_audio = None
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_audio = tmp.name

            # Извлекаем аудио
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
