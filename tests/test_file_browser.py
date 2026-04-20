"""Тесты для file_browser.py."""

import os
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock

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


class TestFileBrowserViewModel:
    """Тесты ViewModel файлового браузера."""
    
    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Создать тестовую директорию с файлами."""
        # Создаём структуру директорий
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir" / "file3.txt").write_text("content3")
        return str(tmp_path)
    
    @pytest.fixture
    def view_model(self, sample_dir):
        """Создать ViewModel для тестирования."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        return FileBrowserViewModel(sample_dir, provenance)
    
    def test_load_directory(self, view_model, sample_dir):
        """Тест загрузки директории."""
        view_model.load_directory()
        
        # subdir, file1.txt, file2.txt (без .. т.к. это корень для VM)
        assert len(view_model.entries) == 3
        assert view_model.entries[0].name == "subdir"
        assert view_model.entries[0].is_dir is True
        assert view_model.selected_index == 0
    
    def test_load_directory_root_no_parent(self, sample_dir):
        """Тест загрузки корневой директории (без ..)."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        
        vm.load_directory()
        
        # В корневой директории не должно быть ".."
        assert vm.entries[0].name != ".." or len(vm.entries) == 0
    
    def test_navigate_down(self, view_model):
        """Тест навигации вниз."""
        view_model.load_directory()
        initial_index = view_model.selected_index
        
        result = view_model.navigate_down()
        
        assert result is True
        assert view_model.selected_index == initial_index + 1
    
    def test_navigate_down_at_end(self, view_model):
        """Тест навигации вниз в конце списка."""
        view_model.load_directory()
        # Перемещаемся в конец
        view_model.selected_index = len(view_model.entries) - 1
        
        result = view_model.navigate_down()
        
        assert result is False
        assert view_model.selected_index == len(view_model.entries) - 1
    
    def test_navigate_up(self, view_model):
        """Тест навигации вверх."""
        view_model.load_directory()
        view_model.selected_index = 2
        
        result = view_model.navigate_up()
        
        assert result is True
        assert view_model.selected_index == 1
    
    def test_navigate_up_at_start(self, view_model):
        """Тест навигации вверх в начале списка."""
        view_model.load_directory()
        view_model.selected_index = 0
        
        result = view_model.navigate_up()
        
        assert result is False
        assert view_model.selected_index == 0
    
    def test_get_selected_entry(self, view_model):
        """Тест получения выбранного элемента."""
        view_model.load_directory()
        
        entry = view_model.get_selected_entry()
        
        assert entry is not None
        assert entry == view_model.entries[0]
    
    def test_get_selected_entry_out_of_bounds(self, view_model):
        """Тест получения элемента за пределами диапазона."""
        view_model.load_directory()
        view_model.selected_index = 999
        
        entry = view_model.get_selected_entry()
        
        assert entry is None
    
    def test_open_selected_directory(self, view_model, sample_dir):
        """Тест открытия директории."""
        view_model.load_directory()
        # Находим subdir
        for i, entry in enumerate(view_model.entries):
            if entry.name == "subdir":
                view_model.selected_index = i
                break
        
        new_path = view_model.open_selected()
        
        assert new_path is not None
        assert "subdir" in new_path
        assert view_model.current_path == new_path
        assert view_model.selected_index == 0
    
    def test_go_back(self, view_model, sample_dir):
        """Тест возврата назад."""
        view_model.load_directory()
        # Открываем поддиректорию
        for i, entry in enumerate(view_model.entries):
            if entry.name == "subdir":
                view_model.selected_index = i
                break
        view_model.open_selected()
        
        # Возвращаемся назад
        new_path = view_model.go_back()
        
        assert new_path == sample_dir
        assert view_model.current_path == sample_dir
        assert view_model.selected_index == 0
    
    def test_get_entries_for_display(self, view_model):
        """Тест получения данных для отображения."""
        view_model.load_directory()
        
        entries = view_model.get_entries_for_display()
        
        assert len(entries) == len(view_model.entries)
        # Проверяем формат кортежей
        for display_name, base_style, focus_style in entries:
            assert isinstance(display_name, str)
            assert isinstance(base_style, str)
            assert isinstance(focus_style, str)
    
    def test_get_reasoning_data_no_selection(self, view_model):
        """Тест получения данных обоснования без выбора."""
        view_model.entries = []
        
        data = view_model.get_reasoning_data()
        
        assert data.get("empty") is True
    
    def test_refresh(self, view_model):
        """Тест обновления директории."""
        view_model.load_directory()
        view_model.selected_index = 2
        
        view_model.refresh()
        
        assert view_model.selected_index == 0  # После refresh индекс сбрасывается


class TestFileBrowserView:
    """Тесты View файлового браузера."""
    
    @pytest.fixture
    def mock_vm(self):
        """Создать mock ViewModel."""
        vm = Mock()
        vm.entries = [
            Mock(name="..", is_dir=True),
            Mock(name="file1.txt", is_dir=False),
            Mock(name="file2.txt", is_dir=False),
        ]
        vm.get_entries_for_display.return_value = [
            ("📁 ..", 'directory', 'directory_focus'),
            ("📄 file1.txt", 'file', 'file_focus'),
            ("📄 file2.txt", 'file', 'file_focus'),
        ]
        vm.get_reasoning_data.return_value = {"empty": True}
        return vm
    
    def test_render_file_list(self, mock_vm):
        """Тест отрисовки списка файлов."""
        from file_browser import FileBrowserView
        
        view = FileBrowserView(mock_vm)
        view.render_file_list()
        
        # Проверяем что walker не пустой
        assert len(view.file_walker) == 3
    
    def test_render_file_list_sets_focus(self, mock_vm):
        """Тест установки фокуса при отрисовке."""
        from file_browser import FileBrowserView
        
        mock_vm.selected_index = 1
        view = FileBrowserView(mock_vm)
        view.render_file_list()
        
        # Проверяем что фокус установлен корректно
        assert view.file_walker.focus == 1
    
    def test_update_footer(self, mock_vm):
        """Тест обновления footer."""
        from file_browser import FileBrowserView
        
        view = FileBrowserView(mock_vm)
        view.update_footer()
        
        assert "Навигация" in view.footer_text.text
        assert "Выход" in view.footer_text.text


class TestFileBrowserNavigation:
    """Интеграционные тесты навигации."""
    
    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Создать тестовую директорию с несколькими файлами."""
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text(f"content{i}")
        return str(tmp_path)
    
    def test_sequential_down_navigation(self, sample_dir):
        """Тест последовательной навигации вниз."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        initial_index = vm.selected_index
        
        # Нажимаем вниз несколько раз
        for i in range(3):
            result = vm.navigate_down()
            assert result is True
            assert vm.selected_index == initial_index + i + 1
    
    def test_down_then_up_navigation(self, sample_dir):
        """Тест навигации вниз затем вверх."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Вниз
        vm.navigate_down()
        assert vm.selected_index == 1
        
        # Вверх
        vm.navigate_up()
        assert vm.selected_index == 0
    
    def test_first_down_goes_to_second_item(self, sample_dir):
        """Тест что первое нажатие вниз переходит ко второму элементу.
        
        Это регрессионный тест для бага когда при первом нажатии вниз
        фокус перескакивал на последний элемент.
        """
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        initial_count = len(vm.entries)
        assert initial_count >= 2  # Убеждаемся что есть хотя бы 2 элемента
        
        # Первое нажатие вниз
        result = vm.navigate_down()
        
        assert result is True
        assert vm.selected_index == 1  # Должен быть второй элемент (индекс 1)
        assert vm.selected_index != initial_count - 1  # Не должен быть последним


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
