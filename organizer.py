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
import sys
import time

from config import (
    SOURCE_DIR, TARGET_DIR, DELETE_DIR, ARCHIVE_DIR,
    UNKNOWN_DIR, BUILD_ARTIFACTS_DIR, STATE_DIR,
)
from models import FileInfo, ImageMetadata, ProcessingState
from clients import LocalAIClient, SearXNGClient
from analyzer import compute_file_hash, is_temp_file
from archives import extract_archive
from duplicates import detect_and_handle_duplicates
from relationships import group_related_files
from diagnostics import run_diagnostics
from modules import get_analyzers
from projects import find_project_root, is_build_artifact, is_project_directory, get_directory_listing
from provenance import ProvenanceStore

# ── Логирование (настраивается в main()) ──────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def _setup_logging(cumulative_log: bool = False, debug: bool = False):
    """Настроить логирование.
    
    cumulative_log=False (по умолчанию): отдельный файл на запуск
    cumulative_log=True: один общий organizer.log
    """
    if cumulative_log:
        log_file = os.path.join(LOG_DIR, "organizer.log")
    else:
        run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, f"organizer_{run_id}.log")

    # Убираем старые хендлеры (для повторных вызовов)
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return log_file

logger = logging.getLogger(__name__)


class FileOrganizer:
    def __init__(self, source: str = SOURCE_DIR, target: str = TARGET_DIR):
        self.source = Path(source)
        self.target = Path(target)
        self.state = ProcessingState.load()
        self.provenance = ProvenanceStore(str(self.target))
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

        # Статистика по типам файлов
        self.stats: dict[str, dict[str, int]] = {}

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _record_stats(self, ext: str, status: str):
        """Записать статистику обработки файла.
        
        status: 'ok', 'error', 'skipped'
        """
        ext_upper = ext.upper() if ext else "NO_EXT"
        if ext_upper not in self.stats:
            self.stats[ext_upper] = {"ok": 0, "error": 0, "skipped": 0}
        if status in self.stats[ext_upper]:
            self.stats[ext_upper][status] += 1

    def _print_stats(self):
        """Вывести статистику по типам файлов."""
        if not self.stats:
            return

        lines = ["", "═" * 70, "Статистика по типам файлов", "═" * 70]
        lines.append(f"  {'Тип':<12} {'✓ OK':>6} {'✗ Error':>8} {'⏭ Skip':>7} {'Всего':>7}")
        lines.append(f"  {'─' * 10} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 7}")

        total_ok = total_err = total_skip = 0
        unknown_exts = []
        
        for ext, counts in sorted(self.stats.items(), key=lambda x: -(x[1]["ok"] + x[1]["error"])):
            ok = counts["ok"]
            err = counts["error"]
            skip = counts["skipped"]
            total = ok + err + skip
            total_ok += ok
            total_err += err
            total_skip += skip
            
            # Собираем неизвестные форматы
            if ok == 0 and err == 0 and skip == 0:
                unknown_exts.append(ext)
            
            lines.append(f"  {ext:<12} {ok:>6} {err:>8} {skip:>7} {total:>7}")

        grand_total = total_ok + total_err + total_skip
        lines.append(f"  {'─' * 10} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 7}")
        lines.append(f"  {'Итого':<12} {total_ok:>6} {total_err:>8} {total_skip:>7} {grand_total:>7}")

        # Процент успеха (без учета skipped)
        if grand_total > 0:
            pct = total_ok / (total_ok + total_err) * 100 if (total_ok + total_err) > 0 else 0
            lines.append(f"  Успех: {pct:.0f}%")
        
        # Неизвестные форматы
        if unknown_exts:
            lines.append(f"  Неизвестные форматы: {', '.join(unknown_exts)}")
        
        lines.append("═" * 70)

        for line in lines:
            logger.info(line)

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
                if is_temp_file(fp):
                    continue
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
                # Пропускаем временные/мусорные файлы
                if is_temp_file(fp):
                    continue
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
    def _process_archive_contents(self, archive_info: FileInfo, dry_run: bool = False,
                                   depth: int = 1):
        """Распаковать архив и обработить каждый файл по полной цепочке.
        
        depth — уровень вложенности (1 = первый архив, 2 = вложенный и т.д.)
        
        Если архив является публичным дистрибутивом (is_distributable=True),
        он не распаковывается, а сразу перемещается в папку на удаление.
        """
        indent = "  │   " * depth
        
        # Проверяем, не является ли архив публичным дистрибутивом
        if archive_info.is_distributable or archive_info.should_delete:
            logger.info(f"{indent}🗑  Публичный дистрибутив → без распаковки")
            self._move_single_file(archive_info, dry_run=dry_run)
            return
        
        p = Path(archive_info.original_path)
        extract_dir = os.path.join(ARCHIVE_DIR, p.stem)

        logger.info(f"{indent}📦 Распаковка архива...")
        if dry_run:
            logger.info(f"{indent}[DRY] Распаковка -> {extract_dir}")
            return

        extracted = extract_archive(archive_info.original_path, extract_dir)
        if not extracted:
            logger.info(f"{indent}⚠️ Не удалось распаковать {archive_info.filename}")
            self.errors.append(f"Не распакован: {archive_info.filename}")
            self._move_single_file(archive_info, dry_run=dry_run)
            return

        logger.info(f"{indent}📦 Распаковано {len(extracted)} файлов, обрабатываю...")

        # Фильтруем и сортируем файлы
        files_to_process = []
        for ef in extracted:
            fp = os.path.join(extract_dir, ef)
            if not os.path.isfile(fp):
                continue
            fp_ext = Path(fp).suffix.lstrip(".")
            # Пропускаем временные файлы
            if is_temp_file(fp):
                logger.info(f"{indent}  🗑️ Временный файл: {Path(fp).name}")
                self._record_stats(fp_ext, "skipped")
                continue
            files_to_process.append(fp)

        for fp in files_to_process:
            fp_ext = Path(fp).suffix.lstrip(".")
            # Проверяем дубликаты
            fp_hash = compute_file_hash(fp)
            if fp_hash in self._hash_index:
                dup_path = self._hash_index[fp_hash]
                logger.info(f"{indent}  ⏭ {Path(fp).name} — дубликат {Path(dup_path).name}")
                self._record_stats(fp_ext, "skipped")
                continue
            if self.state.is_already_processed(fp_hash):
                prev = self.state.get_processed_info(fp_hash)
                if prev and prev.get("target_path"):
                    logger.info(f"{indent}  ⏭ {Path(fp).name} — уже обработан")
                    self._record_stats(fp_ext, "skipped")
                    continue

            try:
                logger.info(f"{indent}  └─ 📄 {Path(fp).name}")
                ei = self.analyze_file(fp)

                # Проверка: LocalAI перестал отвечать
                if self.localai.is_fatal() and not dry_run:
                    logger.error(f"\n❌ {self.localai.fatal_message()}")
                    self._record_stats(fp_ext, "error")
                    self._stop_requested = True
                    return

                self.file_infos.append(ei)
                self._print_decision(ei, dry_run=dry_run)

                # Рекурсивно: если вложенный архив — распаковать и его
                if ei.is_archive:
                    self._process_archive_contents(ei, dry_run=dry_run, depth=depth + 1)
                else:
                    self._move_single_file(ei, dry_run=dry_run,
                                           archive_source=archive_info.original_path,
                                           archive_extract_dir=extract_dir)

                self._record_stats(fp_ext, "ok")
            except Exception as e:
                logger.error(f"{indent}  ✗ Ошибка обработки {fp}: {e}")
                self.errors.append(str(e))
                self._record_stats(fp_ext, "error")

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

    def _analyze_directories(self, dry_run: bool = False):
        """Найти каталоги в source и проанализировать их как проекты."""
        source_resolved = str(Path(self.source).resolve())
        target_resolved = str(Path(self.target).resolve()) if self.target_inside_source else None

        # Собираем каталоги первого уровня
        dirs_to_analyze = []
        try:
            for entry in Path(source_resolved).iterdir():
                if entry.is_dir(follow_symlinks=True):
                    # Исключаем target
                    if target_resolved and str(entry.resolve()).startswith(target_resolved):
                        continue
                    # Исключаем скрытые
                    if entry.name.startswith("_"):
                        continue
                    dirs_to_analyze.append(str(entry))
        except Exception as e:
            logger.debug(f"Error scanning dirs: {e}")

        if not dirs_to_analyze:
            return

        logger.info(f"Анализ {len(dirs_to_analyze)} каталогов на наличие проектов...")

        for dirpath in dirs_to_analyze:
            # Проверяем есть ли уже обработанные файлы из этого каталога
            has_processed = False
            for h, info in self.state.processed_files.items():
                orig = info.get("original_path", "")
                if orig.startswith(dirpath + os.sep):
                    has_processed = True
                    break
            if has_processed:
                logger.info(f"  ⏭ {Path(dirpath).name} — уже обработан")
                continue

            # Проверяем есть ли indicators проекта
            if is_project_directory(dirpath):
                logger.info(f"  📁 {Path(dirpath).name} — найден проект")
                self._analyze_and_handle_directory(dirpath, dry_run=dry_run)
            else:
                logger.debug(f"  📁 {Path(dirpath).name} — не похоже на проект")

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

    def _analyze_and_handle_directory(self, dirpath: str, dry_run: bool = False) -> list[FileInfo]:
        """
        Проанализировать каталог через AI и обработать как проект.
        
        Возвращает список FileInfo для файлов которые надо обработать отдельно.
        """
        from pathlib import Path
        p = Path(dirpath)
        results = []

        # Получаем структуру каталога
        listing = get_directory_listing(dirpath, max_depth=2, max_entries=60)
        logger.info(f"  📂 Структура каталога:")
        for line in listing.split("\n")[:15]:
            logger.info(f"  │   {line}")
        if len(listing.split("\n")) > 15:
            logger.info(f"  │   ... и ещё {len(listing.split(chr(10))) - 15} строк")

        # Анализируем через AI
        analysis = self.localai.analyze_directory(listing, str(dirpath))
        if not analysis:
            logger.info(f"  ⚠ AI не смог проанализировать каталог")
            return results

        is_project = analysis.get("is_project", False)
        project_name = analysis.get("project_name", p.name)
        project_type = analysis.get("project_type", "")
        files_to_delete = analysis.get("files_to_delete", [])
        reasoning = analysis.get("reasoning", "")

        logger.info(f"  🤖 AI: проект={is_project}, тип={project_type}, имя={project_name}")
        logger.info(f"  🗑  На удаление: {files_to_delete}")
        logger.info(f"  💬 {reasoning}")

        if not is_project:
            logger.info(f"  │ Не проект — обрабатываю файлы внутри по одному")
            return results  # Файлы обработаются отдельно

        # Это проект — копируем как целое
        safe_name = _safe_name(project_name or p.name)
        project_target = os.path.join(self.target, "Проекты", safe_name)

        if dry_run:
            logger.info(f"  │ [DRY] Копирование проекта -> {project_target}")
            return results

        # Создаём целевой каталог
        os.makedirs(project_target, exist_ok=True)

        # Копируем файлы, исключая build-артефакты и служебные директории
        import shutil as sh
        copied = 0
        deleted = 0
        
        # Стандартные директории и файлы которые не копируем (build-артефакты, IDE кэш)
        exclude_dirs = {".gradle", "build", ".idea", ".vs", "bin", "obj", "target", 
                        "__pycache__", "node_modules", "vendor", ".git", "out",
                        "cmake-build-debug", "CMakeFiles"}
        exclude_file_patterns = {"*.class", "*.jar", "*.war", "*.ear", "*.apk", "*.aab", 
                                 "*.dex", "*.iml", "*.pyc", "*.pyo", "*.so", "*.dll", 
                                 "*.exe", "*.o", "*.a", "*.min.js"}
        
        for root, dirs, files in os.walk(dirpath):
            # Исключаем ненужные директории из обхода
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            rel_root = os.path.relpath(root, dirpath)
            target_root = os.path.join(project_target, rel_root) if rel_root != "." else project_target
            os.makedirs(target_root, exist_ok=True)

            for fn in files:
                src = os.path.join(root, fn)
                rel_path = os.path.relpath(src, dirpath)

                # Проверяем надо ли удалять (явный список от AI)
                should_del = any(
                    del_pattern in rel_path or del_pattern == fn
                    for del_pattern in files_to_delete
                )
                
                # Проверяем является ли файл build-артефактом
                if not should_del:
                    should_del = is_build_artifact(src, dirpath)
                
                if should_del:
                    logger.info(f"  │ 🗑  {rel_path} → на удаление (build-артефакт)")
                    deleted += 1
                    continue

                dst = os.path.join(target_root, fn)
                sh.copy2(src, dst)
                copied += 1

        logger.info(f"  ✅ Проект скопирован: {copied} файлов, {deleted} удалено -> {project_target}")

        # Помечаем все файлы проекта как обработанные
        for root, dirs, files in os.walk(dirpath):
            for fn in files:
                fp = os.path.join(root, fn)
                rel_path = os.path.relpath(fp, dirpath)
                should_del = any(
                    del_pattern in rel_path or del_pattern == fn
                    for del_pattern in files_to_delete
                )
                h = compute_file_hash(fp)
                if not should_del:
                    fi = FileInfo(
                        original_path=fp,
                        filename=fn,
                        extension=Path(fn).suffix.lstrip("."),
                        size=os.path.getsize(fp),
                        file_hash=h,
                        ai_category="Проекты",
                        ai_subcategory=project_type or project_name,
                        ai_suggested_name=project_name,
                        ai_description=f"Файл проекта '{project_name}' ({project_type})",
                        target_path=os.path.join(project_target, rel_path),
                    )
                    self.state.mark_processed(fi)
                    self.state.moved_files[fp] = fi.target_path
                    results.append(fi)

        self.state.save()
        return results

    def _move_single_file(self, info: FileInfo, dry_run: bool,
                           archive_source: str = "", archive_extract_dir: str = "") -> bool:
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

            # Provenance card
            self.provenance.upsert(
                file_hash=info.file_hash or compute_file_hash(target),
                filename=info.filename,
                original_path=info.original_path,
                current_path=target,
                category=info.ai_category,
                subcategory=info.ai_subcategory,
                description=info.ai_description,
                archive_source=archive_source,
                archive_extract_dir=archive_extract_dir,
                reason="reprocess" if self.state.is_already_processed(info.file_hash) else "initial",
                ai_reasoning=info.ai_reasoning,
                algorithmic_reasoning=info.algorithmic_reasoning,
            )

            self.state.save()
            self.provenance.save()

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
    def run(self, dry_run: bool = False, skip_diagnostics: bool = False, limit: int = 0,
            cumulative_report: bool = False):
        """Запустить обработку.
        
        cumulative_report: если True — один общий отчёт, иначе — отчёт на запуск.
        """
        self._cumulative_report = cumulative_report
        # ── Диагностика ──
        if not skip_diagnostics:
            diag = run_diagnostics()
            print(diag.report())
            if not diag.all_ok:
                failed = diag.required_missing
                if failed:
                    logger.error(f"Критические зависимости отсутствуют: {', '.join(failed)}")
                    logger.error("Завершаю работу. Устраните проблемы или используйте --no-diagnostics")
                    sys.exit(1)
                else:
                    # Только опциональные не найдены — продолжаем
                    opt = diag.optional_missing
                    logger.info(f"Опционально не найдено: {', '.join(opt)}")

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

        # 1.5. Анализ каталогов как проектов (до обработки файлов)
        self._analyze_directories(dry_run=dry_run)

        # Для full scan (без limit) — дополнительная фильтрация
        if limit == 0:
            pending = [fp for fp in self.all_files
                       if dry_run or not self.state.is_already_processed(compute_file_hash(fp))]
        else:
            pending = list(self.all_files)

        logger.info(f"Всего найдено: {len(self.all_files)}, к обработке: {len(pending)}")

        # 1.6. Проверка доступности LocalAI (только если есть файлы и не dry-run)
        if pending and not dry_run:
            logger.info("Проверка доступности LocalAI...")
            if not self.localai.is_available(timeout=30):
                logger.error("❌ LocalAI недоступен! Проверьте:")
                logger.error(f"   URL: {self.localai.base_url}")
                logger.error(f"   Модель: {self.localai.model}")
                logger.error(f"   Текст: {self.localai.text_model}")
                logger.error("Завершаю работу.")
                sys.exit(1)
            logger.info("✓ LocalAI доступен")

        # 2. Загрузка категорий из state + сканирование target
        self._load_existing_categories()
        self._scan_existing_categories()

        # 2.3. Нормализация категорий (в начале запуска)
        self._normalize_categories()

        # 2.5. Построить индекс хешей для дубликатов
        self._hash_index: dict[str, str] = {}
        self._build_hash_index()

        # 3. Обработка каждого файла (анализ → перемещение сразу)
        logger.info("Начинаю обработку...")
        processed_count = 0
        total = len(pending)
        for i, fp in enumerate(pending):
            if self._stop_requested:
                logger.info(f"⏹ Остановка по запросу. Обработано {processed_count} файлов.")
                break

            # Показываем номер ДО начала работы
            logger.info(f"  ── [{i+1}/{total}] ── {Path(fp).name}")
            ext = Path(fp).suffix.lstrip(".")
            try:
                # Проверка дубликата по хешу
                fp_hash = compute_file_hash(fp)
                if fp_hash in self._hash_index:
                    dup_path = self._hash_index[fp_hash]
                    logger.info(f"  │ ⏭ Дубликат {Path(dup_path).name} — пропускаю")
                    self._record_stats(ext, "skipped")
                    continue

                info = self.analyze_file(fp)

                # Проверка: LocalAI перестал отвечать
                if self.localai.is_fatal() and not dry_run:
                    logger.error(f"\n❌ {self.localai.fatal_message()}")
                    logger.error("Обработка остановлена. State сохранён.")
                    self._record_stats(ext, "error")
                    self._stop_requested = True
                    break

                self.file_infos.append(info)
                self._print_decision(info, dry_run=dry_run)

                # Если архив — распаковать и обработать содержимое
                if info.is_archive:
                    self._process_archive_contents(info, dry_run=dry_run)
                else:
                    # Перемещаем сразу после анализа
                    self._move_single_file(info, dry_run=dry_run)

                self._record_stats(ext, "ok")
                processed_count += 1

                # Проверяем необходимость нормализации после каждых 100 новых подкатегорий
                self._check_normalization_trigger()

            except Exception as e:
                logger.error(f"  ✗ Ошибка: {e}")
                self.errors.append(str(e))
                self._record_stats(ext, "error")

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
        
        # Определяем причину завершения
        stop_reason = self.localai.get_stop_reason()
        if stop_reason:
            logger.error(f"❌ {stop_reason}")
            logger.error("Обработка остановлена из-за накопленных ошибок LocalAI.")
        elif self._stop_requested:
            logger.info("⏹ Остановлено пользователем")
        else:
            logger.info("✓ Обработка завершена успешно")
        
        logger.info(f"Ошибок: {len(self.errors)}")
        self._print_stats()
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

    def _get_categories_with_counts(self) -> dict:
        """Собрать статистику по категориям и подкатегориям с количеством файлов."""
        from pathlib import Path
        
        cats_stats = {}  # category -> {"count": int, "subcategories": {subcat: count}}
        
        if not self.target.exists():
            return cats_stats
        
        for root, dirs, files in os.walk(self.target):
            rel = os.path.relpath(root, self.target)
            # Пропускаем служебные каталоги
            if rel.startswith("_"):
                dirs.clear()
                continue
            
            parts = Path(rel).parts
            if len(parts) >= 1 and parts[0] and not parts[0].startswith("_"):
                cat = parts[0]
                subcat = parts[1] if len(parts) >= 2 else None
                
                if cat not in cats_stats:
                    cats_stats[cat] = {"count": 0, "subcategories": {}}
                
                # Считаем файлы в текущей директории
                file_count = len([f for f in files if not f.startswith(".")])
                cats_stats[cat]["count"] += file_count
                
                if subcat:
                    if subcat not in cats_stats[cat]["subcategories"]:
                        cats_stats[cat]["subcategories"][subcat] = 0
                    cats_stats[cat]["subcategories"][subcat] += file_count
            
            dirs[:] = [d for d in dirs if not d.startswith("_")]
        
        return cats_stats

    def _normalize_categories(self, processed_since_last_check: int = 0):
        """Проверить и выполнить нормализацию категорий через ИИ.
        
        Вызывается после каждых 100 новых подкатегорий или в начале запуска.
        """
        # Проверяем нужно ли запускать нормализацию
        total_subcats = sum(len(subs) for subs in self.state.categories.values())
        
        # Нормализация нужна если:
        # 1. Это начало запуска (processed_since_last_check == 0 и total_subcats > 0)
        # 2. Или добавлено 100+ новых подкатегорий с последней проверки
        should_normalize = False
        
        if hasattr(self, '_last_normalization_subcat_count'):
            new_subcats = total_subcats - self._last_normalization_subcat_count
            if new_subcats >= 100:
                should_normalize = True
                logger.info(f"📊 Добавлено {new_subcats} новых подкатегорий — запускаю нормализацию...")
        elif total_subcats > 0:
            # Первый запуск с существующими категориями
            should_normalize = True
            logger.info(f"📊 Найдено {total_subcats} подкатегорий — запускаю начальную нормализацию...")
        
        if not should_normalize:
            return
        
        # Собираем статистику по категориям
        cats_stats = self._get_categories_with_counts()
        if not cats_stats:
            logger.info("  ⏭ Нет категорий для нормализации")
            return
        
        # Формируем запрос к ИИ
        cats_list = []
        for cat in sorted(cats_stats.keys()):
            data = cats_stats[cat]
            cat_count = data["count"]
            subs = data["subcategories"]
            
            cats_list.append(f"- {cat} (всего файлов: {cat_count})")
            for subcat in sorted(subs.keys()):
                cats_list.append(f"    • {subcat}: {subs[subcat]} файлов")
        
        cats_text = "\n".join(cats_list)
        
        prompt = f"""Проанализируй список категорий и подкатегорий архива и предложи какие из них можно объединить.

Список категорий (с количеством файлов):
{cats_text}

Ответь в формате JSON:
{{
  "merges": [
    {{
      "source_categories": ["Категория1", "Категория2"],
      "source_subcategories": [["подкат1", "подкат2"], ["подкат3"]],
      "target_category": "Новое название категории",
      "target_subcategory": "Новое название подкатегории или null",
      "reason": "Причина объединения"
    }}
  ]
}}

Правила:
1. Объединяй категории/подкатегории с похожей тематикой
2. Предлагай понятные общие названия для объединённых категорий
3. Если target_subcategory = null, файлы будут в корне категории
4. Не объединяй всё подряд — только действительно похожие категории
5. Учитывай что перемещение файлов должно быть логичным

Отвечай ТОЛЬКО валидным JSON."""

        try:
            result = self.localai.analyze_content(text_content=prompt)
            if not result or "merges" not in result:
                logger.info("  ⚠ ИИ не предложил вариантов объединения")
                return
            
            merges = result.get("merges", [])
            if not merges:
                logger.info("  ✓ Категории в порядке, объединений не требуется")
                return
            
            logger.info(f"  🤖 ИИ предложил {len(merges)} вариантов объединения:")
            for merge in merges:
                src_cats = merge.get("source_categories", [])
                target_cat = merge.get("target_category", "")
                reason = merge.get("reason", "")
                logger.info(f"     {' + '.join(src_cats)} → {target_cat} ({reason})")
            
            # Выполняем слияния
            self._execute_category_merges(merges)
            
        except Exception as e:
            logger.error(f"  ❌ Ошибка нормализации категорий: {e}")
        
        # Обновляем счётчик
        self._last_normalization_subcat_count = total_subcats

    def _check_normalization_trigger(self):
        """Проверить, добавлено ли 100+ новых подкатегорий и запустить нормализацию."""
        total_subcats = sum(len(subs) for subs in self.state.categories.values())
        
        if hasattr(self, '_last_normalization_subcat_count'):
            new_subcats = total_subcats - self._last_normalization_subcat_count
            if new_subcats >= 100:
                logger.info(f"📊 Добавлено {new_subcats} новых подкатегорий — запускаю нормализацию...")
                self._normalize_categories()

    def _execute_category_merges(self, merges: list):
        """Выполнить слияние категорий согласно рекомендациям ИИ."""
        import shutil
        
        for merge in merges:
            source_categories = merge.get("source_categories", [])
            source_subcategories = merge.get("source_subcategories", [[]])
            target_category = merge.get("target_category", "")
            target_subcategory = merge.get("target_subcategory")
            
            if not source_categories or not target_category:
                continue
            
            logger.info(f"  🔀 Объединение: {' + '.join(source_categories)} → {target_category}")
            
            # Обрабатываем каждую исходную категорию
            for i, src_cat in enumerate(source_categories):
                src_cat_path = os.path.join(self.target, src_cat)
                if not os.path.exists(src_cat_path):
                    logger.info(f"     ⏭ Категория '{src_cat}' не найдена, пропускаю")
                    continue
                
                # Определяем подкатегории для этой категории
                src_subcats = source_subcategories[i] if i < len(source_subcategories) else []
                
                # Если подкатегории не указаны — берём все
                if not src_subcats:
                    src_subcats = list(self.existing_subcategories.get(src_cat, set()))
                
                # Путь к целевой категории
                target_cat_path = os.path.join(self.target, target_category)
                
                for src_subcat in src_subcats:
                    src_subcat_path = os.path.join(src_cat_path, src_subcat)
                    if not os.path.exists(src_subcat_path):
                        logger.info(f"     ⏭ Подкатегория '{src_cat}/{src_subcat}' не найдена")
                        continue
                    
                    # Определяем целевую подкатегорию
                    if target_subcategory:
                        target_subcat_path = os.path.join(target_cat_path, target_subcategory)
                    else:
                        # Файлы будут в корне категории
                        target_subcat_path = target_cat_path
                    
                    # Создаём целевую директорию
                    os.makedirs(target_subcat_path, exist_ok=True)
                    
                    # Перемещаем файлы с обработкой коллизий
                    moved = 0
                    for item in os.listdir(src_subcat_path):
                        src_item = os.path.join(src_subcat_path, item)
                        
                        # Определяем целевое имя с обработкой коллизий
                        target_item = os.path.join(target_subcat_path, item)
                        
                        if os.path.exists(target_item):
                            # Коллизия — переименовываем
                            stem = Path(item).stem
                            ext = Path(item).suffix
                            counter = 1
                            while os.path.exists(target_item):
                                target_item = os.path.join(target_subcat_path, f"{stem}_{counter}{ext}")
                                counter += 1
                            logger.info(f"        ⚠️ Коллизия: {item} → {Path(target_item).name}")
                        
                        try:
                            shutil.move(src_item, target_item)
                            moved += 1
                        except Exception as e:
                            logger.error(f"        ❌ Ошибка перемещения {item}: {e}")
                    
                    logger.info(f"     ✅ Перемещено {moved} файлов из '{src_cat}/{src_subcat}'")
                
                # Удаляем пустую исходную категорию
                try:
                    if not os.listdir(src_cat_path):
                        os.rmdir(src_cat_path)
                        logger.info(f"     🗑 Удалена пустая категория '{src_cat}'")
                    else:
                        # Проверяем остались ли подкатегории
                        remaining = [d for d in os.listdir(src_cat_path) 
                                   if os.path.isdir(os.path.join(src_cat_path, d))]
                        if not remaining:
                            # Остались только файлы в корне — тоже удаляем если нужно
                            pass
                except Exception as e:
                    logger.error(f"     ⚠ Не удалось удалить '{src_cat}': {e}")
            
            # Обновляем состояние категорий
            self._scan_existing_categories()

    def _save_report(self):
        """Сохранить отчёт.
        
        По умолчанию: именной файл на каждый запуск.
        С --cumulative-report: один общий organizer_report.json.
        """
        run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        mode = "dry-run" if self._cumulative_report and self.file_infos else ""

        report = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "mode": "DRY-RUN" if self._cumulative_report and self.file_infos else "LIVE",
            "source": str(self.source),
            "target": str(self.target),
            "total": len(self.file_infos),
            "errors": self.errors,
            "stats": self.stats,
            "files": [fi.to_dict() for fi in self.file_infos],
        }

        if getattr(self, '_cumulative_report', False):
            # Один общий отчёт
            path = os.path.join(self.target, "organizer_report.json")
            # Дописываем в существующий или создаём новый
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if "runs" not in existing:
                        existing = {"runs": [existing]}
                    existing.setdefault("runs", []).append(report)
                    existing["total_runs"] = len(existing["runs"])
                    report = existing
                except Exception:
                    pass
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        else:
            # Именной файл на запуск
            path = os.path.join(self.target, f"organizer_report_{run_id}.json")
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
    parser.add_argument("--restore-dir", type=str, default="", help="Восстановить все файлы из указанного исходного каталога")
    parser.add_argument("--find-file", type=str, default="", help="Найти где находится файл по его оригинальному пути")
    parser.add_argument("--provenance-stats", action="store_true", help="Показать статистику provenance")
    parser.add_argument("--restore", type=str, default="", help="Восстановить файлы из organized в исходное место (путь или 'all')")
    parser.add_argument("--cumulative-report", action="store_true", help="Один общий отчёт (по умолчанию — по запуску)")
    parser.add_argument("--cumulative-log", action="store_true", help="Один общий лог organizer.log (по умолчанию — по запуску)")
    args = parser.parse_args()

    # Логирование настраивается ДО всего остального
    log_file = _setup_logging(cumulative_log=args.cumulative_log, debug=args.debug)

    if args.reset_state:
        state_path = os.path.join(STATE_DIR, "state.json")
        if os.path.exists(state_path):
            os.remove(state_path)
            logger.info("State сброшен")

    # Логирование уже настроено выше
    logger.info(f"Лог: {log_file}")
    import clients
    if args.debug:
        clients.DEBUG = True

    # Проведение provenance-операций
    if args.provenance_stats:
        prov = ProvenanceStore(args.target)
        stats = prov.get_stats()
        print(f"\n📊 Provenance Statistics")
        print(f"  Карточек: {stats['total_cards']}")
        print(f"  Из архивов: {stats['with_archive_source']}")
        print(f"  С историей: {stats['with_move_history']}")
        print(f"  Категории:")
        for cat, n in sorted(stats['categories'].items(), key=lambda x: -x[1]):
            print(f"    {cat}: {n}")
        return

    if args.find_file:
        prov = ProvenanceStore(args.target)
        filepath = os.path.abspath(os.path.expanduser(args.find_file))
        # Ищем по хешу, original_path, или first_seen_path
        found = []
        for card in prov.cards.values():
            if (filepath in card.first_seen_path or
                filepath in card.current_path or
                any(filepath in m.get("from", "") for m in card.move_history)):
                found.append(card)
        if found:
            print(f"\n🔍 Найдено {len(found)} записей для '{args.find_file}':")
            for card in found:
                print(f"  📄 {card.filename}")
                print(f"     Первое место: {card.first_seen_path}")
                print(f"     Сейчас:       {card.current_path}")
                print(f"     Категория:    {card.category}")
                if card.archive_source:
                    print(f"     Из архива:    {card.archive_source}")
                if card.move_history:
                    print(f"     Перемещений:  {len(card.move_history)}")
        else:
            print(f"Не найдено записей для '{args.find_file}'")
        return

    if args.restore_dir:
        prov = ProvenanceStore(args.target)
        orig_dir = os.path.abspath(os.path.expanduser(args.restore_dir))
        cards = prov.find_by_first_seen(orig_dir)
        if not cards:
            # Попробуем по пути в move_history
            cards = prov.find_by_original(orig_dir)
        if not cards:
            print(f"Нет файлов из '{orig_dir}'")
            return
        print(f"\n♻️  Восстановление {len(cards)} файлов из '{orig_dir}':")
        import shutil as sh
        for card in cards:
            if os.path.exists(card.current_path):
                # Создаём директорию по original_path (first_seen_path)
                dest = card.first_seen_path
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    sh.move(card.current_path, dest)
                    print(f"  ✅ {Path(card.current_path).name} -> {dest}")
                    del prov.cards[card.file_hash]
                except Exception as e:
                    print(f"  ❌ {Path(card.current_path).name}: {e}")
            else:
                print(f"  ⚠️  {card.filename} не найден в {card.current_path}")
        prov.save()
        return

    if args.restore:
        state = ProcessingState.load()
        if not state.restore_map:
            logger.info("Нет карты восстановления в state")
            return
        if args.restore == "all":
            restore_map = dict(state.restore_map)
        else:
            restore_map = {t: v for t, v in state.restore_map.items() if args.restore in t}
        logger.info(f"Восстановление {len(restore_map)} файлов...")
        import shutil
        for target_path, info in restore_map.items():
            orig = info["original_path"]
            if os.path.exists(target_path):
                os.makedirs(os.path.dirname(orig), exist_ok=True)
                shutil.move(target_path, orig)
                logger.info(f"  ✅ {Path(target_path).name} -> {orig}")
                del state.restore_map[target_path]
        state.save()
        return

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
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics, limit=0, cumulative_report=args.cumulative_report)
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
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics, cumulative_report=args.cumulative_report)
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
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics, cumulative_report=args.cumulative_report)
    else:
        organizer.run(dry_run=args.dry_run, skip_diagnostics=args.no_diagnostics,
                      limit=args.limit, cumulative_report=args.cumulative_report)


if __name__ == "__main__":
    main()
