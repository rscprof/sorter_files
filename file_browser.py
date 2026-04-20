#!/usr/bin/env python3
"""Консольный файловый менеджер в стиле Midnight Commander.

Позволяет просматривать отсортированные файлы с сохранением исходной иерархии,
а также видеть обоснования перемещения файлов (от AI и алгоритмического кода).
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import urwid

# Добавляем путь к модулям проекта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provenance import ProvenanceStore, ProvenanceCard


class FileEntry:
    """Элемент файловой панели."""
    
    def __init__(self, name: str, is_dir: bool, path: str, 
                 card: Optional[ProvenanceCard] = None,
                 original_path: Optional[str] = None):
        self.name = name
        self.is_dir = is_dir
        self.path = path  # Текущий путь в organized/
        self.card = card  # Provenance карточка (если есть)
        self.original_path = original_path or (card.first_seen_path if card else None)
    
    def __repr__(self):
        return f"FileEntry({self.name}, dir={self.is_dir})"


class FileBrowserViewModel:
    """ViewModel - модель представления для файлового браузера.
    
    Содержит состояние и бизнес-логику, отделённую от UI.
    """
    
    def __init__(self, target_dir: str, provenance_store: ProvenanceStore):
        self.target_dir = os.path.abspath(target_dir)
        self.provenance = provenance_store
        
        # Состояние навигации
        self.current_path = self.target_dir
        self.history: List[str] = []
        self.entries: List[FileEntry] = []
        self.selected_index = 0
    
    def load_directory(self, path: Optional[str] = None) -> None:
        """Загрузить содержимое директории."""
        if path is not None:
            self.current_path = path
        
        self.entries = []
        
        try:
            items = sorted(os.listdir(self.current_path))
        except PermissionError:
            self.entries.append(FileEntry("[Нет доступа]", False, ""))
            self.selected_index = 0
            return
        
        # Добавляем ".." если не в корне
        if self.current_path != self.target_dir:
            parent = os.path.dirname(self.current_path)
            self.entries.insert(0, FileEntry("..", True, parent))
        
        for name in items:
            full_path = os.path.join(self.current_path, name)
            is_dir = os.path.isdir(full_path)
            
            # Ищем карточку provenance
            card = self.provenance.find_by_current_path(full_path)
            
            # Если это файл из "unknown" или корневой директории без карточки,
            # пытаемся найти по original_path
            if not card and not is_dir:
                for c in self.provenance.cards.values():
                    if os.path.abspath(c.current_path) == full_path:
                        card = c
                        break
            
            self.entries.append(FileEntry(name, is_dir, full_path, card))
        
        # Сортируем: сначала директории, потом файлы
        dirs = [e for e in self.entries if e.is_dir]
        files = [e for e in self.entries if not e.is_dir]
        self.entries = sorted(dirs, key=lambda x: x.name.lower()) + \
                       sorted(files, key=lambda x: x.name.lower())
        
        self.selected_index = 0
    
    def navigate_up(self) -> bool:
        """Переместиться вверх. Возвращает True если удалось."""
        if self.selected_index > 0:
            self.selected_index -= 1
            return True
        return False
    
    def navigate_down(self) -> bool:
        """Переместиться вниз. Возвращает True если удалось."""
        if self.selected_index < len(self.entries) - 1:
            self.selected_index += 1
            return True
        return False
    
    def get_selected_entry(self) -> Optional[FileEntry]:
        """Получить выбранный элемент."""
        if not self.entries or self.selected_index >= len(self.entries):
            return None
        return self.entries[self.selected_index]
    
    def open_selected(self) -> Optional[str]:
        """Открыть выбранный элемент. Возвращает новый путь если это директория."""
        entry = self.get_selected_entry()
        if not entry:
            return None
        
        if entry.name == "..":
            return self._go_back()
        
        if entry.is_dir:
            self.history.append(self.current_path)
            self.current_path = entry.path
            self.selected_index = 0
            return self.current_path
        
        return None
    
    def go_back(self) -> Optional[str]:
        """Вернуться назад. Возвращает новый путь."""
        result = self._go_back()
        if result:
            self.selected_index = 0
        return result
    
    def _go_back(self) -> Optional[str]:
        """Внутренний метод возврата назад."""
        if self.history:
            self.current_path = self.history.pop()
            return self.current_path
        elif self.current_path != self.target_dir:
            self.current_path = os.path.dirname(self.current_path)
            return self.current_path
        return None
    
    def refresh(self) -> None:
        """Обновить текущую директорию."""
        self.load_directory()
    
    def get_entries_for_display(self) -> List[Tuple[str, str, str]]:
        """Получить данные для отображения списка файлов.
        
        Returns:
            Список кортежей (display_name, base_style, focus_style)
        """
        result = []
        for entry in self.entries:
            if entry.name == "..":
                result.append(("📁 ..", 'directory', 'directory_focus'))
            elif entry.is_dir:
                result.append((f"📁 {entry.name}/", 'directory', 'directory_focus'))
            else:
                result.append((f"📄 {entry.name}", 'file', 'file_focus'))
        return result
    
    def get_reasoning_data(self) -> Dict[str, Any]:
        """Получить данные для панели обоснований."""
        entry = self.get_selected_entry()
        if not entry:
            return {"empty": True}
        
        data = {
            "name": entry.name,
            "path": entry.path,
            "original_path": entry.original_path,
            "is_dir": entry.is_dir,
            "has_card": entry.card is not None,
        }
        
        if entry.card:
            card = entry.card
            data["category"] = card.category
            data["subcategory"] = card.subcategory
            data["description"] = card.description
            data["ai_reasoning"] = card.ai_reasoning
            data["algorithmic_reasoning"] = card.algorithmic_reasoning
            data["move_history"] = card.move_history[-5:] if card.move_history else []
        
        return data


class NavigableListBox(urwid.ListBox):
    """ListBox с кастомной обработкой клавиш.
    
    Перехватывает все навигационные клавиши и передаёт их обработчику,
    вместо того чтобы обрабатывать самостоятельно. Это предотвращает
    некорректное поведение прокрутки и позволяет полностью контролировать
    навигацию через ViewModel.
    """
    
    def __init__(self, body, keypress_handler):
        super().__init__(body)
        self.keypress_handler = keypress_handler
    
    def keypress(self, size, key: str) -> Optional[str]:
        """Перехватить нажатие клавиши и передать обработчику.
        
        Returns:
            None если клавиша обработана, иначе ключ для дальнейшей обработки.
        """
        if self.keypress_handler(key):
            return None  # Клавиша обработана
        return super().keypress(size, key)


class FileBrowserView:
    """View - визуальный слой файлового браузера."""
    
    PALETTE = [
        ('header', 'white', 'dark blue', 'bold'),
        ('footer', 'white', 'dark gray'),
        ('directory', 'yellow', 'default', 'bold'),
        ('directory_focus', 'black', 'yellow', 'bold'),
        ('file', 'light gray', 'default'),
        ('file_focus', 'black', 'light gray', 'bold'),
        ('selected', 'black', 'light gray'),
        ('reasoning_ai', 'light cyan', 'default'),
        ('reasoning_algo', 'light green', 'default'),
        ('path_info', 'dark gray', 'default'),
        ('error', 'light red', 'default'),
        ('help_key', 'light blue', 'default', 'bold'),
        ('help_text', 'light gray', 'default'),
    ]
    
    # Клавиши навигации которые нужно перехватывать
    NAVIGATION_KEYS = ('up', 'down', 'page up', 'page down', 'home', 'end', 
                       'k', 'j', 'g', 'G', 'left', 'right', 'h', 'l', 
                       'enter', 'backspace', 'esc', 'r', 'R', 'q', 'Q')
    
    def __init__(self, view_model: FileBrowserViewModel, input_handler):
        self.vm = view_model
        self.input_handler = input_handler
        
        # Виджеты
        self.header = urwid.AttrMap(
            urwid.Text("📁 File Browser - Просмотр отсортированных файлов", align='center'),
            'header'
        )
        
        self.file_walker = urwid.SimpleFocusListWalker([])
        # Отключаем обработку клавиш в ListBox - будем обрабатывать сами
        self.file_listbox = NavigableListBox(self.file_walker, self._handle_keypress)
        
        self.reasoning_walker = urwid.SimpleFocusListWalker([])
        self.reasoning_view = urwid.ListBox(self.reasoning_walker)
        
        # Основной layout
        main_columns = urwid.Columns([
            ('weight', 2, self.file_listbox),
            ('weight', 1, self.reasoning_view),
        ])
        
        self.footer_text = urwid.Text("")
        self.footer = urwid.AttrMap(self.footer_text, 'footer')
        
        self.frame = urwid.Frame(
            body=main_columns,
            header=self.header,
            footer=self.footer
        )
        
        self.main_loop: Optional[urwid.MainLoop] = None
    
    def _handle_keypress(self, key: str) -> bool:
        """Обработать нажатие клавиши.
        
        Returns:
            True если клавиша была обработана, False если нет.
        """
        if key in self.NAVIGATION_KEYS or len(key) == 1:
            try:
                self.input_handler(key)
                return True
            except urwid.ExitMainLoop:
                raise
            except Exception:
                return False
        return False
    
    def create_main_loop(self, input_handler) -> urwid.MainLoop:
        """Создать главный цикл приложения."""
        self.main_loop = urwid.MainLoop(
            self.frame,
            palette=self.PALETTE,
            unhandled_input=input_handler,
        )
        return self.main_loop
    
    def render_file_list(self) -> None:
        """Отрисовать список файлов."""
        self.file_walker.clear()
        
        for display_name, base_style, focus_style in self.vm.get_entries_for_display():
            widget = urwid.AttrMap(
                urwid.Text(display_name),
                base_style,
                focus_style
            )
            self.file_walker.append(widget)
        
        # Устанавливаем фокус корректно
        if self.vm.entries:
            try:
                focus_idx = max(0, min(self.vm.selected_index, len(self.vm.entries) - 1))
                self.file_walker.set_focus(focus_idx)
                # Важно: устанавливаем focus_position для ListBox чтобы предотвратить
                # некорректное поведение прокрутки
                self.file_listbox.focus_position = focus_idx
            except (TypeError, AttributeError):
                # Для тестов с mock объектами
                pass
    
    def render_reasoning_panel(self) -> None:
        """Отрисовать панель обоснований."""
        self.reasoning_walker.clear()
        
        data = self.vm.get_reasoning_data()
        
        if data.get("empty"):
            return
        
        widgets = []
        
        # Заголовок
        widgets.append(urwid.AttrMap(
            urwid.Text("📋 Информация о файле", align='center'),
            'header'
        ))
        widgets.append(urwid.Divider())
        
        # Имя и путь
        widgets.append(urwid.Text(('file', f"Имя: {data['name']}")))
        widgets.append(urwid.Text(('path_info', f"Путь: {data['path']}")))
        
        if data.get('original_path') and data['original_path'] != data['path']:
            widgets.append(urwid.Text(('path_info', f"Оригинал: {data['original_path']}")))
        
        widgets.append(urwid.Divider())
        
        # Provenance информация
        if data.get('has_card'):
            widgets.append(urwid.Text(('directory', "📊 Provenance:")))
            widgets.append(urwid.Text(f"  Категория: {data.get('category') or '—'}"))
            if data.get('subcategory'):
                widgets.append(urwid.Text(f"  Подкатегория: {data['subcategory']}"))
            if data.get('description'):
                widgets.append(urwid.Text(f"  Описание: {data['description']}"))
            
            widgets.append(urwid.Divider())
            
            # Обоснование от AI
            if data.get('ai_reasoning'):
                widgets.append(urwid.Text(('reasoning_ai', "🤖 Обоснование AI:")))
                for line in self._wrap_text(data['ai_reasoning'], width=40):
                    widgets.append(urwid.Text(('reasoning_ai', f"  {line}")))
                widgets.append(urwid.Divider())
            
            # Обоснование от алгоритма
            if data.get('algorithmic_reasoning'):
                widgets.append(urwid.Text(('reasoning_algo', "⚙️ Обоснование алгоритма:")))
                for line in self._wrap_text(data['algorithmic_reasoning'], width=40):
                    widgets.append(urwid.Text(('reasoning_algo', f"  {line}")))
                widgets.append(urwid.Divider())
            
            # История перемещений
            if data.get('move_history'):
                widgets.append(urwid.Text(('directory', f"📜 История ({len(data['move_history'])} перемещений):")))
                for move in data['move_history']:
                    ts = move.get('timestamp', '')[:16].replace('T', ' ')
                    reason = move.get('reason', '')
                    widgets.append(urwid.Text(
                        ('path_info', f"  {ts} [{reason}]")
                    ))
        else:
            if data.get('is_dir'):
                widgets.append(urwid.Text("📁 Директория"))
            else:
                widgets.append(urwid.Text(('error', "⚠️ Нет информации provenance")))
                widgets.append(urwid.Text(
                    ('path_info', "Файл мог быть перемещён вручную или до включения отслеживания.")
                ))
        
        self.reasoning_walker.extend(widgets)
    
    def _wrap_text(self, text: str, width: int = 40) -> List[str]:
        """Разбить текст на строки заданной ширины."""
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
    
    def update_footer(self) -> None:
        """Обновить нижнюю панель с подсказками."""
        help_text = (
            "[↑↓] Навигация  "
            "[Enter] Открыть  "
            "[Backspace] Назад  "
            "[R] Обновить  "
            "[Q] Выход"
        )
        self.footer_text.set_text(help_text)
    
    def set_focus_position(self, index: int) -> None:
        """Установить позицию фокуса в списке файлов."""
        if self.vm.entries and 0 <= index < len(self.vm.entries):
            self.file_walker.set_focus(index)
            self.file_listbox.focus_position = index


class FileBrowser:
    """Основное приложение файлового браузера.
    
    Координирует взаимодействие между ViewModel и View.
    """
    
    def __init__(self, target_dir: str):
        self.provenance = ProvenanceStore(os.path.abspath(target_dir))
        self.vm = FileBrowserViewModel(target_dir, self.provenance)
        # Передаём обработчик ввода в View для перехвата клавиш
        self.view = FileBrowserView(self.vm, self.handle_input)
        
        self.view.update_footer()
        self.vm.load_directory()
        self.view.render_file_list()
        self.view.render_reasoning_panel()
    
    def handle_input(self, key) -> None:
        """Обработка ввода пользователя."""
        if key in ('up', 'k'):
            if self.vm.navigate_up():
                self.view.render_file_list()
                self.view.render_reasoning_panel()
        
        elif key in ('down', 'j'):
            if self.vm.navigate_down():
                self.view.render_file_list()
                self.view.render_reasoning_panel()
        
        elif key in ('enter', 'right', 'l'):
            new_path = self.vm.open_selected()
            if new_path is not None:
                # Перешли в директорию
                self.vm.load_directory(new_path)
                self.view.render_file_list()
                self.view.render_reasoning_panel()
        
        elif key in ('backspace', 'left', 'h'):
            new_path = self.vm.go_back()
            if new_path is not None:
                self.vm.load_directory(new_path)
                self.view.render_file_list()
                self.view.render_reasoning_panel()
        
        elif key in ('r', 'R'):
            self.vm.refresh()
            self.view.render_file_list()
            self.view.render_reasoning_panel()
        
        elif key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()
    
    def run(self):
        """Запустить приложение."""
        main_loop = self.view.create_main_loop(self.handle_input)
        main_loop.run()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Консольный файловый менеджер в стиле MC"
    )
    parser.add_argument(
        "--target", "-t",
        default=os.environ.get('TARGET_DIR', 'organized'),
        help="Директория с отсортированными файлами (по умолчанию: organized)"
    )
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.target):
        print(f"Ошибка: директория '{args.target}' не существует")
        sys.exit(1)
    
    browser = FileBrowser(args.target)
    browser.run()


if __name__ == "__main__":
    main()
