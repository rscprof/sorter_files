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
        """Тест навигации вниз - должен возвращать True только в крайней нижней позиции."""
        view_model.load_directory()
        
        # Когда не в конце списка - navigate_down должен вернуть False
        result = view_model.navigate_down()
        assert result is False
        assert view_model.selected_index == 0  # индекс не изменился
        
        # Перемещаемся в конец списка
        view_model.selected_index = len(view_model.entries) - 1
        
        # Теперь navigate_down должен вернуть True (сигнал для прокрутки)
        result = view_model.navigate_down()
        assert result is True
        assert view_model.selected_index == len(view_model.entries) - 1  # индекс не изменился
    
    def test_navigate_down_at_end(self, view_model):
        """Тест навигации вниз в конце списка."""
        view_model.load_directory()
        # Перемещаемся в конец
        view_model.selected_index = len(view_model.entries) - 1
        
        result = view_model.navigate_down()
        
        assert result is True  # В конце списка navigate_down возвращает True для прокрутки
        assert view_model.selected_index == len(view_model.entries) - 1  # индекс не изменился
    
    def test_navigate_up(self, view_model):
        """Тест навигации вверх - должен возвращать True только в крайней верхней позиции."""
        view_model.load_directory()
        
        # Когда не в начале списка - navigate_up должен вернуть False
        view_model.selected_index = 2
        result = view_model.navigate_up()
        assert result is False
        assert view_model.selected_index == 2  # индекс не изменился
        
        # Перемещаемся в начало списка
        view_model.selected_index = 0
        
        # Теперь navigate_up должен вернуть True (сигнал для прокрутки)
        result = view_model.navigate_up()
        assert result is True
        assert view_model.selected_index == 0  # индекс не изменился
    
    def test_navigate_up_at_start(self, view_model):
        """Тест навигации вверх в начале списка."""
        view_model.load_directory()
        view_model.selected_index = 0
        
        result = view_model.navigate_up()
        
        assert result is True  # В начале списка navigate_up возвращает True для прокрутки
        assert view_model.selected_index == 0  # индекс не изменился
    
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
    
    @pytest.fixture
    def mock_handler(self):
        """Создать mock обработчик ввода."""
        return Mock()
    
    def test_render_file_list(self, mock_vm, mock_handler):
        """Тест отрисовки списка файлов."""
        from file_browser import FileBrowserView
        
        view = FileBrowserView(mock_vm, mock_handler)
        view.render_file_list()
        
        # Проверяем что walker не пустой
        assert len(view.file_walker) == 3
    
    def test_render_file_list_sets_focus(self, mock_vm, mock_handler):
        """Тест установки фокуса при отрисовке."""
        from file_browser import FileBrowserView
        
        mock_vm.selected_index = 1
        view = FileBrowserView(mock_vm, mock_handler)
        view.render_file_list()
        
        # Проверяем что фокус установлен корректно
        assert view.file_walker.focus == 1
    
    def test_update_footer(self, mock_vm, mock_handler):
        """Тест обновления footer."""
        from file_browser import FileBrowserView
        
        view = FileBrowserView(mock_vm, mock_handler)
        view.update_footer()
        
        assert "Навигация" in view.footer_text.text
        assert "Выход" in view.footer_text.text


