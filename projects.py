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
    
    # Имена каталогов-контейнеров (src, include и т.д.) — это индикаторы проекта
    # только когда они находятся ВНУТРИ директории, а не когда сама директория так называется
    container_dirs = {"src", "include", "lib", "source", "sources", "app", "core"}
    
    # Проверка на наличие индикаторов проекта (файлы конфигурации, .git и т.д.)
    has_indicator = False
    for entry in entries:
        for indicator in PROJECT_INDICATORS:
            if indicator.startswith("*"):
                if fnmatch.fnmatch(entry, indicator):
                    has_indicator = True
                    break
            elif indicator.endswith("/"):
                # Директорный индикатор (например, "src/")
                dir_name = indicator.rstrip("/")
                # Пропускаем контейнерные директории - они не делают текущую папку проектом
                if dir_name.lower() in container_dirs:
                    continue
                if entry.lower() == dir_name.lower() and os.path.isdir(os.path.join(dirpath, entry)):
                    has_indicator = True
                    break
            elif entry == indicator:
                # Пропускаем файлы main.* если это единственный файл в директории-контейнере
                # (чтобы src/main.py не считался проектом сам по себе)
                if entry.lower().startswith("main.") and len(entries) == 1:
                    continue
                has_indicator = True
                break
        if has_indicator:
            break
    
    return has_indicator


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
                if f"/{dir_name}/" in f"/{rel}" or rel.startswith(f"{dir_name}/") or f"/.{dir_name}/" in f"/{rel}":
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
    
    # Проверка скрытых директорий IDE и build-систем в начале пути
    if rel.startswith(".gradle/") or rel.startswith(".idea/"):
        return True

    return False


def is_mobile_project(filepath: str) -> bool:
    """Проверить, является ли файл частью Android/Java/Kotlin проекта."""
    p = Path(filepath)
    mobile_indicators = {
        "AndroidManifest.xml", "build.gradle", "build.gradle.kts",
        "settings.gradle", "settings.gradle.kts", "gradle.properties",
        "pom.xml", "AppModule.iml",
    }
    idea_indicators = {".idea", "*.iml"}
    try:
        project = find_project_root(filepath, max_depth=4)
        if project:
            proj_path = Path(project)
            for f in proj_path.iterdir():
                if f.name in mobile_indicators:
                    return True
                for ind in idea_indicators:
                    if ind.startswith("*") and f.name.endswith(ind.lstrip("*")):
                        return True
                    elif f.name == ind:
                        return True
    except Exception:
        pass
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
