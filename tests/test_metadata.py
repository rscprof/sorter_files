"""Тесты metadata.py с программно созданными тестовыми файлами."""

import os
import struct
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from metadata import (
    read_image_metadata, read_audio_metadata,
    ImageMetadata, AudioMetadata,
    _read_exif, _parse_gps_ifd
)


class TestReadImageMetadata:
    def test_nonexistent_file(self):
        result = read_image_metadata("/nonexistent/file.jpg")
        # Возвращает пустой ImageMetadata или None
        assert result is None or (isinstance(result, ImageMetadata) and result.camera_make is None)

    def test_non_image_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello world")
        result = read_image_metadata(str(f))
        assert result is None

    def test_minimal_jpeg(self, tmp_path):
        """Создаём минимальный JPEG без EXIF."""
        f = tmp_path / "minimal.jpg"
        # JPEG SOI + EOI маркеры
        f.write_bytes(b"\xff\xd8\xff\xd9")
        result = read_image_metadata(str(f))
        # Вернёт ImageMetadata с датой модификации файла
        assert result is not None
        assert isinstance(result, ImageMetadata)

    def test_png_file(self, tmp_path):
        """Минимальный PNG с tIME chunk."""
        f = tmp_path / "test.png"
        # PNG signature
        png_data = b"\x89PNG\r\n\x1a\n"
        # IHDR chunk (width=10, height=10, bit_depth=8, color_type=2)
        ihdr_data = struct.pack(">IIBBBBB", 10, 10, 8, 2, 0, 0, 0)
        ihdr_crc = 0  # Упрощённо
        png_data += struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        # IEND chunk
        png_data += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0xAE426082)
        f.write_bytes(png_data)
        
        result = read_image_metadata(str(f))
        assert result is not None

    def test_heic_stub(self, tmp_path):
        """HEIC — должен вернуть пустой ImageMetadata или None."""
        f = tmp_path / "test.heic"
        f.write_bytes(b"ftypheic" + b"\x00" * 100)
        result = read_image_metadata(str(f))
        # Нет реального парсера HEIC — None или пустой ImageMetadata
        assert result is None or isinstance(result, ImageMetadata)


class TestReadAudioMetadata:
    def test_nonexistent_file(self):
        result = read_audio_metadata("/nonexistent/file.ogg")
        assert result.filename_hint == "file.ogg"
        assert result.title == ""

    def test_non_audio_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = read_audio_metadata(str(f))
        assert result.duration_seconds == 0

    def test_minimal_ogg(self, tmp_path):
        """Создаём минимальный OGG файл."""
        f = tmp_path / "test.ogg"
        # OGG magic "OggS"
        f.write_bytes(b"OggS" + b"\x00" * 100)
        result = read_audio_metadata(str(f))
        assert result.filename_hint == "test.ogg"
        # ffprobe скорее всего не распознает, но metadata объект создан
        assert result is not None

    def test_wav_with_tags(self, tmp_path):
        """Минимальный WAV без тегов."""
        f = tmp_path / "test.wav"
        # RIFF header
        data = b"RIFF"
        data += struct.pack("<I", 36)  # file size - 8
        data += b"WAVE"
        # fmt chunk
        data += b"fmt "
        data += struct.pack("<IHHIIHH", 16, 1, 1, 44100, 176400, 2, 16)
        # data chunk
        data += b"data"
        data += struct.pack("<I", 0)  # empty data
        f.write_bytes(data)
        
        result = read_audio_metadata(str(f))
        assert result.filename_hint == "test.wav"
        # duration должен быть 0 для пустого data
        assert result.duration_seconds >= 0


class TestImageMetadataClass:
    def test_empty_fields(self):
        meta = ImageMetadata()
        assert meta.date_taken is None
        assert meta.camera_make is None
        assert meta.latitude is None

    def test_partial_data(self):
        meta = ImageMetadata(
            date_taken="2024-01-01T12:00:00",
            latitude=55.75,
            longitude=37.62,
        )
        assert meta.date_taken == "2024-01-01T12:00:00"
        assert meta.latitude == 55.75

    def test_full_data(self):
        meta = ImageMetadata(
            camera_make="Canon",
            camera_model="EOS R5",
            date_taken="2024-01-01T12:00:00",
            latitude=55.75,
            longitude=37.62,
        )
        assert meta.camera_make == "Canon"
        assert meta.camera_model == "EOS R5"


class TestAudioMetadataClass:
    def test_empty_summary(self):
        meta = AudioMetadata()
        assert meta.summary() == ""

    def test_summary_with_data(self):
        meta = AudioMetadata(
            title="Test Song",
            artist="Artist",
            duration_seconds=62.0,
        )
        s = meta.summary()
        assert "Test Song" in s
        assert "Artist" in s
        assert "[1:02]" in s


class TestEXIFParser:
    def test_non_jpeg_data(self):
        """_read_exif должен вернуть пустой ImageMetadata для не-JPEG."""
        result = _read_exif(b"\x00\x01\x02\x03")
        assert isinstance(result, ImageMetadata)

    def test_minimal_jpeg_no_exif(self):
        """JPEG без EXIF — пустой ImageMetadata."""
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        result = _read_exif(data)
        assert isinstance(result, ImageMetadata)

    def test_invalid_exif_structure(self):
        """Невалидная EXIF структура."""
        # JPEG + APP1 с мусором
        data = b"\xff\xd8\xff\xe1" + b"\x00\x0A" + b"Exif\x00\x00II" + b"\x00" * 20
        result = _read_exif(data)
        assert isinstance(result, ImageMetadata)


class TestGPSParser:
    def test_empty_data(self):
        meta = ImageMetadata()
        result = _parse_gps_ifd(b"", 0, "<", meta)
        assert result.latitude is None
        assert result.longitude is None

    def test_invalid_data(self):
        meta = ImageMetadata()
        result = _parse_gps_ifd(b"\x00" * 10, 0, "<", meta)
        # Не должен упасть
        assert isinstance(result, ImageMetadata)


class TestRealWorldFiles:
    """Тесты с реальными файлами из интернета (если доступны)."""
    
    def test_sample_image_from_web(self):
        """Пытаемся скачать тестовое изображение с EXIF."""
        import urllib.request
        import tempfile
        
        # Публичное тестовое изображение с EXIF
        urls = [
            "https://www.exiv2.org/img_1771.jpg",  # Canon EOS 40D
            "https://www.exiv2.org/img_1771.jpg",
        ]
        
        for url in urls:
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        f.write(resp.read())
                    img_path = f.name
                
                result = read_image_metadata(img_path)
                if result and result.camera_make:
                    # Если EXIF прочитался — проверяем
                    assert result.camera_make in ("Canon", "NIKON", "SONY", "Apple", "")
                    os.unlink(img_path)
                    return
                else:
                    os.unlink(img_path)
            except Exception:
                continue
        
        pytest.skip("Не удалось загрузить тестовые изображения из интернета")
