#!/usr/bin/env python3
"""Консольный файловый менеджер в стиле Midnight Commander.

Исправлено: плавная построчная прокрутка у краёв экрана, 
стабильная высота строк, корректное сохранение позиции скролла.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import urwid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from provenance import ProvenanceStore, ProvenanceCard
except ImportError:
    class ProvenanceStore:
        def __init__(self, path): self.cards = {}
        def find_by_current_path(self, path): return None
    class ProvenanceCard: pass


class FileEntry:
    def __init__(self, name: str, is_dir: bool, path: str, 
                 card: Optional[ProvenanceCard] = None,
                 original_path: Optional[str] = None):
        self.name = name
        self.is_dir = is_dir
        self.path = os.path.abspath(path)
        self.card = card
        self.original_path = original_path or (getattr(card, 'first_seen_path', None) if card else None)
    
    def __repr__(self):
        return f"FileEntry({self.name!r}, dir={self.is_dir})"


class FileBrowserViewModel:
    def __init__(self, target_dir: str, provenance_store: ProvenanceStore):
        self.target_dir = os.path.abspath(target_dir)
        self.provenance = provenance_store
        self.current_path = self.target_dir
        self.history: List[str] = []
        self.entries: List[FileEntry] = []
        self.selected_index = 0
        self.top_index = 0
    
    def load_directory(self, path: Optional[str] = None) -> None:
        if path is not None:
            self.current_path = os.path.normpath(os.path.abspath(path))
            
        self.entries = []
        try:
            items = os.listdir(self.current_path)
        except OSError:
            self.entries.append(FileEntry("[Нет доступа]", False, ""))
            self.selected_index = 0
            return
        
        items.sort(key=lambda x: x.lower())
        
        if self.current_path != self.target_dir:
            self.entries.append(FileEntry("..", True, os.path.dirname(self.current_path)))
        
        for name in items:
            full_path = os.path.join(self.current_path, name)
            is_dir = os.path.isdir(full_path)
            card = self.provenance.find_by_current_path(full_path)
            self.entries.append(FileEntry(name, is_dir, full_path, card))
        
        # Сортировка: ".." всегда сверху, затем директории, затем файлы
        if self.entries and self.entries[0].name == "..":
            parent = self.entries.pop(0)
            dirs = sorted([e for e in self.entries if e.is_dir], key=lambda x: x.name.lower())
            files = sorted([e for e in self.entries if not e.is_dir], key=lambda x: x.name.lower())
            self.entries = [parent] + dirs + files
        else:
            dirs = sorted([e for e in self.entries if e.is_dir], key=lambda x: x.name.lower())
            files = sorted([e for e in self.entries if not e.is_dir], key=lambda x: x.name.lower())
            self.entries = dirs + files
            
        self.selected_index = 0
    
    def move_up(self) -> bool:
        if self.selected_index > 0:
            self.selected_index -= 1
            return True
        return False
    
    def navigate_up(self, viewport_height: int = 10) -> bool:
        """Навигация вверх с поддержкой прокрутки.
        
        Возвращает True если была прокрутка (достигнут край), False иначе.
        """
        if self.selected_index > 0:
            self.selected_index -= 1
            # Если selected_index ушёл за верхнюю границу видимости
            if self.selected_index < self.top_index:
                self.top_index = self.selected_index
            return False
        # Достигли верха - сигнал для прокрутки
        if self.top_index > 0:
            self.top_index -= 1
            return True
        return False
    
    def move_down(self) -> bool:
        if self.entries and self.selected_index < len(self.entries) - 1:
            self.selected_index += 1
            return True
        return False
    
    def navigate_down(self, viewport_height: int = 10) -> bool:
        """Навигация вниз с поддержкой прокрутки.
        
        Возвращает True если была прокрутка (достигнут край), False иначе.
        """
        if not self.entries:
            return False
        
        max_index = len(self.entries) - 1
        if self.selected_index < max_index:
            self.selected_index += 1
            # Если selected_index ушёл за нижнюю границу видимости
            if self.selected_index >= self.top_index + viewport_height:
                self.top_index = self.selected_index - viewport_height + 1
            return False
        # Достигли низа - проверяем возможность прокрутки
        # Прокрутка возможна только если список больше viewport
        if len(self.entries) > viewport_height and self.top_index < len(self.entries) - viewport_height:
            self.top_index += 1
            return True
        return False
    
    def get_selected_entry(self) -> Optional[FileEntry]:
        if not self.entries or self.selected_index >= len(self.entries):
            return None
        return self.entries[self.selected_index]
    
    def open_selected(self) -> Optional[str]:
        entry = self.get_selected_entry()
        if not entry: return None
        if entry.name == "..": return self._go_back()
        if entry.is_dir:
            self.history.append(self.current_path)
            self.current_path = entry.path
            return self.current_path
        return None
    
    def go_back(self) -> Optional[str]:
        return self._go_back()
    
    def _go_back(self) -> Optional[str]:
        if self.history:
            self.current_path = self.history.pop()
            return self.current_path
        elif self.current_path != self.target_dir:
            self.current_path = os.path.dirname(self.current_path)
            return self.current_path
        return None
    
    def refresh(self) -> None:
        self.load_directory()
    
    def get_entries_for_display(self) -> List[Tuple[str, str, str]]:
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
        entry = self.get_selected_entry()
        if not entry: return {"empty": True}
        data = {
            "name": entry.name, "path": entry.path,
            "original_path": entry.original_path,
            "is_dir": entry.is_dir, "has_card": entry.card is not None,
        }
        if entry.card:
            card = entry.card
            data.update({
                "category": getattr(card, "category", None),
                "subcategory": getattr(card, "subcategory", None),
                "description": getattr(card, "description", None),
                "ai_reasoning": getattr(card, "ai_reasoning", None),
                "algorithmic_reasoning": getattr(card, "algorithmic_reasoning", None),
                "move_history": (getattr(card, "move_history", []) or [])[-5:]
            })
        return data


class NavigableListBox(urwid.ListBox):
    def __init__(self, body, keypress_handler):
        super().__init__(body)
        self.keypress_handler = keypress_handler
    
    def keypress(self, size, key: str) -> Optional[str]:
        if self.keypress_handler(key):
            return None
        return super().keypress(size, key)


class FileBrowserView:
    PALETTE = [
        ('header', 'white', 'dark blue', 'bold'),
        ('footer', 'white', 'dark gray'),
        ('directory', 'yellow', 'default', 'bold'),
        ('directory_focus', 'black', 'yellow', 'bold'),
        ('file', 'light gray', 'default'),
        ('file_focus', 'black', 'light gray', 'bold'),
        ('reasoning_ai', 'light cyan', 'default'),
        ('reasoning_algo', 'light green', 'default'),
        ('path_info', 'dark gray', 'default'),
        ('error', 'light red', 'default'),
    ]
    
    def __init__(self, view_model: FileBrowserViewModel, input_handler):
        self.vm = view_model
        self.input_handler = input_handler
        self.viewport_height = 0
        
        self.header = urwid.AttrMap(
            urwid.Text("📁 File Browser - Просмотр отсортированных файлов", align='center'),
            'header'
        )
        
        self.file_walker = urwid.SimpleListWalker([])
        self.file_listbox = NavigableListBox(self.file_walker, self._handle_keypress)
        
        self.reasoning_walker = urwid.SimpleListWalker([])
        self.reasoning_view = urwid.ListBox(self.reasoning_walker)
        
        self.footer_text = urwid.Text("")
        self.footer = urwid.AttrMap(self.footer_text, 'footer')
        
        self.frame = urwid.Frame(
            body=urwid.Columns([('weight', 2, self.file_listbox), ('weight', 1, self.reasoning_view)]),
            header=self.header,
            footer=self.footer
        )
        
        self.main_loop: Optional[urwid.MainLoop] = None
    
    def _handle_keypress(self, key: str) -> bool:
        try:
            self.input_handler(key)
            return True
        except urwid.ExitMainLoop:
            raise
        except Exception:
            return False
    
    def create_main_loop(self) -> urwid.MainLoop:
        self.main_loop = urwid.MainLoop(
            self.frame,
            palette=self.PALETTE,
            unhandled_input=self.input_handler,
        )
        self._update_viewport_height()
        return self.main_loop
    
    def _update_viewport_height(self) -> None:
        if self.main_loop and hasattr(self.main_loop.screen, 'get_cols_lines'):
            try:
                _, height = self.main_loop.screen.get_cols_lines()
                # Header (1) + Footer (1) + разделители/отступы (~2)
                self.viewport_height = max(1, height - 4)
            except Exception:
                self.viewport_height = getattr(self, 'viewport_height', 20)
    
    def render_file_list(self) -> None:
        self._update_viewport_height()
        self.file_walker.clear()
        
        entries_data = self.vm.get_entries_for_display()
        
        # Определяем диапазон видимых элементов
        viewport = self.viewport_height if self.viewport_height > 0 else 20
        start_idx = self.vm.top_index
        end_idx = min(start_idx + viewport, len(entries_data))
        
        # Добавляем placeholder'ы до видимой области
        for i in range(start_idx):
            widget = urwid.AttrMap(
                urwid.Text("", wrap='clip'),
                'file',
                'file_focus'
            )
            self.file_walker.append(widget)
        
        # Добавляем видимые элементы
        for i in range(start_idx, end_idx):
            display_name, base_style, focus_style = entries_data[i]
            widget = urwid.AttrMap(
                urwid.Text(display_name, wrap='clip'),
                base_style,
                focus_style
            )
            self.file_walker.append(widget)
        
        # Добавляем placeholder'ы после видимой области
        for i in range(end_idx, len(entries_data)):
            widget = urwid.AttrMap(
                urwid.Text("", wrap='clip'),
                'file',
                'file_focus'
            )
            self.file_walker.append(widget)
        
        if not self.vm.entries:
            return
        
        idx = max(0, min(self.vm.selected_index, len(self.vm.entries) - 1))
        self.file_listbox.focus_position = idx
        self.file_listbox.offset_rows = 0
    
    @property
    def viewport_height(self) -> int:
        """Возвращает высоту области просмотра."""
        return self._viewport_height if hasattr(self, '_viewport_height') and self._viewport_height > 0 else 20
    
    @viewport_height.setter
    def viewport_height(self, value: int) -> None:
        """Устанавливает высоту области просмотра."""
        self._viewport_height = value
    
    def render_reasoning_panel(self) -> None:
        self.reasoning_walker.clear()
        data = self.vm.get_reasoning_data()
        if data.get("empty"): return
        
        widgets = [
            urwid.AttrMap(urwid.Text("📋 Информация о файле", align='center'), 'header'),
            urwid.Divider(),
            urwid.Text(('file', f"Имя: {data['name']}")),
            urwid.Text(('path_info', f"Путь: {data['path']}")),
        ]
        if data.get('original_path') and data['original_path'] != data['path']:
            widgets.append(urwid.Text(('path_info', f"Оригинал: {data['original_path']}")))
        widgets.append(urwid.Divider())
        
        if data.get('has_card'):
            widgets.append(urwid.Text(('directory', "📊 Provenance:")))
            widgets.append(urwid.Text(f"  Категория: {data.get('category') or '—'}"))
            if data.get('subcategory'):
                widgets.append(urwid.Text(f"  Подкатегория: {data['subcategory']}"))
            if data.get('description'):
                widgets.append(urwid.Text(f"  Описание: {data['description']}"))
            widgets.append(urwid.Divider())
            
            for label, style, content in [
                ("🤖 Обоснование AI:", 'reasoning_ai', data.get('ai_reasoning')),
                ("⚙️ Обоснование алгоритма:", 'reasoning_algo', data.get('algorithmic_reasoning'))
            ]:
                if content:
                    widgets.append(urwid.Text((style, label)))
                    for line in self._wrap_text(content, width=40):
                        widgets.append(urwid.Text((style, f"  {line}")))
                    widgets.append(urwid.Divider())
            
            if data.get('move_history'):
                widgets.append(urwid.Text(('directory', f"📜 История ({len(data['move_history'])} перемещений):")))
                for move in data['move_history']:
                    ts = move.get('timestamp', '')[:16].replace('T', ' ')
                    reason = move.get('reason', '')
                    widgets.append(urwid.Text(('path_info', f"  {ts} [{reason}]")))
        else:
            if data.get('is_dir'):
                widgets.append(urwid.Text("📁 Директория"))
            else:
                widgets.extend([
                    urwid.Text(('error', "⚠️ Нет информации provenance")),
                    urwid.Text(('path_info', "Файл мог быть перемещён вручную или до включения отслеживания."))
                ])
        
        self.reasoning_walker.extend(widgets)
    
    @staticmethod
    def _wrap_text(text: str, width: int = 40) -> List[str]:
        words, lines, current, current_len = text.split(), [], [], 0
        for word in words:
            if current_len + len(word) + 1 <= width:
                current.append(word); current_len += len(word) + 1
            else:
                if current: lines.append(' '.join(current))
                current = [word]; current_len = len(word)
        if current: lines.append(' '.join(current))
        return lines
    
    def update_footer(self) -> None:
        self.footer_text.set_text(
            "[↑↓/jk] Навигация  [Enter/l] Открыть  [Backspace/h] Назад  [R] Обновить  [Q/Esc] Выход"
        )


class FileBrowser:
    def __init__(self, target_dir: str):
        self.provenance = ProvenanceStore(os.path.abspath(target_dir))
        self.vm = FileBrowserViewModel(target_dir, self.provenance)
        self.view = FileBrowserView(self.vm, self.handle_input)
        
        self.view.update_footer()
        self.vm.load_directory()
        self.view.render_file_list()
        self.view.render_reasoning_panel()
    
    def handle_input(self, key) -> None:
        updated = False
        if key in ('up', 'k'):
            updated = self.vm.move_up()
        elif key in ('down', 'j'):
            updated = self.vm.move_down()
        elif key in ('enter', 'right', 'l'):
            new_path = self.vm.open_selected()
            if new_path is not None:
                self.vm.load_directory(new_path)
                updated = True
        elif key in ('backspace', 'left', 'h'):
            new_path = self.vm.go_back()
            if new_path is not None:
                self.vm.load_directory(new_path)
                updated = True
        elif key in ('r', 'R'):
            self.vm.refresh()
            updated = True
        elif key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()
        
        if updated:
            self.view.render_file_list()
            self.view.render_reasoning_panel()
    
    def run(self):
        self.view.create_main_loop().run()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Консольный файловый менеджер в стиле MC")
    parser.add_argument("--target", "-t", default=os.environ.get('TARGET_DIR', 'organized'),
                        help="Директория с отсортированными файлами")
    args = parser.parse_args()
    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print(f"Ошибка: директория '{args.target}' не существует", file=sys.stderr)
        sys.exit(1)
    FileBrowser(target).run()

if __name__ == "__main__":
    main()