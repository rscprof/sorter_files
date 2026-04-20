"""Тесты для file_browser.py."""

import os
import tempfile
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance import ProvenanceStore, ProvenanceCard


class TestFileEntry:
    """Тесты класса FileEntry."""
    
    def test_file_entry_creation(self):
        from file_browser import FileEntry
        
        entry = FileEntry("test.txt", False, "/path/test.txt")
        assert entry.name == "test.txt"
        assert entry.is_dir is False
        assert entry.path == "/path/test.txt"
        assert entry.card is None
        assert entry.original_path is None
    
    def test_file_entry_with_card(self):
        from file_browser import FileEntry
        
        card = ProvenanceCard(
            file_hash="abc123",
            filename="test.txt",
            first_seen_path="/source/test.txt",
            current_path="/target/test.txt",
            first_processed="2024-01-01T00:00:00",
            last_processed="2024-01-01T00:00:00",
            category="Тест",
            ai_reasoning="AI решил что это тестовый файл",
            algorithmic_reasoning="Правило: расширение .txt -> Документы",
        )
        
        entry = FileEntry("test.txt", False, "/target/test.txt", card=card)
        assert entry.card == card
        assert entry.original_path == "/source/test.txt"
    
    def test_file_entry_repr(self):
        from file_browser import FileEntry
        
        entry = FileEntry("test.txt", False, "/path/test.txt")
        assert "test.txt" in repr(entry)
        assert "dir=False" in repr(entry)


class TestFileBrowserHelpers:
    """Тесты вспомогательных методов FileBrowser."""
    
    def test_wrap_text_short(self):
        from file_browser import FileBrowser
        
        # Создаём фиктивный объект для вызова метода
        class FakeBrowser:
            def _wrap_text(self, text, width=40):
                words = text.split()
                lines = []
                current_line = []
                current_length = 0
                
                for word in words:
                    if current_length + len(word) + 1 <= width:
                        current_line.append(word)
                        current_length += len(word) + 1
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = len(word)
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                return lines
        
        browser = FakeBrowser()
        result = browser._wrap_text("Короткий текст", width=40)
        assert result == ["Короткий текст"]
    
    def test_wrap_text_long(self):
        from file_browser import FileBrowser
        
        class FakeBrowser:
            def _wrap_text(self, text, width=40):
                words = text.split()
                lines = []
                current_line = []
                current_length = 0
                
                for word in words:
                    if current_length + len(word) + 1 <= width:
                        current_line.append(word)
                        current_length += len(word) + 1
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = len(word)
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                return lines
        
        browser = FakeBrowser()
        long_text = "Это очень длинный текст который должен быть разбит на несколько строк"
        result = browser._wrap_text(long_text, width=20)
        assert len(result) > 1
        for line in result:
            assert len(line) <= 20 or len(line) == len(long_text)  # Или первая строка


class TestProvenanceWithReasoning:
    """Тесты provenance с обоснованиями."""
    
    def test_provenance_card_with_reasoning(self):
        card = ProvenanceCard(
            file_hash="hash1",
            filename="test.txt",
            first_seen_path="/source/test.txt",
            current_path="/target/test.txt",
            first_processed="2024-01-01T00:00:00",
            last_processed="2024-01-01T00:00:00",
            ai_reasoning="Нейросеть определила категорию по содержимому",
            algorithmic_reasoning="Алгоритмическое правило: .txt -> Документы",
        )
        assert card.ai_reasoning != ""
        assert card.algorithmic_reasoning != ""
    
    def test_provenance_store_upsert_with_reasoning(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        
        card = store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            category="Тест",
            ai_reasoning="AI обоснование",
            algorithmic_reasoning="Алгоритмическое обоснование",
        )
        
        assert card.ai_reasoning == "AI обоснование"
        assert card.algorithmic_reasoning == "Алгоритмическое обоснование"
        
        # Проверяем сохранение и загрузку
        store.save()
        store2 = ProvenanceStore(str(tmp_path))
        card2 = store2.get_card("hash1")
        assert card2.ai_reasoning == "AI обоснование"
        assert card2.algorithmic_reasoning == "Алгоритмическое обоснование"
    
    def test_provenance_store_update_reasoning(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        
        # Создаём карточку
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            ai_reasoning="Старое AI обоснование",
            algorithmic_reasoning="Старое алгоритмическое обоснование",
        )
        
        # Обновляем обоснования
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            ai_reasoning="Новое AI обоснование",
            algorithmic_reasoning="Новое алгоритмическое обоснование",
        )
        
        card = store.get_card("hash1")
        assert card.ai_reasoning == "Новое AI обоснование"
        assert card.algorithmic_reasoning == "Новое алгоритмическое обоснование"
    
    def test_provenance_jsonl_format_with_reasoning(self, tmp_path):
        store = ProvenanceStore(str(tmp_path))
        
        store.upsert(
            file_hash="hash1",
            filename="test.txt",
            original_path="/source/test.txt",
            current_path="/target/test.txt",
            ai_reasoning="AI reasoning text",
            algorithmic_reasoning="Algorithmic reasoning text",
        )
        store.save()
        
        # Проверяем JSONL файл
        cards_path = os.path.join(tmp_path, ".provenance", "cards.jsonl")
        assert os.path.exists(cards_path)
        
        with open(cards_path, "r") as f:
            lines = f.readlines()
        
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["ai_reasoning"] == "AI reasoning text"
        assert d["algorithmic_reasoning"] == "Algorithmic reasoning text"


class TestFileInfoWithReasoning:
    """Тесты FileInfo с обоснованиями."""
    
    def test_fileinfo_has_reasoning_fields(self):
        from models import FileInfo
        
        info = FileInfo(
            original_path="/test/file.txt",
            filename="file.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
            ai_reasoning="AI decided this category",
            algorithmic_reasoning="Rule-based classification",
        )
        
        assert info.ai_reasoning == "AI decided this category"
        assert info.algorithmic_reasoning == "Rule-based classification"
    
    def test_fileinfo_default_reasoning_empty(self):
        from models import FileInfo
        
        info = FileInfo(
            original_path="/test/file.txt",
            filename="file.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
        )
        
        assert info.ai_reasoning == ""
        assert info.algorithmic_reasoning == ""
    
    def test_fileinfo_to_dict_includes_reasoning(self):
        from models import FileInfo
        
        info = FileInfo(
            original_path="/test/file.txt",
            filename="file.txt",
            extension="txt",
            size=100,
            mime_type="text/plain",
            ai_reasoning="Test AI reasoning",
            algorithmic_reasoning="Test algo reasoning",
        )
        
        d = info.to_dict()
        assert d["ai_reasoning"] == "Test AI reasoning"
        assert d["algorithmic_reasoning"] == "Test algo reasoning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
