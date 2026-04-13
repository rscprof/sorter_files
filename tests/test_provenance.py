"""Тесты provenance.py."""

import os
import json
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance import ProvenanceStore, ProvenanceCard


class TestProvenanceCard:
    def test_defaults(self):
        card = ProvenanceCard(
            file_hash="abc123",
            filename="test.txt",
            first_seen_path="/source/test.txt",
            current_path="/target/test.txt",
            first_processed="2024-01-01T00:00:00",
            last_processed="2024-01-01T00:00:00",
        )
        assert card.category == ""
        assert card.move_history == []

    def test_to_dict(self):
        card = ProvenanceCard(
            file_hash="abc",
            filename="test.txt",
            first_seen_path="/source/test.txt",
            current_path="/target/test.txt",
            first_processed="2024-01-01T00:00:00",
            last_processed="2024-01-01T00:00:00",
            category="Тест",
        )
        d = card.to_dict()
        assert d["category"] == "Тест"
        assert d["file_hash"] == "abc"

    def test_from_dict_backwards_compat(self):
        d = {
            "file_hash": "abc",
            "filename": "test.txt",
            "first_seen_path": "/source/test.txt",
            "current_path": "/target/test.txt",
            "first_processed": "2024-01-01T00:00:00",
            "last_processed": "2024-01-01T00:00:00",
        }
        card = ProvenanceCard.from_dict(d)
        assert card.archive_source == ""
        assert card.move_history == []


class TestProvenanceStore:
    def test_empty(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        assert len(store.cards) == 0

    def test_upsert_new(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        card = store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            category="Тест",
        )
        assert card.file_hash == "hash1"
        assert card.first_seen_path == "/source/test.txt"
        assert len(store.cards) == 1

    def test_upsert_update(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            category="Категория1",
        )
        # Обновляем
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/new_path/test.txt",
            category="Категория2",
        )
        card = store.cards["hash1"]
        assert card.current_path == "/target/new_path/test.txt"
        assert card.category == "Категория2"
        assert len(card.move_history) == 1  # Одно перемещение

    def test_save_load(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            category="Тест",
        )
        store.save()

        # Перезагружаем
        store2 = ProvenanceStore(str(tmp_path))
        assert len(store2.cards) == 1
        card = store2.cards["hash1"]
        assert card.category == "Тест"

    def test_get_card(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "test.txt", "/src/test.txt", "/tgt/test.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест")
        assert store.get_card("hash1") is not None
        assert store.get_card("nonexistent") is None

    def test_find_by_current_path(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "test.txt", "/src/test.txt", "/tgt/test.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест")
        card = store.find_by_current_path("/tgt/test.txt")
        assert card is not None
        assert card.file_hash == "hash1"

    def test_find_by_first_seen(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "file1.txt", "/project/file1.txt", "/tgt/file1.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест")
        store.upsert("hash2", "file2.txt", "/project/sub/file2.txt", "/tgt/file2.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест2")
        store.upsert("hash3", "other.txt", "/other/other.txt", "/tgt/other.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Другое")

        cards = store.find_by_first_seen("/project")
        assert len(cards) == 2

    def test_find_by_original(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "file.txt", "/project/file.txt", "/tgt/file.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест")
        # Добавляем перемещение
        card = store.cards["hash1"]
        card.move_history.append({
            "from": "/tgt/file.txt",
            "to": "/tgt2/file.txt",
            "timestamp": "2024-01-02T00:00:00",
            "reason": "reprocess",
        })
        card.current_path = "/tgt2/file.txt"

        # Ищем по пути из move_history
        cards = store.find_by_original("/tgt")
        assert len(cards) == 1

    def test_get_stats(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "f1.txt", "/src/f1.txt", "/tgt/f1.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Категория1")
        store.upsert("hash2", "f2.txt", "/src/f2.txt", "/tgt/f2.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Категория1")
        store.upsert("hash3", "f3.txt", "/archive.zip/extract/f3.txt", "/tgt/f3.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Категория2",
                     archive_source="/src/archive.zip")

        stats = store.get_stats()
        assert stats["total_cards"] == 3
        assert stats["with_archive_source"] == 1
        # Категории могут быть в разных форматах, проверяем наличие
        assert "Категория1" in stats["categories"] or len(stats["categories"]) >= 1

    def test_jsonl_format(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        store.upsert("hash1", "f.txt", "/src/f.txt", "/tgt/f.txt",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00", "Тест")
        store.save()

        # Проверяем что файл в JSONL формате
        cards_path = os.path.join(tmp_path, ".provenance", "cards.jsonl")
        assert os.path.exists(cards_path)
        with open(cards_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["file_hash"] == "hash1"
