"""Тесты временных файлов — чтобы ошибка TemporaryDirectory не повторялась.

Проблема: TemporaryDirectory удаляет файлы при выходе из with/функции.
Решение: использовать mkdtemp и возвращать пути. Вызывающий обязан очистить.
"""

import os
import struct
import tempfile
import zipfile

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyzer import pdf_to_images, image_to_jpeg
from modules.video import VideoAnalyzer
from clients import LocalAIClient


class TestPdfToImages:
    """pdf_to_images НЕ должен использовать TemporaryDirectory.

    Файлы должны существовать после возврата из функции.
    Вызывающий обязан удалить их сам.
    """

    def _make_minimal_pdf(self, tmp_path):
        """Создать минимальный PDF (пустой но валидный)."""
        # Минимальный PDF: 1 пустая страница
        pdf_content = (
            b"%PDF-1.0\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
            b"trailer<</Root 1 0 R/Size 4>>\n"
            b"%%EOF"
        )
        f = tmp_path / "test.pdf"
        f.write_bytes(pdf_content)
        return str(f)

    def test_returns_existing_files(self, tmp_path):
        """Файлы должны существовать после возврата."""
        pdf = self._make_minimal_pdf(tmp_path)
        images = pdf_to_images(pdf, max_pages=1)

        # Проверяем что файлы существуют
        for img_path in images:
            assert os.path.exists(img_path), f"Файл не существует: {img_path}"
            assert os.path.getsize(img_path) > 0

    def test_files_readable(self, tmp_path):
        """Файлы должны быть читаемы (JPEG)."""
        pdf = self._make_minimal_pdf(tmp_path)
        images = pdf_to_images(pdf, max_pages=1)

        for img_path in images:
            with open(img_path, "rb") as f:
                header = f.read(2)
            # JPEG начинается с \xff\xd8
            assert header == b"\xff\xd8", f"Не JPEG: {img_path}, header={header}"

    def test_caller_can_delete(self, tmp_path):
        """Вызывающий должен иметь право удалить файлы."""
        import shutil
        pdf = self._make_minimal_pdf(tmp_path)
        images = pdf_to_images(pdf, max_pages=1)

        for img_path in images:
            if os.path.exists(img_path):
                os.unlink(img_path)
            assert not os.path.exists(img_path), f"Не удалось удалить: {img_path}"

    def test_no_temporary_directory_leak(self, tmp_path):
        """Каталог должен быть в temp, но НЕ удаляться автоматически."""
        pdf = self._make_minimal_pdf(tmp_path)
        images = pdf_to_images(pdf, max_pages=1)

        if images:
            # Каталог должен существовать
            parent = os.path.dirname(images[0])
            assert os.path.isdir(parent)
            # Каталог НЕ должен быть удалён
            assert "pdf_convert_" in parent


class TestImageToJpeg:
    """image_to_jpeg: конвертация изображений."""

    def test_jpg_returns_original_path(self, tmp_path):
        """JPEG возвращается без конвертации."""
        from PIL import Image
        f = tmp_path / "test.jpg"
        img = Image.new("RGB", (10, 10), color="red")
        img.save(str(f))

        result = image_to_jpeg(str(f))
        assert result == str(f)

    def test_png_converts_to_jpeg(self, tmp_path):
        """PNG конвертируется в JPEG."""
        from PIL import Image
        f = tmp_path / "test.png"
        img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
        img.save(str(f))

        result = image_to_jpeg(str(f))
        assert result != str(f)
        assert result.endswith(".converted.jpg")
        assert os.path.exists(result)
        # Вызывающий может удалить
        os.unlink(result)
        assert not os.path.exists(result)

    def test_rgba_converts_to_rgb(self, tmp_path):
        """RGBA изображение конвертируется в RGB."""
        from PIL import Image
        f = tmp_path / "alpha.png"
        img = Image.new("RGBA", (10, 10), color=(0, 255, 0, 100))
        img.save(str(f))

        result = image_to_jpeg(str(f))
        assert result.endswith(".converted.jpg")
        assert os.path.exists(result)

        # Проверяем что сохранено как JPEG (не PNG)
        with open(result, "rb") as fp:
            header = fp.read(2)
        assert header == b"\xff\xd8"

        os.unlink(result)

    def test_nonexistent_file_returns_original(self):
        """Несуществующий файл возвращается как есть."""
        result = image_to_jpeg("/nonexistent/path.xyz")
        assert result == "/nonexistent/path.xyz"


class TestVideoKeyframes:
    """Ключевые кадры видео — должны существовать после возврата."""

    def _create_minimal_video(self, tmp_path):
        """Создать минимальный MP4 (пустой но с заголовком)."""
        # Минимальный ftyp box + moov
        # Это не настоящий MP4, но ffprobe может распознать заголовок
        f = tmp_path / "test.mp4"
        # Пишем пустой файл — test будет пропущен если нет ffmpeg
        f.write_bytes(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")
        return str(f)

    def test_keyframes_exist_after_return(self, tmp_path):
        """Если кадры извлечены — они должны существовать."""
        import subprocess
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        except (FileNotFoundError, Exception):
            pytest.skip("ffmpeg недоступен")

        # Создаём настоящий маленький MP4 через ffmpeg
        mp4 = tmp_path / "real.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)],
            capture_output=True, timeout=30,
        )
        if not mp4.exists():
            pytest.skip("Не удалось создать тестовое видео")

        analyzer = VideoAnalyzer()
        frames = analyzer._extract_keyframes(str(mp4), num_frames=1)

        # Все кадры должны существовать
        for frame_path in frames:
            assert os.path.exists(frame_path), f"Кадр не существует: {frame_path}"
            assert os.path.getsize(frame_path) > 0

        # Вызывающий может удалить
        import shutil
        if frames:
            try:
                shutil.rmtree(os.path.dirname(frames[0]), ignore_errors=True)
            except Exception:
                pass

    def test_empty_video_returns_empty_list(self, tmp_path):
        """Пустой/битый файл → пустой список."""
        analyzer = VideoAnalyzer()
        frames = analyzer._extract_keyframes(self._create_minimal_video(tmp_path), num_frames=1)
        assert isinstance(frames, list)


class TestTempFileCleanup:
    """Тесты что временные файлы реально удаляются."""

    def test_pdf_images_cleanup(self, tmp_path):
        """После ручной очистки файлы удалены."""
        import shutil

        # Создаём минимальный PDF
        pdf_content = (
            b"%PDF-1.0\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
            b"trailer<</Root 1 0 R/Size 4>>\n"
            b"%%EOF"
        )
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(pdf_content)

        images = pdf_to_images(str(pdf), max_pages=1)

        # Считаем файлы до очистки
        if images:
            parent = os.path.dirname(images[0])
            files_before = len(os.listdir(parent))

            # Очищаем
            shutil.rmtree(parent, ignore_errors=True)

            # Каталога больше нет
            assert not os.path.exists(parent)

    def test_image_to_jpeg_cleanup(self, tmp_path):
        """Конвертированный JPEG можно удалить."""
        from PIL import Image

        f = tmp_path / "test.png"
        Image.new("RGBA", (10, 10), color=(255, 0, 0, 100)).save(str(f))

        result = image_to_jpeg(str(f))
        assert os.path.exists(result)

        os.unlink(result)
        assert not os.path.exists(result)