class TestNavigableListBox:
    """Тесты кастомного ListBox с перехватом клавиш."""
    
    def test_navigable_listbox_intercepts_navigation_keys(self):
        """Тест что NavigableListBox перехватывает навигационные клавиши."""
        from file_browser import NavigableListBox
        import urwid
        
        handler_called = []
        
        def mock_handler(key):
            handler_called.append(key)
            return True
        
        walker = urwid.SimpleFocusListWalker([
            urwid.Text("item1"),
            urwid.Text("item2"),
        ])
        listbox = NavigableListBox(walker, mock_handler)
        
        # Симулируем нажатие клавиши вниз
        result = listbox.keypress((10,), 'down')
        
        # Клавиша должна быть перехвачена (возвращает None)
        assert result is None
        assert 'down' in handler_called
    
    def test_navigable_listbox_calls_handler_with_up_key(self):
        """Тест что обработчик вызывается с клавишей up."""
        from file_browser import NavigableListBox
        import urwid
        
        handler_called = []
        
        def mock_handler(key):
            handler_called.append(key)
            return True
        
        walker = urwid.SimpleFocusListWalker([urwid.Text("item")])
        listbox = NavigableListBox(walker, mock_handler)
        
        listbox.keypress((10,), 'up')
        
        assert 'up' in handler_called
    
    def test_navigable_listbox_passes_through_unhandled_keys(self):
        """Тест что необработанные клавиши передаются дальше."""
        from file_browser import NavigableListBox
        import urwid
        
        def mock_handler_false(key):
            return False  # Обработчик не обработал клавишу
        
        walker = urwid.SimpleFocusListWalker([urwid.Text("item")])
        listbox = NavigableListBox(walker, mock_handler_false)
        
        # Если обработчик вернул False, ListBox должен вернуть ключ
        # Используем корректный размер (maxcol, maxrow)
        result = listbox.keypress((20, 10), 'unknown_key')
        
        # Ключ должен быть возвращён для дальнейшей обработки (urwid заменяет _ на пробел)
        assert result == 'unknown_key'
    
    def test_view_handle_keypress_calls_input_handler(self):
        """Тест что View._handle_keypress вызывает переданный обработчик."""
        from file_browser import FileBrowserView
        from unittest.mock import Mock
        
        mock_vm = Mock()
        mock_vm.entries = []
        mock_vm.get_entries_for_display.return_value = []
        mock_vm.get_reasoning_data.return_value = {"empty": True}
        
        input_handler = Mock()
        view = FileBrowserView(mock_vm, input_handler)
        
        # Вызываем внутренний обработчик
        result = view._handle_keypress('down')
        
        # Обработчик должен быть вызван
        input_handler.assert_called_once_with('down')
        assert result is True
    
    def test_view_handle_keypress_returns_false_for_unknown_keys(self):
        """Тест что неизвестные клавиши возвращают False."""
        from file_browser import FileBrowserView
        from unittest.mock import Mock
        
        mock_vm = Mock()
        mock_vm.entries = []
        mock_vm.get_entries_for_display.return_value = []
        mock_vm.get_reasoning_data.return_value = {"empty": True}
        
        input_handler = Mock(side_effect=Exception("Test error"))
        view = FileBrowserView(mock_vm, input_handler)
        
        # Если обработчик выбрасывает исключение, должно вернуться False
        result = view._handle_keypress('some_key')
        
        assert result is False
    
    def test_view_handle_keypress_propagates_exit_main_loop(self):
        """Тест что ExitMainLoop пробрасывается дальше."""
        from file_browser import FileBrowserView
        import urwid
        from unittest.mock import Mock
        
        mock_vm = Mock()
        mock_vm.entries = []
        mock_vm.get_entries_for_display.return_value = []
        mock_vm.get_reasoning_data.return_value = {"empty": True}
        
        def raise_exit(key):
            raise urwid.ExitMainLoop()
        
        view = FileBrowserView(mock_vm, raise_exit)
        
        with pytest.raises(urwid.ExitMainLoop):
            view._handle_keypress('q')


