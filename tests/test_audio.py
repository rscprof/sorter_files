"""Тесты для модуля audio."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import os
import sys

sys.path.insert(0, '/workspace')

from modules.audio import AudioAnalyzer
from models import FileInfo
from metadata import AudioMetadata


class TestAudioAnalyzerProperties:
    """Тесты свойств анализатора аудио."""

    def setup_method(self):
        self.analyzer = AudioAnalyzer()

    def test_priority(self):
        assert self.analyzer.priority == 40

    def test_name(self):
        assert self.analyzer.name == "audio"


class TestAudioAnalyzerCanHandle:
    """Тесты метода can_handle."""

    def setup_method(self):
        self.analyzer = AudioAnalyzer()

    def test_mp3_file(self):
        assert self.analyzer.can_handle("test.mp3") is True

    def test_wav_file(self):
        assert self.analyzer.can_handle("test.wav") is True

    def test_flac_file(self):
        assert self.analyzer.can_handle("test.flac") is True

    def test_ogg_file(self):
        assert self.analyzer.can_handle("test.ogg") is True

    def test_m4a_file(self):
        assert self.analyzer.can_handle("test.m4a") is True

    def test_aac_file(self):
        assert self.analyzer.can_handle("test.aac") is True

    def test_wma_file(self):
        assert self.analyzer.can_handle("test.wma") is True

    def test_txt_file(self):
        assert self.analyzer.can_handle("test.txt") is False

    def test_pdf_file(self):
        assert self.analyzer.can_handle("test.pdf") is False

    def test_case_insensitive(self):
        assert self.analyzer.can_handle("TEST.MP3") is True
        assert self.analyzer.can_handle("Test.Wav") is True


class TestAudioAnalyzerAnalyze:
    """Тесты метода analyze."""

    def setup_method(self):
        self.analyzer = AudioAnalyzer()
        self.filepath = "/tmp/test_audio.mp3"
        
        # Создаем фиктивный файл
        Path(self.filepath).touch()

    def teardown_method(self):
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

    def test_analyze_without_localai(self):
        """Анализ без LocalAI должен вернуть базовую информацию."""
        context = {}
        
        with patch('modules.audio.read_audio_metadata', return_value=None):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info is not None
        assert isinstance(info, FileInfo)
        assert info.ai_category == "Аудио"
        assert info.extension == "mp3"

    def test_analyze_with_metadata_no_localai(self):
        """Анализ с метаданными но без LocalAI."""
        context = {}
        mock_metadata = AudioMetadata(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration_seconds=180
        )
        
        with patch('modules.audio.read_audio_metadata', return_value=mock_metadata):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info is not None
        assert info.ai_category == "Аудио"
        assert info.audio_metadata is not None
        assert info.audio_metadata.title == "Test Song"

    def test_analyze_with_localai_no_transcript(self):
        """Анализ с LocalAI но без транскрипции."""
        mock_localai = Mock()
        mock_localai.transcribe_audio.return_value = ""
        context = {"localai": mock_localai}
        
        with patch('modules.audio.read_audio_metadata', return_value=None):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info is not None
        assert info.ai_category == "Аудио"
        mock_localai.transcribe_audio.assert_called_once()

    def test_analyze_with_localai_and_transcript(self):
        """Анализ с LocalAI и транскрипцией."""
        mock_localai = Mock()
        mock_localai.transcribe_audio.return_value = "Это тестовая транскрипция"
        mock_localai.analyze_content.return_value = {
            "category": "Музыка",
            "subcategory": "Рок",
            "suggested_name": "test_song",
            "description": "Тестовое описание",
            "reasoning": "Тестовое обоснование",
            "is_distributable": False
        }
        context = {"localai": mock_localai, "categories_context": ""}
        
        with patch('modules.audio.read_audio_metadata', return_value=None):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info is not None
        assert info.ai_category == "Музыка"
        assert info.ai_subcategory == "Рок"
        assert info.ai_description == "Тестовое описание"
        assert info.audio_transcript == "Это тестовая транскрипция"
        mock_localai.transcribe_audio.assert_called_once()
        mock_localai.analyze_content.assert_called_once()

    def test_analyze_with_metadata_and_localai(self):
        """Анализ с метаданными и LocalAI."""
        mock_localai = Mock()
        mock_localai.transcribe_audio.return_value = "Транскрипция"
        mock_localai.analyze_content.return_value = {
            "category": "Подкаст",
            "description": "Описание подкаста"
        }
        mock_metadata = AudioMetadata(
            title="Podcast Episode",
            duration_seconds=3600
        )
        context = {"localai": mock_localai, "categories_context": ""}
        
        with patch('modules.audio.read_audio_metadata', return_value=mock_metadata):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info is not None
        assert info.ai_category == "Подкаст"
        assert info.audio_metadata is not None

    def test_analyze_preserves_file_info(self):
        """Проверка сохранения базовой информации о файле."""
        context = {}
        
        with patch('modules.audio.read_audio_metadata', return_value=None):
            info = self.analyzer.analyze(self.filepath, context)
        
        assert info.original_path == self.filepath
        assert info.filename == "test_audio.mp3"
        assert info.extension == "mp3"
        assert info.size == 0  # Файл пустой


class TestAudioAnalyzerEdgeCases:
    """Тесты граничных случаев."""

    def setup_method(self):
        self.analyzer = AudioAnalyzer()

    def test_empty_context(self):
        """Анализ с пустым контекстом."""
        filepath = "/tmp/test.mp3"
        Path(filepath).touch()
        
        try:
            with patch('modules.audio.read_audio_metadata', return_value=None):
                info = self.analyzer.analyze(filepath, {})
            assert info is not None
        finally:
            os.remove(filepath)

    def test_nonexistent_file_metadata(self):
        """Поведение при несуществующем файле для метаданных."""
        filepath = "/tmp/nonexistent_audio.mp3"
        context = {}
        
        with patch('modules.audio.read_audio_metadata', side_effect=Exception("File not found")):
            with pytest.raises(Exception):
                self.analyzer.analyze(filepath, context)

    def test_various_audio_extensions(self):
        """Проверка различных аудио расширений."""
        extensions = ["mp3", "wav", "flac", "ogg", "m4a", "aac", "wma", "MP3", "WAV"]
        for ext in extensions:
            filepath = f"/tmp/test.{ext}"
            Path(filepath).touch()
            try:
                assert self.analyzer.can_handle(filepath) is True
            finally:
                os.remove(filepath)
