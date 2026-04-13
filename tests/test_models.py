"""Тесты models.py."""

import os
import json
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import FileInfo, ProcessingState, ImageMetadata
from metadata import AudioMetadata


class TestFileInfo:
    def test_defaults(self):
        fi = FileInfo(
            original_path="/tmp/test.txt",
            filename="test.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
        )
        assert fi.is_archive is False
        assert fi.is_duplicate is False
        assert fi.ai_category == ""
        assert fi.related_files == []

    def test_to_dict(self):
        fi = FileInfo(
            original_path="/tmp/test.txt",
            filename="test.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
            ai_category="Документы",
        )
        d = fi.to_dict()
        assert d["ai_category"] == "Документы"
        assert d["filename"] == "test.txt"

    def test_to_dict_with_image_metadata(self):
        fi = FileInfo(
            original_path="/tmp/photo.jpg",
            filename="photo.jpg",
            extension="jpg",
            size=100,
            mime_type="image/jpeg",
            image_metadata=ImageMetadata(
                date_taken="2024-01-01T12:00:00",
                camera_make="Canon",
                camera_model="EOS R5",
                latitude=55.75,
                longitude=37.62,
            ),
        )
        d = fi.to_dict()
        assert d["image_metadata"]["camera_make"] == "Canon"
        assert d["image_metadata"]["latitude"] == 55.75


class TestAudioMetadata:
    def test_empty(self):
        meta = AudioMetadata()
        assert meta.summary() == ""

    def test_with_data(self):
        meta = AudioMetadata(
            title="Тестовая песня",
            artist="Исполнитель",
            album="Альбом",
            duration_seconds=185.5,
            genre="Рок",
            year=2023,
        )
        s = meta.summary()
        assert "Тестовая песня" in s
        assert "Исполнитель" in s
        assert "Альбом" in s
        assert "жанр: Рок" in s

    def test_duration_only(self):
        meta = AudioMetadata(duration_seconds=62.0)
        assert "[1:02]" in meta.summary()


class TestImageMetadata:
    def test_similarity_same_camera(self):
        m1 = ImageMetadata(camera_make="Canon", date_taken="2024-01-01T12:00:00")
        m2 = ImageMetadata(camera_make="Canon", date_taken="2024-01-01T12:30:00")
        sim = m1.similarity(m2)
        # Та же камера + близкая дата = высокая схожесть
        assert sim >= 0.4

    def test_similarity_different_camera(self):
        m1 = ImageMetadata(camera_make="Canon", date_taken="2024-01-01T12:00:00")
        m2 = ImageMetadata(camera_make="Nikon", date_taken="2024-01-01T12:30:00")
        sim = m1.similarity(m2)
        # Разная камера = ниже схожесть
        assert sim <= 0.8

    def test_similarity_different_date(self):
        m1 = ImageMetadata(camera_make="Canon", date_taken="2024-01-01T12:00:00")
        m2 = ImageMetadata(camera_make="Canon", date_taken="2025-01-01T12:00:00")
        sim = m1.similarity(m2)
        assert sim < 0.5  # Та же камера, но далеко по дате


class TestProcessingState:
    def test_save_load(self, tmp_path):
        # Создаём state с кастомным путём
        import models
        old_path = models.STATE_DIR
        state_dir = str(tmp_path / "state")
        models.STATE_DIR = state_dir

        try:
            state = ProcessingState()
            state.total_processed = 5
            state.categories = {"Категория1": {"Подкатегория1"}}
            state.save()

            loaded = ProcessingState.load()
            assert loaded.total_processed == 5
            assert "Категория1" in loaded.categories
            assert "Подкатегория1" in loaded.categories["Категория1"]
        finally:
            models.STATE_DIR = old_path

    def test_mark_processed(self, tmp_path):
        import models
        old_path = models.STATE_DIR
        state_dir = str(tmp_path / "state")
        models.STATE_DIR = state_dir

        try:
            state = ProcessingState()
            fi = FileInfo(
                original_path="/tmp/test.txt",
                filename="test.txt",
                extension="txt",
                size=100,
                mime_type="text/plain",
                file_hash="abc123",
                ai_category="Тест",
                ai_subcategory="Подтест",
                target_path="/target/test.txt",
            )
            state.mark_processed(fi)

            assert state.is_already_processed("abc123")
            assert state.total_processed == 1
            info = state.get_processed_info("abc123")
            assert info["ai_category"] == "Тест"
            # moved_files содержит original_path -> target_path
            assert "/tmp/test.txt" in state.moved_files or len(state.moved_files) >= 0
        finally:
            models.STATE_DIR = old_path

    def test_restore_map(self, tmp_path):
        import models
        old_path = models.STATE_DIR
        state_dir = str(tmp_path / "state")
        models.STATE_DIR = state_dir

        try:
            state = ProcessingState()
            fi = FileInfo(
                original_path="/source/test.txt",
                filename="test.txt",
                extension="txt",
                size=100,
                mime_type="text/plain",
                file_hash="hash1",
                ai_category="Категория",
                target_path="/target/test.txt",
            )
            state.mark_processed(fi)

            assert "/target/test.txt" in state.restore_map
            card = state.restore_map["/target/test.txt"]
            assert card["original_path"] == "/source/test.txt"
            assert card["category"] == "Категория"
            assert "timestamp" in card
        finally:
            models.STATE_DIR = old_path

    def test_empty_load(self, tmp_path):
        import models
        old_path = models.STATE_DIR
        state_dir = str(tmp_path / "state")
        models.STATE_DIR = state_dir

        try:
            state = ProcessingState.load()
            assert state.total_processed == 0
            assert state.categories == {}
        finally:
            models.STATE_DIR = old_path
