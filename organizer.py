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

from config import (
    SOURCE_DIR, TARGET_DIR, DELETE_DIR, ARCHIVE_DIR,
    UNKNOWN_DIR, BUILD_ARTIFACTS_DIR, STATE_DIR,
)
from models import FileInfo, ImageMetadata, ProcessingState
from clients import LocalAIClient, SearXNGClient
from analyzer import compute_file_hash, extract_text, is_archive, is_executable, is_image
from metadata import read_image_metadata
from projects import find_project_root, is_build_artifact
from archives import extract_archive
from duplicates import detect_and_handle_duplicates
from relationships import group_related_files
from diagnostics import run_diagnostics

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

    # ── Шаг 1: Сбор ──────────────────────────────
    def collect_files(self) -> list[str]:
        files = []
        source_resolved = str(Path(self.source).resolve())
        for root, dirs, filenames in os.walk(source_resolved, followlinks=True):
            for fn in filenames:
                fp = os.path.join(root, fn)
                files.append(fp)
        self.all_files = files
        logger.info(f"Найдено файлов: {len(files)}")
        return files

    # ── Шаг 2: Анализ ────────────────────────────
    def analyze_file(self, filepath: str) -> FileInfo:
        p = Path(filepath)
        ext = p.suffix.lower().lstrip(".")
        size = os.path.getsize(filepath)
        mime = _guess_mime(filepath)

        info = FileInfo(
            original_path=filepath,
            filename=p.name,
            extension=ext,
            size=size,
            mime_type=mime or "unknown",
        )

        # Хеш
        info.file_hash = compute_file_hash(filepath)

        # Проект
        proj_root = find_project_root(filepath)
        if proj_root:
            info.is_part_of_project = True
            info.project_root = proj_root
            if is_build_artifact(filepath, proj_root):
                info.is_build_artifact = True
                info.should_delete = True
                info.ai_category = "build_artifact"
                info.ai_description = f"Build-артефакт проекта {Path(proj_root).name}"
                return info

        # Очень большие файлы
        if size > 500 * 1024 * 1024:
            info.ai_category = "дистрибутив / образ"
            info.ai_description = f"Очень большой файл ({size / (1024**3):.1f} GB)"
            return info

        # Архив
        if is_archive(filepath):
            info.is_archive = True
            info.ai_category = "архив"
            info.ai_description = f"Архив {ext}"
            return info

        # Исполняемый / дистрибутив
        if is_executable(filepath) or ext == "iso":
            info.ai_category = "дистрибутив"
            info.is_distributable = self.searxng.is_known_distributable(p.name)
            info.should_delete = info.is_distributable
            return info

        # Изображение — метаданные + AI
        if is_image(filepath):
            info.image_metadata = read_image_metadata(filepath)

        # AI-анализ (текст и/или изображение)
        text = extract_text(filepath)
        ai_result = self.localai.analyze_content(
            text_content=text,
            image_path=filepath if is_image(filepath) else "",
            file_context=f"Имя: {p.name}, Каталог: {p.parent.name}",
        )
        if ai_result:
            info.ai_category = ai_result.get("category", "неразобранное")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)

        return info

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

    # ── Шаг 5: Архивы ────────────────────────────
    def process_archives(self, dry_run: bool = False):
        archives = [fi for fi in self.file_infos if fi.is_archive]
        for info in archives:
            extract_dir = os.path.join(ARCHIVE_DIR, Path(info.original_path).stem)
            logger.info(f"Распаковка: {info.filename}")
            if dry_run:
                logger.info(f"  [DRY] -> {extract_dir}")
                continue
            extracted = extract_archive(info.original_path, extract_dir)
            if extracted:
                logger.info(f"  Распаковано: {len(extracted)} файлов")
                # Анализируем содержимое
                for ef in extracted:
                    fp = os.path.join(extract_dir, ef)
                    if os.path.isfile(fp):
                        ei = self.analyze_file(fp)
                        self.file_infos.append(ei)
            else:
                self.errors.append(f"Не распакован: {info.original_path}")

    # ── Шаг 6: Перемещение ───────────────────────
    def _print_decision(self, info: FileInfo, dry_run: bool = False):
        """Вывести подробное решение по файлу."""
        prefix = "  │ "
        logger.info(f"{prefix}📁 Категория: {info.ai_category or '—'}")
        if info.ai_subcategory:
            logger.info(f"{prefix}📂 Подкатегория: {info.ai_subcategory}")
        if info.ai_suggested_name:
            logger.info(f"{prefix}✏️  Имя: {info.ai_suggested_name}.{info.extension}")
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

        # Избегаем коллизий
        target = os.path.join(*parts)
        if os.path.exists(target):
            ts = int(datetime.now().timestamp())
            target = str(Path(target).parent / f"{Path(target).stem}_{ts}{Path(target).suffix}")

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
                moved += 1
            except Exception as e:
                logger.error(f"Ошибка перемещения {info.filename}: {e}")
                self.errors.append(str(e))
                skipped += 1

        logger.info(f"Перемещено: {moved}, пропущено: {skipped}")

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
        logger.info("=" * 60)

        if not dry_run:
            for d in (self.target, DELETE_DIR, ARCHIVE_DIR, UNKNOWN_DIR,
                      BUILD_ARTIFACTS_DIR, STATE_DIR):
                os.makedirs(d, exist_ok=True)

        # 1. Сбор
        if not self.all_files:
            self.collect_files()

        # Ограничение
        if limit > 0:
            self.all_files = self.all_files[:limit]
            logger.info(f"Ограничение: обрабатываю {limit} файлов из {len(self.all_files)}")

        # 2. Анализ
        logger.info("Анализ файлов...")
        for fp in self.all_files:
            # Пропускаем уже обработанные
            fh = compute_file_hash(fp)
            if self.state.is_already_processed(fh) and not dry_run:
                logger.info(f"  ⏭ Пропуск (уже обработан): {Path(fp).name}")
                continue
            try:
                logger.info(f"  ┌─ {Path(fp).name}")
                info = self.analyze_file(fp)
                self.file_infos.append(info)
                # Сразу показываем решение
                self._print_decision(info, dry_run=dry_run)
            except Exception as e:
                logger.error(f"  ✗ Ошибка анализа {fp}: {e}")
                self.errors.append(str(e))

        # 3. Дубликаты
        logger.info("Поиск дубликатов...")
        self.handle_duplicates()

        # 4. Связи
        logger.info("Определение связей...")
        self.find_relationships()

        # 5. Архивы
        archives = [fi for fi in self.file_infos if fi.is_archive]
        if archives:
            logger.info(f"Распаковка {len(archives)} архивов...")
            self.process_archives(dry_run=dry_run)

        # 6. Статистика
        cats = {}
        for fi in self.file_infos:
            cat = fi.ai_category or "?"
            cats[cat] = cats.get(cat, 0) + 1
        logger.info("Категории:")
        for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
            logger.info(f"  {cat}: {n}")

        # 7. Перемещение
        logger.info("Перемещение...")
        self.move_files(dry_run=dry_run)

        # 8. Сохранение state
        if not dry_run:
            self.state.save()
            self._save_report()

        logger.info(f"Ошибок: {len(self.errors)}")
        logger.info("Готово.")

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
    args = parser.parse_args()

    if args.reset_state:
        state_path = os.path.join(STATE_DIR, "state.json")
        if os.path.exists(state_path):
            os.remove(state_path)
            logger.info("State сброшен")

    organizer = FileOrganizer(args.source, args.target)

    if args.first_level_only:
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