class TestViewModelNavigation:
    """Дополнительные тесты навигации ViewModel."""
    
    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Создать тестовую директорию с несколькими файлами."""
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text(f"content{i}")
        return str(tmp_path)
    
    def test_navigate_down_multiple_times(self, sample_dir):
        """Тест многократной навигации вниз - проверяем что navigate_down возвращает True только в конце."""
        from file_browser import FileBrowserViewModel
        from provenance import ProvenanceStore
        
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        initial_count = len(vm.entries)
        
        # Когда не в конце списка - navigate_down должен вернуть False
        for i in range(initial_count - 1):
            result = vm.navigate_down()
            assert result is False
            assert vm.selected_index == 0  # индекс не меняется
        
        # Перемещаемся вручную в конец
        vm.selected_index = initial_count - 1
        
        # Теперь navigate_down должен вернуть True (сигнал для прокрутки)
        result = vm.navigate_down()
        assert result is True
        assert vm.selected_index == initial_count - 1  # индекс не меняется
    
    def test_navigate_up_from_middle(self, sample_dir):
        """Тест навигации вверх из середины списка - должен вернуть False пока не в начале."""
        from file_browser import FileBrowserViewModel
        from provenance import ProvenanceStore
        
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Перемещаемся в середину
        vm.selected_index = 5
        
        # Вверх - должен вернуть False так как не в начале
        result = vm.navigate_up()
        assert result is False
        assert vm.selected_index == 5  # индекс не меняется
        
        # Перемещаемся в начало
        vm.selected_index = 0
        
        # Теперь navigate_up должен вернуть True (сигнал для прокрутки)
        result = vm.navigate_up()
        assert result is True
        assert vm.selected_index == 0  # индекс не меняется
    
    def test_boundary_conditions_navigation(self, sample_dir):
        """Тест граничных условий навигации."""
        from file_browser import FileBrowserViewModel
        from provenance import ProvenanceStore
        
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Находимся в начале - up должен вернуть True (сигнал для прокрутки)
        assert vm.navigate_up() is True
        assert vm.selected_index == 0  # индекс не меняется
        
        # Перемещаемся в конец
        vm.selected_index = len(vm.entries) - 1
        
        # down должен вернуть True (сигнал для прокрутки)
        assert vm.navigate_down() is True
        assert vm.selected_index == len(vm.entries) - 1  # индекс не меняется
    
    def test_navigation_up_changes_indices(self, sample_dir):
        """Тест что navigation_up изменяет selected_index и top_index корректно."""
        from file_browser import FileBrowserViewModel
        from provenance import ProvenanceStore
        
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Изначально оба индекса равны 0
        assert vm.selected_index == 0
        assert vm.top_index == 0
        
        # Перемещаемся в середину
        vm.selected_index = 5
        vm.top_index = 3
        
        # navigation_up должен уменьшить selected_index
        result = vm.navigation_up()
        assert result is False  # Прокрутки не было
        assert vm.selected_index == 4
        assert vm.top_index == 3  # top_index не изменился
        
        # Перемещаемся на позицию где selected_index == top_index
        vm.selected_index = 3
        
        # navigation_up должен уменьшить selected_index и top_index
        result = vm.navigation_up()
        assert result is False  # Прокрутки не было (просто перемещение выделения)
        assert vm.selected_index == 2
        assert vm.top_index == 2  # top_index подстроился под selected_index
        
        # Теперь selected_index == 0, top_index > 0 - должна быть прокрутка
        vm.selected_index = 0
        vm.top_index = 5
        
        result = vm.navigation_up()
        assert result is True  # Была прокрутка
        assert vm.selected_index == 0  # selected_index не изменился
        assert vm.top_index == 4  # top_index уменьшился
    
    def test_navigation_down_changes_indices(self, sample_dir):
        """Тест что navigation_down изменяет selected_index и top_index корректно."""
        from file_browser import FileBrowserViewModel
        from provenance import ProvenanceStore
        
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        viewport_height = 5  # Маленький viewport чтобы можно было прокручивать
        max_index = len(vm.entries) - 1
        
        # Изначально оба индекса равны 0
        assert vm.selected_index == 0
        assert vm.top_index == 0
        
        # Перемещаемся в середину
        vm.selected_index = 5
        vm.top_index = 3
        
        # navigation_down должен увеличить selected_index
        result = vm.navigation_down(viewport_height)
        assert result is False  # Прокрутки не было
        assert vm.selected_index == 6
        assert vm.top_index == 3  # top_index не изменился
        
        # Устанавливаем ситуацию где selected_index == max_index, но top_index можно увеличить
        # Для этого нужно чтобы len(entries) > viewport_height
        vm.selected_index = max_index
        vm.top_index = 0
        
        # При viewport_height=5 и len(entries)=10, max_top_index = 10-5 = 5
        # top_index=0 < 5, поэтому должна быть прокрутка
        result = vm.navigation_down(viewport_height)
        assert result is True  # Была прокрутка
        assert vm.selected_index == max_index  # selected_index не изменился
        assert vm.top_index == 1  # top_index увеличился


class TestFileBrowserNavigation:
    """Интеграционные тесты навигации."""
    
    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Создать тестовую директорию с несколькими файлами."""
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text(f"content{i}")
        return str(tmp_path)
    
    def test_sequential_down_navigation(self, sample_dir):
        """Тест последовательной навигации вниз - navigate_down возвращает True только в конце."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        initial_count = len(vm.entries)
        
        # Когда не в конце - navigate_down должен вернуть False
        for i in range(initial_count - 1):
            result = vm.navigate_down()
            assert result is False
            assert vm.selected_index == 0  # индекс не меняется
        
        # Перемещаемся вручную в конец
        vm.selected_index = initial_count - 1
        
        # Теперь navigate_down должен вернуть True (сигнал для прокрутки)
        result = vm.navigate_down()
        assert result is True
        assert vm.selected_index == initial_count - 1  # индекс не меняется
    
    def test_down_then_up_navigation(self, sample_dir):
        """Тест навигации вниз затем вверх - проверяем что индексы не меняются пока не в крайних позициях."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Вниз из позиции 0 - должен вернуть False, индекс не меняется
        result = vm.navigate_down()
        assert result is False
        assert vm.selected_index == 0
        
        # Перемещаемся в середину вручную
        vm.selected_index = 2
        
        # Вверх из середины - должен вернуть False, индекс не меняется
        result = vm.navigate_up()
        assert result is False
        assert vm.selected_index == 2
        
        # Перемещаемся в начало
        vm.selected_index = 0
        
        # Вверх из начала - должен вернуть True (сигнал для прокрутки)
        result = vm.navigate_up()
        assert result is True
        assert vm.selected_index == 0
    
    def test_first_down_goes_to_second_item(self, sample_dir):
        """Тест что первое нажатие вниз перемещает фокус на второй элемент.

        Это регрессионный тест для проверки логики: при нажатии вниз
        из позиции 0 (не в крайней нижней позиции), navigate_down должен вернуть False.
        Прокрутка вниз выполняется только когда selected_index == len(entries) - 1.
        """
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        initial_count = len(vm.entries)
        assert initial_count >= 2  # Убеждаемся что есть хотя бы 2 элемента
        
        # Первое нажатие вниз из позиции 0 - navigate_down должен вернуть False (не в крайней позиции)
        result = vm.navigate_down()
        assert result is False
        assert vm.selected_index == 0  # индекс не меняется
        
        # Перемещаемся в конец вручную
        vm.selected_index = initial_count - 1
        
        # Теперь navigate_down должен вернуть True (сигнал для прокрутки)
        result = vm.navigate_down()
        assert result is True
        assert vm.selected_index == initial_count - 1  # индекс не меняется
    
    def test_navigation_up_integration(self, sample_dir):
        """Интеграционный тест navigation_up - проверка изменения selected_index и top_index."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        # Начинаем с позиции 3
        vm.selected_index = 3
        vm.top_index = 2
        
        # navigation_up должен уменьшить selected_index
        result = vm.navigation_up()
        assert result is False
        assert vm.selected_index == 2
        assert vm.top_index == 2  # top_index подстроился
        
        # Ещё раз navigation_up
        result = vm.navigation_up()
        assert result is False
        assert vm.selected_index == 1
        assert vm.top_index == 1
        
        # Ещё раз - теперь selected_index == 0
        result = vm.navigation_up()
        assert result is False
        assert vm.selected_index == 0
        assert vm.top_index == 0
        
        # Теперь selected_index == 0 и top_index == 0 - достигнут край
        result = vm.navigation_up()
        assert result is False  # Прокрутка невозможна,已达 край
    
    def test_navigation_down_integration(self, sample_dir):
        """Интеграционный тест navigation_down - проверка изменения selected_index и top_index."""
        from file_browser import FileBrowserViewModel
        provenance = ProvenanceStore(sample_dir)
        vm = FileBrowserViewModel(sample_dir, provenance)
        vm.load_directory()
        
        viewport_height = 3  # Маленький viewport для теста
        
        # Начинаем с позиции 0
        vm.selected_index = 0
        vm.top_index = 0
        
        # navigation_down должен увеличить selected_index
        result = vm.navigation_down(viewport_height)
        assert result is False
        assert vm.selected_index == 1
        assert vm.top_index == 0
        
        # Ещё раз navigation_down
        result = vm.navigation_down(viewport_height)
        assert result is False
        assert vm.selected_index == 2
        assert vm.top_index == 0
        
        # Ещё раз - теперь selected_index переходит на 3, а top_index увеличивается до 1
        # так как selected_index (3) выходит за пределы видимости (top_index + viewport_height - 1 = 0 + 3 - 1 = 2)
        result = vm.navigation_down(viewport_height)
        assert result is False  # Не прокрутка в смысле достижения края, а просто перемещение с подстройкой top_index
        assert vm.selected_index == 3
        assert vm.top_index == 1  # top_index увеличился чтобы показать selected_index
        
        # Теперь selected_index == max_index (4 при 5 элементах), top_index можно ещё увеличить
        result = vm.navigation_down(viewport_height)
        assert result is False  # Просто перемещение с подстройкой top_index
        assert vm.selected_index == len(vm.entries) - 1  # selected_index теперь max
        assert vm.top_index == 2  # top_index увеличился
        
        # Теперь selected_index == max_index и top_index максимален - достигнут край
        result = vm.navigation_down(viewport_height)
        assert result is False  # Прокрутка невозможна,已达 край


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
