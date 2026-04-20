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
from typing import Optional, List, Dict, Any

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


class FileBrowser:
    """Основное приложение файлового браузера."""
    
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
    
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)
        self.provenance = ProvenanceStore(self.target_dir)
        
        # Текущее состояние
        self.current_path = self.target_dir
        self.history: List[str] = []  # История навигации
        self.entries: List[FileEntry] = []
        self.selected_index = 0
        
        # Виджеты
        self.header = urwid.AttrMap(
            urwid.Text("📁 File Browser - Просмотр отсортированных файлов", align='center'),
            'header'
        )
        
        self.file_listbox = self._create_file_list()
        self.reasoning_view = self._create_reasoning_view()
        
        # Основной layout
        main_columns = urwid.Columns([
            ('weight', 2, self.file_listbox),
            ('weight', 1, self.reasoning_view),
        ])
        
        self.footer = urwid.AttrMap(
            urwid.Text(""),
            'footer'
        )
        
        frame = urwid.Frame(
            body=main_columns,
            header=self.header,
            footer=self.footer
        )
        
        self.main_loop = urwid.MainLoop(
            frame,
            palette=self.PALETTE,
            unhandled_input=self.handle_input,
        )
        
        self._load_directory()
        self._update_footer()
    
    def _create_file_list(self) -> urwid.ListBox:
        """Создать список файлов."""
        self.walker = urwid.SimpleFocusListWalker([])
        return urwid.ListBox(self.walker)
    
    def _create_reasoning_view(self) -> urwid.ListBox:
        """Создать панель обоснований."""
        self.reasoning_walker = urwid.SimpleFocusListWalker([])
        return urwid.ListBox(self.reasoning_walker)
    
    def _load_directory(self):
        """Загрузить содержимое текущей директории."""
        self.entries = []
        
        try:
            items = sorted(os.listdir(self.current_path))
        except PermissionError:
            self.entries.append(FileEntry("[Нет доступа]", False, ""))
            self._update_file_list()
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
            original_path = None
            if not card and not is_dir:
                # Ищем среди всех карточек те, у которых current_path совпадает
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
        self._update_file_list()
        self._update_reasoning()
    
    def _update_file_list(self):
        """Обновить виджет списка файлов."""
        self.walker.clear()
        
        for i, entry in enumerate(self.entries):
            if entry.name == "..":
                widget = urwid.AttrMap(
                    urwid.Text("📁 .."),
                    'directory',
                    'directory_focus'
                )
            elif entry.is_dir:
                widget = urwid.AttrMap(
                    urwid.Text(f"📁 {entry.name}/"),
                    'directory',
                    'directory_focus'
                )
            else:
                widget = urwid.AttrMap(
                    urwid.Text(f"📄 {entry.name}"),
                    'file',
                    'file_focus'
                )
            
            self.walker.append(widget)
        
        if self.entries:
            self.walker.set_focus(max(0, min(self.selected_index, len(self.entries) - 1)))
    
    def _update_reasoning(self):
        """Обновить панель обоснований для выбранного файла."""
        self.reasoning_walker.clear()
        
        if not self.entries or self.selected_index >= len(self.entries):
            return
        
        entry = self.entries[self.selected_index]
        
        widgets = []
        
        # Заголовок
        widgets.append(urwid.AttrMap(
            urwid.Text(f"📋 Информация о файле", align='center'),
            'header'
        ))
        widgets.append(urwid.Divider())
        
        # Имя и путь
        widgets.append(urwid.Text(('file', f"Имя: {entry.name}")))
        widgets.append(urwid.Text(('path_info', f"Путь: {entry.path}")))
        
        if entry.original_path and entry.original_path != entry.path:
            widgets.append(urwid.Text(('path_info', f"Оригинал: {entry.original_path}")))
        
        widgets.append(urwid.Divider())
        
        # Provenance информация
        if entry.card:
            card = entry.card
            
            widgets.append(urwid.Text(('directory', "📊 Provenance:"),))
            widgets.append(urwid.Text(f"  Категория: {card.category or '—'}"))
            if card.subcategory:
                widgets.append(urwid.Text(f"  Подкатегория: {card.subcategory}"))
            if card.description:
                widgets.append(urwid.Text(f"  Описание: {card.description}"))
            
            widgets.append(urwid.Divider())
            
            # Обоснование от AI
            if card.ai_reasoning:
                widgets.append(urwid.Text(('reasoning_ai', "🤖 Обоснование AI:")))
                # Разбиваем на строки для форматирования
                for line in self._wrap_text(card.ai_reasoning, width=40):
                    widgets.append(urwid.Text(('reasoning_ai', f"  {line}")))
                widgets.append(urwid.Divider())
            
            # Обоснование от алгоритма
            if card.algorithmic_reasoning:
                widgets.append(urwid.Text(('reasoning_algo', "⚙️ Обоснование алгоритма:")))
                for line in self._wrap_text(card.algorithmic_reasoning, width=40):
                    widgets.append(urwid.Text(('reasoning_algo', f"  {line}")))
                widgets.append(urwid.Divider())
            
            # История перемещений
            if card.move_history:
                widgets.append(urwid.Text(('directory', f"📜 История ({len(card.move_history)} перемещений):")))
                for move in card.move_history[-5:]:  # Показываем последние 5
                    ts = move.get('timestamp', '')[:16].replace('T', ' ')
                    reason = move.get('reason', '')
                    widgets.append(urwid.Text(
                        ('path_info', f"  {ts} [{reason}]")
                    ))
        else:
            if entry.is_dir:
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
    
    def _update_footer(self):
        """Обновить нижнюю панель с подсказками."""
        help_text = (
            "[↑↓] Навигация  "
            "[Enter] Открыть  "
            "[Backspace] Назад  "
            "[R] Обновить  "
            "[Q] Выход"
        )
        self.footer.original_widget.set_text(help_text)
    
    def handle_input(self, key):
        """Обработка ввода пользователя."""
        if key in ('up', 'k'):
            if self.selected_index > 0:
                self.selected_index -= 1
                self._update_file_list()
                self._update_reasoning()
        
        elif key in ('down', 'j'):
            if self.selected_index < len(self.entries) - 1:
                self.selected_index += 1
                self._update_file_list()
                self._update_reasoning()
        
        elif key in ('enter', 'right', 'l'):
            self._open_selected()
        
        elif key in ('backspace', 'left', 'h'):
            self._go_back()
        
        elif key in ('r', 'R'):
            self._load_directory()
        
        elif key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()
    
    def _open_selected(self):
        """Открыть выбранный элемент."""
        if not self.entries or self.selected_index >= len(self.entries):
            return
        
        entry = self.entries[self.selected_index]
        
        if entry.name == "..":
            self._go_back()
            return
        
        if entry.is_dir:
            self.history.append(self.current_path)
            self.current_path = entry.path
            self.selected_index = 0
            self._load_directory()
    
    def _go_back(self):
        """Вернуться назад."""
        if self.history:
            self.current_path = self.history.pop()
            self.selected_index = 0
            self._load_directory()
        elif self.current_path != self.target_dir:
            self.current_path = os.path.dirname(self.current_path)
            self.selected_index = 0
            self._load_directory()
    
    def run(self):
        """Запустить приложение."""
        self.main_loop.run()


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
