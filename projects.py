"""Обнаружение проектов и build-артефактов."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Optional

from config import BUILD_ARTIFACT_PATTERNS, PROJECT_INDICATORS, PROJECT_EXCLUDE_DIRS


def is_project_directory(dirpath: str) -> bool:
    """Каталог содержит indicators проекта."""
    try:
        entries = os.listdir(dirpath)
    except OSError:
        return False
    
    # Проверка на наличие src/ или подобных каталогов — признак проекта
    # Но сами по себе эти каталоги не делают директорию проектом — 
    # они должны быть в сочетании с другими индикаторами
    src_dirs = {"src", "include", "lib", "source", "sources", "app", "core"}
    has_src_dir = False
    for entry in entries:
        if entry.lower() in src_dirs and os.path.isdir(os.path.join(dirpath, entry)):
            has_src_dir = True
            break
    
    # Если есть только src-каталог без других индикаторов — это ещё не проект
    # (чтобы не считать проектом просто каталог с исходниками)
    has_other_indicator = False
    for entry in entries:
        for indicator in PROJECT_INDICATORS:
            if indicator.startswith("*"):
                if fnmatch.fnmatch(entry, indicator):
                    has_other_indicator = True
                    break
            elif indicator.endswith("/"):
                # Директорный индикатор (например, "src/")
                dir_name = indicator.rstrip("/")
                if entry.lower() == dir_name.lower() and os.path.isdir(os.path.join(dirpath, entry)):
                    has_other_indicator = True
                    break
            elif entry == indicator:
                has_other_indicator = True
                break
        if has_other_indicator:
            break
    
    # Считаем проектом если есть другие индикаторы ИЛИ (src-каталог + другие признаки)
    # Для простоты: src-каталог сам по себе достаточно для C++ проектов
    # но чтобы избежать ложных срабатываний, требуем хотя бы один файл кода
    # ВАЖНО: src-каталог внутри другой директории делает ПРОЕКТ родительскую директорию,
    # а не сам src. Поэтому проверяем что мы НЕ внутри src-каталога.
    if has_src_dir:
        code_exts = {".cpp", ".c", ".h", ".hpp", ".py", ".js", ".ts", ".java", ".go", ".rs"}
        for entry in entries:
            if any(entry.lower().endswith(ext) for ext in code_exts):
                # Проверяем что это не просто src-подкаталог без корневых файлов проекта
                # Если в директории ТОЛЬКО src и файлы кода — это вероятно подкаталог
                non_src_entries = [e for e in entries if e.lower() not in src_dirs]
                if len(non_src_entries) > 0:
                    return True
    
    return has_other_indicator


def find_project_root(filepath: str, max_depth: int = 6) -> Optional[str]:
    """Найти корень проекта, поднимаясь вверх."""
    current = Path(filepath).resolve().parent
    for _ in range(max_depth):
        # Не считаем системные/чужие каталоги проектами
        if current.name.lower() in PROJECT_EXCLUDE_DIRS:
            parent = current.parent
            if parent == current:
                break
            current = parent
            continue
        # Не уходим в корень файловой системы
        if str(current) == "/":
            break
        if is_project_directory(str(current)):
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def is_build_artifact(filepath: str, project_root: str = "") -> bool:
    """Файл — результат сборки/компиляции."""
    p = Path(filepath)
    if project_root:
        try:
            rel = str(p.relative_to(project_root)).lower()
        except ValueError:
            rel = p.name.lower()
    else:
        rel = p.name.lower()

    name_lower = p.name.lower()

    for lang, patterns in BUILD_ARTIFACT_PATTERNS.items():
        for pattern in patterns:
            if pattern.endswith("/"):
                dir_name = pattern.rstrip("/")
                if f"/{dir_name}/" in f"/{rel}" or rel.startswith(f"{dir_name}/"):
                    return True
            elif pattern.startswith("*"):
                if fnmatch.fnmatch(name_lower, pattern.lower()):
                    return True
            else:
                if pattern.lower() in rel:
                    return True

    # Общие паттерны
    for indicator in ("/build/", "/dist/", "/out/", "/bin/", "/obj/",
                       "/target/", "/.next/", "/.svelte-kit/",
                       "__pycache__", ".min.", ".bundle."):
        if indicator in rel:
            return True

    return False


def get_directory_listing(dirpath: str, max_depth: int = 2, max_entries: int = 50) -> str:
    """Получить структуру каталога в текстовом виде."""
    lines = []
    dirpath = os.path.abspath(dirpath)
    base = dirpath.rstrip("/")
    depth = base.count("/") + 1

    try:
        entries = sorted(os.listdir(dirpath))
    except OSError:
        return f"[недоступно: {dirpath}]"

    for entry in entries[:max_entries]:
        full = os.path.join(dirpath, entry)
        rel = os.path.relpath(full, base)
        if os.path.isdir(full):
            lines.append(f"📁 {rel}/")
            # Подкаталоги первого уровня
            if rel.count("/") < max_depth - 1:
                try:
                    sub = sorted(os.listdir(full))[:20]
                    for s in sub:
                        sf = os.path.join(full, s)
                        sub_rel = os.path.relpath(sf, base)
                        if os.path.isdir(sf):
                            lines.append(f"  📁 {sub_rel}/")
                        else:
                            sz = os.path.getsize(sf)
                            lines.append(f"  📄 {sub_rel} ({_human_size(sz)})")
                except OSError:
                    pass
        else:
            sz = os.path.getsize(full)
            lines.append(f"📄 {rel} ({_human_size(sz)})")

    if len(entries) > max_entries:
        lines.append(f"... и ещё {len(entries) - max_entries} записей")

    return "\n".join(lines)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"
