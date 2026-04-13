#!/usr/bin/env python3
"""Главный orchestrator — связывает все модули."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

import signal
import time

from config import (
    SOURCE_DIR, TARGET_DIR, DELETE_DIR, ARCHIVE_DIR,
    UNKNOWN_DIR, BUILD_ARTIFACTS_DIR, STATE_DIR,
)
from models import FileInfo, ImageMetadata, ProcessingState
from clients import LocalAIClient, SearXNGClient
from analyzer import compute_file_hash
from archives import extract_archive
from duplicates import detect_and_handle_duplicates
from relationships import group_related_files
from diagnostics import run_diagnostics
from modules import get_analyzers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("organizer.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class FileOrganizer:
    def __init__(self, source: str = SOURCE_DIR, target: str = TARGET_DIR):
        self.source = Path(source)
        self.target = Path(target)
        self.state = ProcessingState.load()
        self.localai = LocalAIClient()
        self.searxng = SearXNGClient()
        self.all_files: list[str] = []
        self.file_infos: list[FileInfo] = []
        self.errors: list[str] = []
        self.existing_categories: set[str] = set()
        self.existing_subcategories: dict[str, set[str]] = {}  # category -> {subcategories}
        self._stop_requested = False
        self._signal_count = 0
        self._last_signal_time = 0.0

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        now = time.time()
        self._signal_count += 1

        if self._signal_count >= 2 and (now - self._last_signal_time) < 2.0:
            # Второй сигнал в течение 2 секунд — немедленный выход
            logger.info("\n⚡ Повторный сигнал! Немедленное завершение...")
            self.state.save()
            import sys
            sys.exit(1)

        self._last_signal_time = now
        sig_name = "SIGINT (Ctrl-C)" if signum == signal.SIGINT else "SIGTERM (systemd stop)"
        logger.info(f"\n⚠️  Получен {sig_name}. Завершаю после текущего файла...")
        logger.info(f"     Повторите сигнал в течение 2 секунд для немедленного выхода.")
        self._stop_requested = True

    @property
    def target_inside_source(self) -> bool:
        """Target находится внутри source — нужно исключить его из обхода."""
        try:
            src = str(Path(self.source).resolve())
            tgt = str(Path(self.target).resolve())
            return tgt.startswith(src + os.sep) or tgt == src
        except Exception:
            return False

    # ── Шаг 1: Сбор ──────────────────────────────
    def collect_files(self) -> list[str]:
        files = []
        source_resolved = str(Path(self.source).resolve())
        target_resolved = str(Path(self.target).resolve()) if self.target_inside_source else None

        for root, dirs, filenames in os.walk(source_resolved, followlinks=True):
            # Исключаем target, если он внутри source
            if target_resolved:
                dirs[:] = [d for d in dirs if os.path.join(root, d) != target_resolved
                           and not os.path.join(root, d).startswith(target_resolved + os.sep)]
            for fn in filenames:
                fp = os.path.join(root, fn)
                files.append(fp)
        self.all_files = files
        logger.info(f"Найдено файлов: {len(files)}")
        return files

    def collect_files_limited(self, limit: int, dry_run: bool = False) -> list[str]:
        """Собрать файлы, остановившись при достижении лимита.
        
        Быстрее, чем collect_files + срез, потому что не обходит всё дерево.
        Также пропускает уже обработанные файлы по хешу.
        """
        files = []
        source_resolved = str(Path(self.source).resolve())
        target_resolved = str(Path(self.target).resolve()) if self.target_inside_source else None

        for root, dirs, filenames in os.walk(source_resolved, followlinks=True):
            if target_resolved:
                dirs[:] = [d for d in dirs if os.path.join(root, d) != target_resolved
                           and not os.path.join(root, d).startswith(target_resolved + os.sep)]
            for fn in filenames:
                fp = os.path.join(root, fn)
                # Пропускаем уже обработанные
                if not dry_run:
                    fh = compute_file_hash(fp)
                    if self.state.is_already_processed(fh):
                        continue
                files.append(fp)
                if len(files) >= limit:
                    self.all_files = files
                    logger.info(f"Собрано {len(files)} файлов для обработки (лимит {limit})")
                    return files

        self.all_files = files
        logger.info(f"Найдено файлов для обработки: {len(files)}")
        return files

    # ── Шаг 2: Анализ через модульную систему ──
    def analyze_file(self, filepath: str) -> FileInfo:
        """Анализ файла через систему модулей с priority order."""
        from pathlib import Path
        p = Path(filepath)
        ext = p.suffix.lower().lstrip(".")
        size = os.path.getsize(filepath)

        # Показываем тип файла сразу
        size_str = _human_size_short(size)
        logger.info(f"  │ 📂 Тип: {ext.upper()} | 📏 {size_str}")

        # Контекст для модулей
        context = {
            "localai": self.localai,
            "searxng": self.searxng,
            "categories_context": self._get_categories_context(),
        }

        # Проходим по модулям в порядке приоритета
        for analyzer_cls in get_analyzers():
            analyzer = analyzer_cls()
            if analyzer.can_handle(filepath):
                logger.info(f"  → Модуль: {analyzer.name}")
                info = analyzer.analyze(filepath, context)
                if info:
                    info.file_hash = compute_file_hash(filepath)
                    return info

        # Не должно произойти (fallback всегда срабатывает)
        from modules.fallback import FallbackAnalyzer
        fb = FallbackAnalyzer()
        return fb.analyze(filepath, context)

    # ── Шаг 3: Дубликаты ─────────────────────────
    def handle_duplicates(self):
        self.file_infos = detect_and_handle_duplicates(self.file_infos, self.state)

    # ── Шаг 4: Связанные файлы ───────────────────
    def find_relationships(self):
        groups = group_related_files(self.file_infos)
        # Записываем связи обратно в FileInfo
        for group in groups:
            if len(group) > 1:
                for fi in group:
                    fi.related_files = [
                        f.original_path for f in group if f != fi
                    ]

    # ── Шаг 5: Обработка содержимого архива ─────
    def _process_archive_contents(self, archive_info: FileInfo, dry_run: bool = False):
        """Распаковать архив и обработить каждый файл по полной цепочке."""
        p = Path(archive_info.original_path)
        extract_dir = os.path.join(ARCHIVE_DIR, p.stem)

        logger.info(f"  │ 📦 Распаковка архива...")
        if dry_run:
            logger.info(f"  │ [DRY] Распаковка -> {extract_dir}")
            return

        extracted = extract_archive(archive_info.original_path, extract_dir)
        if not extracted:
            logger.info(f"  │ ⚠️ Не удалось распаковать {archive_info.filename}")
            self.errors.append(f"Не распакован: {archive_info.filename}")
            # Перемещаем сам архив
            self._move_single_file(archive_info, dry_run=dry_run)
            return

        logger.info(f"  │ 📦 Распаковано {len(extracted)} файлов, обрабатываю...")

        # Обрабатываем каждый распакованный файл по полной цепочке
        for ef in extracted:
            fp = os.path.join(extract_dir, ef)
            if not os.path.isfile(fp):
                continue

            # Проверяем дубликаты: 1) hash-index, 2) в organized, 3) в state
            fp_hash = compute_file_hash(fp)
            if fp_hash in self._hash_index:
                dup_path = self._hash_index[fp_hash]
                logger.info(f"  │ ⏭ {Path(fp).name} — дубликат {Path(dup_path).name}")
                continue
            if self.state.is_already_processed(fp_hash):
                prev = self.state.get_processed_info(fp_hash)
                if prev and prev.get("target_path"):
                    logger.info(f"  │ ⏭ {Path(fp).name} — уже обработан")
                    continue

            try:
                logger.info(f"  │   └─ 📄 {Path(fp).name}")
                ei = self.analyze_file(fp)
                self.file_infos.append(ei)
                self._print_decision(ei, dry_run=dry_run)

                # Рекурсивно: если вложенный архив — распаковать и его
                if ei.is_archive:
                    self._process_archive_contents(ei, dry_run=dry_run)
                else:
                    self._move_single_file(ei, dry_run=dry_run)
            except Exception as e:
                logger.error(f"  │   ✗ Ошибка обработки {fp}: {e}")
                self.errors.append(str(e))

        # Перемещаем сам архив после обработки содержимого
        self._move_single_file(archive_info, dry_run=dry_run)

    # ── Шаг 6: Перемещение ───────────────────────
    def _print_decision(self, info: FileInfo, dry_run: bool = False):
        """Вывести подробное решение по файлу."""
        prefix = "  │ "
        logger.info(f"{prefix}📁 Категория: {info.ai_category or '—'}")
        if info.ai_subcategory:
            logger.info(f"{prefix}📂 Подкатегория: {info.ai_subcategory}")
        if info.ai_suggested_name:
            # Проверяем, есть ли уже расширение в имени
            name_display = info.ai_suggested_name
            if not name_display.lower().endswith(f".{info.extension.lower()}"):
                name_display = f"{name_display}.{info.extension}"
            logger.info(f"{prefix}✏️  Имя: {name_display}")
        if info.ai_description:
            logger.info(f"{prefix}💬 {info.ai_description}")
        if info.ai_reasoning:
            logger.info(f"{prefix}🤔 {info.ai_reasoning}")
        if info.is_build_artifact:
            logger.info(f"{prefix}🔨 BUILD-АРТЕФАКТ → удаление")
        if info.is_archive:
            logger.info(f"{prefix}📦 Архив → распаковка и анализ содержимого")
        if info.is_distributable or info.should_delete:
            logger.info(f"{prefix}🗑  Дистрибутив → в каталог «на_удаление»")
        if info.is_duplicate:
            action_labels = {
                "delete": "удалить (дубликат)",
                "keep": "оставить (оригинал)",
                "keep_as_project_part": "оставить (часть проекта)",
            }
            logger.info(f"{prefix}📋 Дубликат → {action_labels.get(info.duplicate_action, info.duplicate_action)}")
            if info.duplicate_of:
                logger.info(f"{prefix}    оригинал: {Path(info.duplicate_of).name}")
        if info.is_part_of_project:
            logger.info(f"{prefix}🛠  Часть проекта: {Path(info.project_root).name if info.project_root else '?'}")
        if info.related_files:
            logger.info(f"{prefix}🔗 Связанные: {len(info.related_files)} файлов")
        if info.image_metadata:
            md = info.image_metadata
            parts = []
            if md.camera_make:
                parts.append(f"{md.camera_make} {md.camera_model or ''}")
            if md.date_taken:
                parts.append(md.date_taken[:16].replace("T", " "))
            if md.latitude is not None:
                parts.append(f"GPS {md.latitude:.4f}, {md.longitude:.4f}")
            if parts:
                logger.info(f"{prefix}📷 EXIF: {', '.join(parts)}")
        if info.audio_metadata:
            md = info.audio_metadata
            parts = []
            if md.title:
                parts.append(f"«{md.title}»")
            if md.artist:
                parts.append(md.artist)
            if md.duration_seconds:
                mins = int(md.duration_seconds // 60)
                secs = int(md.duration_seconds % 60)
                parts.append(f"[{mins}:{secs:02d}]")
            if md.genre:
                parts.append(f"жанр: {md.genre}")
            if parts:
                logger.info(f"{prefix}🎵 {', '.join(parts)}")
            if info.audio_transcript:
                logger.info(f"{prefix}🎤 Транскрипт: {info.audio_transcript[:200]}")
        target = self.determine_target_path(info)
        if dry_run:
            logger.info(f"{prefix}└─ ▶ {target}")
        else:
            logger.info(f"{prefix}└─ ▶ {target}")
        print()  # пустая строка-разделитель
    def determine_target_path(self, info: FileInfo) -> str:
        """Определить куда переместить файл."""
        # Уже обработан — используем сохранённый путь
        if info.target_path:
            return info.target_path

        p = Path(info.original_path)

        # Удалить
        if info.should_delete or info.is_distributable:
            return os.path.join(DELETE_DIR, info.filename)

        # Build-артефакт
        if info.is_build_artifact:
            proj_name = Path(info.project_root).name if info.project_root else "unknown"
            return os.path.join(BUILD_ARTIFACTS_DIR, proj_name, info.filename)

        # Формируем путь из AI-категорий
        category = info.ai_category or "неразобранное"
        safe_cat = _safe_name(category)

        parts = [self.target, safe_cat]

        if info.ai_subcategory:
            parts.append(_safe_name(info.ai_subcategory))

        # Имя файла
        name = info.ai_suggested_name or p.stem
        safe_name = _safe_filename(name, info.extension)

        parts.append(safe_name)

        # Разрешаем коллизии: если файл уже существует, добавляем _номер
        target = os.path.join(*parts)
        if os.path.exists(target):
            # При reprocess — если это тот же самый файл, не переименовываем
            if os.path.abspath(target) == os.path.abspath(info.original_path):
                info.target_path = target
                return target

            # Иначе — ищем свободное имя с _номер
            stem = Path(target).stem
            ext = Path(target).suffix
            parent = Path(target).parent
            counter = 1
            while os.path.exists(target):
                target = str(parent / f"{stem}_{counter}{ext}")
                counter += 1
            logger.info(f"  │ ⚠️ Коллизия имён -> {Path(target).name}")

        info.target_path = target
        return target

    def move_files(self, dry_run: bool = False):
        moved = 0
        skipped = 0
        for info in self.file_infos:
            target = self.determine_target_path(info)

            if dry_run:
                action = "УДАЛИТЬ" if info.should_delete else "ПЕРЕМЕСТИТЬ"
                logger.info(f"[DRY] {action}: {info.filename} -> {target}")
                if info.ai_description:
                    logger.info(f"      {info.ai_description}")
                if info.is_duplicate:
                    logger.info(f"      дубликат of {info.duplicate_of} ({info.duplicate_action})")
                skipped += 1
                continue

            # Сохраняем в state
            self.state.mark_processed(info)

            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.move(info.original_path, target)
                logger.info(f"-> {target}")

                # Сохраняем в state
                self.state.moved_files[info.original_path] = target
                if info.ai_category:
                    subs = self.state.categories.setdefault(info.ai_category, set())
                    if info.ai_subcategory:
                        subs.add(info.ai_subcategory)

                moved += 1
            except Exception as e:
                logger.error(f"Ошибка перемещения {info.filename}: {e}")
                self.errors.append(str(e))
                skipped += 1

        logger.info(f"Перемещено: {moved}, пропущено: {skipped}")

    def _find_duplicate_in_organized(self, file_hash: str) -> Optional[str]:
        """Найти файл с таким же хешом в organized/ (уже организованные)."""
        if not self.target.exists():
            return None
        # Сканируем только организованные файлы (не служебные каталоги)
        for root, dirs, files in os.walk(self.target):
            rel = os.path.relpath(root, self.target)
            if rel.startswith("_"):
                dirs.clear()
                continue
            for fn in files:
                fp = os.path.join(root, fn)
                if compute_file_hash(fp) == file_hash:
                    return fp
        return None

    def _build_hash_index(self):
        """Построить индекс хешей всех уже организованных файлов."""
        self._hash_index: dict[str, str] = {}  # hash -> target_path

        # Сканируем organized/ — всегда, для актуальности
        if self.target.exists():
            logger.info(f"Сканирую organized/ для индекса дубликатов...")
            count = 0
            for root, dirs, files in os.walk(self.target):
                rel = os.path.relpath(root, self.target)
                if rel.startswith("_"):
                    dirs.clear()
                    continue
                for fn in files:
                    fp = os.path.join(root, fn)
                    h = compute_file_hash(fp)
                    if h:
                        self._hash_index[h] = fp
                        count += 1
                dirs[:] = [d for d in dirs if not d.startswith("_")]
            logger.info(f"  найдено: {count} файлов")

        logger.info(f"Индекс дубликатов: {len(self._hash_index)} файлов")

    def _scan_existing_categories(self):
        """Сканировать target-каталог и восстановить категории из существующих файлов."""
        if not self.target.exists():
            return
        for root, dirs, files in os.walk(self.target):
            # Пропускаем служебные каталоги
            rel = os.path.relpath(root, self.target)
            if rel.startswith("_"):
                dirs.clear()
                continue
            # Первый уровень — категория, второй — подкатегория
            parts = Path(rel).parts
            if len(parts) >= 1 and parts[0] and not parts[0].startswith("_"):
                cat = parts[0]
                self.existing_categories.add(cat)
                if len(parts) >= 2 and parts[1]:
                    self.existing_subcategories.setdefault(cat, set()).add(parts[1])
            dirs[:] = [d for d in dirs if not d.startswith("_")]
        if self.existing_categories:
            logger.info(f"Найдено существующих категорий: {len(self.existing_categories)}")

    def _move_single_file(self, info: FileInfo, dry_run: bool) -> bool:
        """Переместить один файл сразу после анализа."""
        target = self.determine_target_path(info)

        if dry_run:
            action = "🗑 УДАЛИТЬ" if info.should_delete else "📦 ПЕРЕМЕСТИТЬ"
            logger.info(f"  │ [DRY] {action}: {target}")
            return True

        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(info.original_path, target)

            # Сохраняем в state
            self.state.mark_processed(info)
            self.state.moved_files[info.original_path] = target
            if info.ai_category:
                subs = self.state.categories.setdefault(info.ai_category, set())
                if info.ai_subcategory:
                    subs.add(info.ai_subcategory)
            self.state.save()

            # Обновляем индекс дубликатов
            if info.file_hash:
                self._hash_index[info.file_hash] = target

            logger.info(f"  │ ✅ -> {target}")
            return True
        except Exception as e:
            logger.error(f"  │ ❌ Ошибка перемещения {info.filename}: {e}")
            self.errors.append(str(e))
            return False

    # ── Главный запуск ───────────────────────────
    def run(self, dry_run: bool = False, skip_diagnostics: bool = False, limit: int = 0):
        # ── Диагностика ──
        if not skip_diagnostics:
            diag = run_diagnostics()
            print(diag.report())
            if not diag.all_ok:
                logger.warning("Не все зависимости доступны. Продолжаю на свой страх и риск...")
                logger.warning("Или запустите: python -m diagnostics для подробностей")

        logger.info("=" * 60)
        logger.info(f"File Organizer | {'DRY-RUN' if dry_run else 'БОЕВОЙ'}")
        logger.info(f"Источник: {self.source}")
        logger.info(f"Цель:     {self.target}")
        logger.info(f"Последний запуск: {self.state.last_run or 'никогда'}")
        logger.info(f"В state обработано: {self.state.total_processed}")
        logger.info("=" * 60)

        if not dry_run:
            for d in (self.target, DELETE_DIR, ARCHIVE_DIR, UNKNOWN_DIR,
                      BUILD_ARTIFACTS_DIR, STATE_DIR):
                os.makedirs(d, exist_ok=True)

        # 1. Сбор файлов
        if not self.all_files:
            if limit > 0:
                self.collect_files_limited(limit, dry_run=dry_run)
            else:
                self.collect_files()

        # Для full scan (без limit) — дополнительная фильтрация
        if limit == 0:
            pending = [fp for fp in self.all_files
                       if dry_run or not self.state.is_already_processed(compute_file_hash(fp))]
        else:
            pending = list(self.all_files)

        logger.info(f"Всего найдено: {len(self.all_files)}, к обработке: {len(pending)}")

        # 2. Загрузка категорий из state + сканирование target
        self._load_existing_categories()
        self._scan_existing_categories()

        # 2.5. Построить индекс хешей для дубликатов
        self._hash_index: dict[str, str] = {}
        self._build_hash_index()

        # 3. Обработка каждого файла (анализ → перемещение сразу)
        logger.info("Начинаю обработку...")
        processed_count = 0
        for i, fp in enumerate(pending):
            if self._stop_requested:
                logger.info(f"⏹ Остановка по запросу. Обработано {processed_count} файлов.")
                break

            logger.info(f"  [{i+1}/{len(pending)}] 📄 {Path(fp).name}")
            try:
                # Проверка дубликата по хешу
                fp_hash = compute_file_hash(fp)
                if fp_hash in self._hash_index:
                    dup_path = self._hash_index[fp_hash]
                    logger.info(f"  │ ⏭ Дубликат {Path(dup_path).name} — пропускаю")
                    continue

                info = self.analyze_file(fp)
                self.file_infos.append(info)
                self._print_decision(info, dry_run=dry_run)

                # Если архив — распаковать и обработать содержимое
                if info.is_archive:
                    self._process_archive_contents(info, dry_run=dry_run)
                else:
                    # Перемещаем сразу после анализа
                    self._move_single_file(info, dry_run=dry_run)

                processed_count += 1

            except Exception as e:
                logger.error(f"  ✗ Ошибка: {e}")
                self.errors.append(str(e))

        # 4. Итоговая статистика
        cats = {}
        for fi in self.file_infos:
            cat = fi.ai_category or "?"
            cats[cat] = cats.get(cat, 0) + 1
        logger.info("")
        logger.info("Категории:")
        for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
            logger.info(f"  {cat}: {n}")

        self.state.save()
        if self._stop_requested:
            logger.info("⏹ Остановлено пользователем/state сохранён")
        logger.info(f"Ошибок: {len(self.errors)}")
        logger.info("Готово.")

        # Отчёт
        if not dry_run:
            self._save_report()

    def cleanup_moved_files(self, dry_run: bool = False):
        """Удалить исходные файлы, которые уже перемещены (после подтверждения пользователя)."""
        moved = self.state.moved_files
        if not moved:
            logger.info("Нет перемещённых файлов для очистки.")
            return

        # Проверяем, какие файлы ещё существуют в source
        existing = []
        for orig_path, target_path in moved.items():
            if os.path.exists(orig_path):
                exists_in_target = os.path.exists(target_path)
                existing.append((orig_path, target_path, exists_in_target))

        if not existing:
            logger.info("Все исходные файлы уже удалены.")
            return

        logger.info(f"Найдено {len(existing)} исходных файлов для удаления:")
        for orig, target, ok in existing:
            status = "✓ целевой существует" if ok else "✗ целевой ОТСУТСТВУЕТ"
            logger.info(f"  {status} — {Path(orig).name}")

        if dry_run:
            logger.info(f"[DRY-RUN] Удалил бы {len(existing)} файлов")
            return

        # Подтверждение
        answer = input(f"\nУдалить {len(existing)} исходных файлов? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "да"):
            logger.info("Отмена.")
            return

        deleted = 0
        for orig, target, ok in existing:
            if not ok:
                logger.error(f"  ПРОПУСК: {Path(orig).name} — целевой файл не найден!")
                continue
            try:
                os.remove(orig)
                deleted += 1
                logger.info(f"  Удалён: {Path(orig).name}")
            except Exception as e:
                logger.error(f"  Ошибка удаления {orig}: {e}")

        # Удаляем из state
        for orig, target, ok in existing:
            if ok:
                self.state.moved_files.pop(orig, None)
        self.state.save()
        logger.info(f"Удалено файлов: {deleted}")

    def _load_existing_categories(self):
        """Загрузить уже существующие категории из state."""
        for cat, subs in self.state.categories.items():
            self.existing_categories.add(cat)
            if subs:
                self.existing_subcategories.setdefault(cat, set()).update(subs)

    def _get_categories_context(self) -> str:
        """Сформировать контекст с существующими категориями."""
        if not self.existing_categories:
            return ""
        lines = ["\nУже существующие категории (используй их если подходят):"]
        for cat in sorted(self.existing_categories):
            subs = self.existing_subcategories.get(cat, set())
            if subs:
                lines.append(f"  - {cat}: {', '.join(sorted(subs))}")
            else:
                lines.append(f"  - {cat}")
        return "\n".join(lines)

    def _save_report(self):
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": str(self.source),
            "target": str(self.target),
            "total": len(self.file_infos),
            "errors": self.errors,
            "files": [fi.to_dict() for fi in self.file_infos],
        }
        path = os.path.join(self.target, "organizer_report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Отчёт: {path}")


# ── Утилиты ──────────────────────────────────────
def _human_size_short(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _guess_mime(filepath: str) -> str:
    mime, _ = __import__("mimetypes").guess_type(filepath)
    return mime or ""


def _safe_name(name: str) -> str:
    import re
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()[:60]
    return name or "другое"


def _safe_filename(name: str, ext: str) -> str:
    import re
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()[:100]
    # Убираем расширение если AI уже его добавил
    if name.lower().endswith(f".{ext.lower()}"):
        name = name[:-(len(ext) + 1)]
    # Также убираем если AI вернул имя с другим расширением того же типа
    for alt_ext in (ext,):
        if name.lower().endswith(f".{alt_ext.lower()}"):
            name = name[:-(len(alt_ext) + 1)]
    return f"{name or 'unnamed'}.{ext}" if ext else (name or "unnamed")


# ── CLI ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="File Organizer")
    parser.add_argument("--dry-run", action="store_true", help="Без изменений")
    parser.add_argument("--source", default=SOURCE_DIR)
    parser.add_argument("--target", default=TARGET_DIR)
    parser.add_argument("--only-duplicates", action="store_true", help="Только дубликаты")
    parser.add_argument("--reset-state", action="store_true", help="Сбросить состояние")
    parser.add_argument("--no-diagnostics", action="store_true", help="Пропустить диагностику")
    parser.add_argument("--limit", type=int, default=0, help="Ограничить кол-во файлов (0 = все)")
    parser.add_argument("--first-level-only", action="store_true", help="Только файлы из корня source")
    parser.add_argument("--single-file", type=str, default="", help="Один конкретный файл для теста")
    parser.add_argument("--debug", action="store_true", help="DEBUG: логировать промпты и ответы AI")
    parser.add_argument("--cleanup", action="store_true", help="Удалить исходные файлы после перемещения")
    parser.add_argument("--reprocess", action="store_true", help="Повторно обработать уже перемещённые файлы")
    args = parser.parse_args()

    if args.reset_state:
        state_path = os.path.join(STATE_DIR, "state.json")
        if os.path.exists(state_path):
            os.remove(state_path)
            logger.info("State сброшен")

    # DEBUG — ДО reprocess/cleanup, иначе return пропустит
    import clients
    if args.debug:
        clients.DEBUG = True

    if args.reprocess:
        # Собираем файлы из organized/ для повторной обработки
        organizer = FileOrganizer(args.source, args.target)
        organized_files = []
        exclude_exts = {".json", ".log", ".md", ".txt"}
        for root, dirs, files in os.walk(organizer.target):
            rel = os.path.relpath(root, organizer.target)
            if rel.startswith("_"):
                dirs.clear()
                continue
            for fn in files:
                if Path(fn).suffix.lower() in exclude_exts:
                    continue
                organized_files.append(os.path.join(root, fn))
            dirs[:] = [d for d in dirs if not d.startswith("_")]
        organizer.all_files = organized_files[:args.limit] if args.limit else organized_files
        logger.info(f"Reprocess: {len(organizer.all_files)} файлов из organized/")
        # Очищаем state и индекс дубликатов
        organizer.state = ProcessingState()
        organizer._hash_index = {}
        # Переопределяем _build_hash_index чтобы не сканировал organized/ при reprocess
        organizer._build_hash_index = lambda: logger.info("Индекс дубликатов: отключён (reprocess)")
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics, limit=0)
        return

    if args.cleanup:
        organizer = FileOrganizer(args.source, args.target)
        organizer.cleanup_moved_files(dry_run=args.dry_run)
        return

    organizer = FileOrganizer(args.source, args.target)

    if args.single_file:
        fp = os.path.abspath(os.path.expanduser(args.single_file))
        organizer.all_files = [fp]
        logger.info(f"Тест одного файла: {fp}")
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics)
    elif args.first_level_only:
        # Только файлы из корня source
        source_resolved = str(Path(args.source).resolve())
        files = []
        for entry in Path(source_resolved).iterdir():
            if entry.is_file() or entry.is_symlink():
                if entry.is_file():
                    files.append(str(entry))
        organizer.all_files = files[:args.limit] if args.limit else files
        logger.info(f"Файлов первого уровня: {len(organizer.all_files)}")
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics)
    else:
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics,
                      limit=args.limit)


if __name__ == "__main__":
    main()
