"""Localization (i18n) — all user-facing strings.

Usage:
    from localization import t
    t("diagnostics.all_ok")
    t("status.moving", filename="test.txt", target="/path")
"""

from __future__ import annotations

from config import LANGUAGE

# ── Translations ──────────────────────────────────────────────────────

STRINGS: dict[str, dict[str, str]] = {
    # ── Diagnostics ──
    "diagnostics.title": {
        "ru": "Диагностика зависимостей",
        "en": "Dependency Diagnostics",
    },
    "diagnostics.ok": {
        "ru": "Всё в порядке",
        "en": "All good",
    },
    "diagnostics.not_ready": {
        "ru": "НЕ ГОТОВО: {items}",
        "en": "NOT READY: {items}",
    },
    "diagnostics.continue_warning": {
        "ru": "Не все зависимости доступны. Продолжаю на свой страх и риск...\nИли запустите: python -m diagnostics для подробностей",
        "en": "Not all dependencies are available. Continuing at your own risk...\nOr run: python -m diagnostics for details",
    },

    # ── Status messages ──
    "status.file": {
        "ru": "  ── [{i}/{total}] ── {filename}",
        "en": "  ── [{i}/{total}] ── {filename}",
    },
    "status.type_size": {
        "ru": "  │ 📂 Тип: {ext} | 📏 {size}",
        "en": "  │ 📂 Type: {ext} | 📏 {size}",
    },
    "status.module": {
        "ru": "  → Модуль: {module}",
        "en": "  → Module: {module}",
    },
    "status.requesting": {
        "ru": "  → Запрос к LocalAI (model={model}, timeout={timeout}s)...",
        "en": "  → Requesting LocalAI (model={model}, timeout={timeout}s)...",
    },
    "status.response": {
        "ru": "  ← Ответ получен, HTTP {status}",
        "en": "  ← Response received, HTTP {status}",
    },
    "status.transcribing": {
        "ru": "  → Транскрипция аудио (whisperx-tiny)...",
        "en": "  → Transcribing audio (whisperx-tiny)...",
    },
    "status.transcript": {
        "ru": "  ← Транскрипт: {count} символов",
        "en": "  ← Transcript: {count} chars",
    },
    "status.extracting_keyframes": {
        "ru": "  → Извлечение ключевых кадров...",
        "en": "  → Extracting keyframes...",
    },
    "status.keyframes_extracted": {
        "ru": "  ← Извлечено {count} кадров, VL-модель описывает...",
        "en": "  ← Extracted {count} frames, VL model describing...",
    },
    "status.frame_description": {
        "ru": "  ← Описание: {desc}",
        "en": "  ← Description: {desc}",
    },
    "status.converting_image": {
        "ru": "  → Конвертация {ext} → JPEG...",
        "en": "  → Converting {ext} → JPEG...",
    },
    "status.converted": {
        "ru": "  ← Готово: {filename}",
        "en": "  ← Done: {filename}",
    },
    "status.vl_describing": {
        "ru": "  → VL-модель описывает изображение...",
        "en": "  → VL model describing image...",
    },
    "status.pdf_converting": {
        "ru": "  → PDF без текста, конвертирую в JPEG...",
        "en": "  → PDF without text, converting to JPEG...",
    },
    "status.pdf_converted": {
        "ru": "  ← Создано {count} JPEG, VL-модель описывает...",
        "en": "  ← Created {count} JPEGs, VL model describing...",
    },
    "status.archive_extracting": {
        "ru": "  {indent}📦 Распаковка архива...",
        "en": "  {indent}📦 Extracting archive...",
    },
    "status.archive_dry": {
        "ru": "  {indent}[DRY] Распаковка -> {path}",
        "en": "  {indent}[DRY] Extract -> {path}",
    },
    "status.archive_failed": {
        "ru": "  {indent}⚠️ Не удалось распаковать {filename}",
        "en": "  {indent}⚠️ Failed to extract {filename}",
    },
    "status.archive_extracted": {
        "ru": "  {indent}📦 Распаковано {count} файлов, обрабатываю...",
        "en": "  {indent}📦 Extracted {count} files, processing...",
    },
    "status.temp_file": {
        "ru": "  {indent}  🗑️ Временный файл: {filename}",
        "en": "  {indent}  🗑️ Temp file: {filename}",
    },
    "status.duplicate": {
        "ru": "  {indent}  ⏭ {filename} — дубликат {dup}",
        "en": "  {indent}  ⏭ {filename} — duplicate of {dup}",
    },
    "status.already_processed": {
        "ru": "  {indent}  ⏭ {filename} — уже обработан",
        "en": "  {indent}  ⏭ {filename} — already processed",
    },
    "status.error": {
        "ru": "  {indent}  ✗ Ошибка обработки {path}: {error}",
        "en": "  {indent}  ✗ Error processing {path}: {error}",
    },
    "status.general_error": {
        "ru": "  ✗ Ошибка: {error}",
        "en": "  ✗ Error: {error}",
    },
    "status.move_success": {
        "ru": "  │ ✅ -> {target}",
        "en": "  │ ✅ -> {target}",
    },
    "status.move_error": {
        "ru": "  │ ❌ Ошибка перемещения {filename}: {error}",
        "en": "  │ ❌ Error moving {filename}: {error}",
    },
    "status.move_dry": {
        "ru": "  │ [DRY] {action}: {target}",
        "en": "  │ [DRY] {action}: {target}",
    },
    "status.name_collision": {
        "ru": "  │ ⚠️ Коллизия имён -> {filename}",
        "en": "  │ ⚠️ Name collision -> {filename}",
    },

    # ── Decision display ──
    "decision.category": {
        "ru": "  │ 📁 Категория: {cat}",
        "en": "  │ 📁 Category: {cat}",
    },
    "decision.subcategory": {
        "ru": "  │ 📂 Подкатегория: {sub}",
        "en": "  │ 📂 Subcategory: {sub}",
    },
    "decision.name": {
        "ru": "  │ ✏️  Имя: {name}",
        "en": "  │ ✏️  Name: {name}",
    },
    "decision.description": {
        "ru": "  │ 💬 {desc}",
        "en": "  │ 💬 {desc}",
    },
    "decision.reasoning": {
        "ru": "  │ 🤔 {reason}",
        "en": "  │ 🤔 {reason}",
    },
    "decision.build_artifact": {
        "ru": "  │ 🔨 BUILD-АРТЕФАКТ → удаление",
        "en": "  │ 🔨 BUILD ARTIFACT → delete",
    },
    "decision.archive": {
        "ru": "  │ 📦 Архив → распаковка и анализ содержимого",
        "en": "  │ 📦 Archive → extract and analyze contents",
    },
    "decision.distributable": {
        "ru": "  │ 🗑  Дистрибутив → в каталог «на_удаление»",
        "en": "  │ 🗑  Distributable → _delete_later directory",
    },
    "decision.duplicate": {
        "ru": "  │ 📋 Дубликат → {action}",
        "en": "  │ 📋 Duplicate → {action}",
    },
    "decision.duplicate_original": {
        "ru": "  │    оригинал: {filename}",
        "en": "  │    original: {filename}",
    },
    "decision.project": {
        "ru": "  │ 🛠  Часть проекта: {project}",
        "en": "  │ 🛠  Part of project: {project}",
    },
    "decision.related": {
        "ru": "  │ 🔗 Связанные: {count} файлов",
        "en": "  │ 🔗 Related: {count} files",
    },
    "decision.photo": {
        "ru": "  │ 📷 EXIF: {info}",
        "en": "  │ 📷 EXIF: {info}",
    },
    "decision.audio": {
        "ru": "  │ 🎵 {info}",
        "en": "  │ 🎵 {info}",
    },
    "decision.transcript": {
        "ru": "  │ 🎤 Транскрипт: {text}",
        "en": "  │ 🎤 Transcript: {text}",
    },
    "decision.target": {
        "ru": "  │ └─ ▶ {target}",
        "en": "  │ └─ ▶ {target}",
    },

    # ── Duplicate actions ──
    "dup.delete": {
        "ru": "удалить (дубликат)",
        "en": "delete (duplicate)",
    },
    "dup.keep": {
        "ru": "оставить (оригинал)",
        "en": "keep (original)",
    },
    "dup.keep_project": {
        "ru": "оставить (часть проекта)",
        "en": "keep (part of project)",
    },

    # ── Signal handling ──
    "signal.int": {
        "ru": "SIGINT (Ctrl-C)",
        "en": "SIGINT (Ctrl-C)",
    },
    "signal.term": {
        "ru": "SIGTERM (systemd stop)",
        "en": "SIGTERM (systemd stop)",
    },
    "signal.graceful": {
        "ru": "\n⚠️  Получен {signal}. Завершаю после текущего файла...\n     Повторите сигнал в течение 2 секунд для немедленного выхода.",
        "en": "\n⚠️  Received {signal}. Finishing current file...\n     Repeat signal within 2 seconds for immediate exit.",
    },
    "signal.immediate": {
        "ru": "\n⚡ Повторный сигнал! Немедленное завершение...",
        "en": "\n⚡ Repeated signal! Immediate shutdown...",
    },
    "signal.stopped": {
        "ru": "⏹ Остановка по запросу. Обработано {count} файлов.",
        "en": "⏹ Stopped by request. Processed {count} files.",
    },
    "signal.stopped_user": {
        "ru": "⏹ Остановлено пользователем/state сохранён",
        "en": "⏹ Stopped by user/state saved",
    },

    # ── Run info ──
    "run.header": {
        "ru": "File Organizer | {mode}",
        "en": "File Organizer | {mode}",
    },
    "run.mode_dry": {
        "ru": "DRY-RUN",
        "en": "DRY-RUN",
    },
    "run.mode_live": {
        "ru": "LIVE",
        "en": "LIVE",
    },
    "run.source": {
        "ru": "Источник: {path}",
        "en": "Source: {path}",
    },
    "run.target": {
        "ru": "Цель:     {path}",
        "en": "Target:   {path}",
    },
    "run.last_run": {
        "ru": "Последний запуск: {time}",
        "en": "Last run: {time}",
    },
    "run.last_run_never": {
        "ru": "никогда",
        "en": "never",
    },
    "run.processed": {
        "ru": "В state обработано: {count}",
        "en": "Processed in state: {count}",
    },
    "run.found": {
        "ru": "Найдено файлов: {count}",
        "en": "Found files: {count}",
    },
    "run.found_limited": {
        "ru": "Собрано {count} файлов для обработки (лимит {limit})",
        "en": "Collected {count} files for processing (limit {limit})",
    },
    "run.total": {
        "ru": "Всего найдено: {total}, к обработке: {pending}",
        "en": "Total found: {total}, to process: {pending}",
    },
    "run.categories_found": {
        "ru": "Найдено существующих категорий: {count}",
        "en": "Found existing categories: {count}",
    },
    "run.duplicates_index": {
        "ru": "Индекс дубликатов: {count} файлов",
        "en": "Duplicates index: {count} files",
    },
    "run.duplicates_disabled": {
        "ru": "Индекс дубликатов: отключён (reprocess)",
        "en": "Duplicates index: disabled (reprocess)",
    },
    "run.scanning_organized": {
        "ru": "Сканирую organized/ для индекса дубликатов...",
        "en": "Scanning organized/ for duplicates index...",
    },
    "run.scanning_found": {
        "ru": "  найдено: {count} файлов",
        "en": "  found: {count} files",
    },
    "run.starting": {
        "ru": "Начинаю обработку...",
        "en": "Starting processing...",
    },
    "run.categories": {
        "ru": "Категории:",
        "en": "Categories:",
    },
    "run.errors": {
        "ru": "Ошибок: {count}",
        "en": "Errors: {count}",
    },
    "run.done": {
        "ru": "Готово.",
        "en": "Done.",
    },
    "run.report": {
        "ru": "Отчёт: {path}",
        "en": "Report: {path}",
    },

    # ── Directories ──
    "dir.delete_later": {
        "ru": "_на_удаление",
        "en": "_delete_later",
    },
    "dir.archives": {
        "ru": "_архивы",
        "en": "_archives",
    },
    "dir.unknown": {
        "ru": "_неразобранное",
        "en": "_unknown",
    },
    "dir.build_artifacts": {
        "ru": "_build_artifacts",
        "en": "_build_artifacts",
    },
    "dir.projects": {
        "ru": "Проекты",
        "en": "Projects",
    },

    # ── Provenance ──
    "prov.stats_title": {
        "ru": "📊 Provenance Statistics",
        "en": "📊 Provenance Statistics",
    },
    "prov.total_cards": {
        "ru": "  Карточек: {count}",
        "en": "  Cards: {count}",
    },
    "prov.from_archives": {
        "ru": "  Из архивов: {count}",
        "en": "  From archives: {count}",
    },
    "prov.with_history": {
        "ru": "  С историей: {count}",
        "en": "  With history: {count}",
    },
    "prov.categories": {
        "ru": "  Категории:",
        "en": "  Categories:",
    },
    "prov.find_title": {
        "ru": "🔍 Найдено {count} записей для '{query}':",
        "en": "🔍 Found {count} records for '{query}':",
    },
    "prov.find_not_found": {
        "ru": "Не найдено записей для '{query}'",
        "en": "No records found for '{query}'",
    },
    "prov.find_filename": {
        "ru": "  📄 {filename}",
        "en": "  📄 {filename}",
    },
    "prov.find_first_seen": {
        "ru": "     Первое место: {path}",
        "en": "     First seen: {path}",
    },
    "prov.find_current": {
        "ru": "     Сейчас:       {path}",
        "en": "     Current:      {path}",
    },
    "prov.find_category": {
        "ru": "     Категория:    {cat}",
        "en": "     Category:     {cat}",
    },
    "prov.find_archive": {
        "ru": "     Из архива:    {path}",
        "en": "     From archive: {path}",
    },
    "prov.find_moves": {
        "ru": "     Перемещений:  {count}",
        "en": "     Moves:        {count}",
    },
    "prov.restore_title": {
        "ru": "♻️  Восстановление {count} файлов из '{dir}':",
        "en": "♻️  Restoring {count} files from '{dir}':",
    },
    "prov.restore_not_found": {
        "ru": "Нет файлов из '{dir}'",
        "en": "No files from '{dir}'",
    },
    "prov.restore_success": {
        "ru": "  ✅ {filename} -> {dest}",
        "en": "  ✅ {filename} -> {dest}",
    },
    "prov.restore_error": {
        "ru": "  ❌ {filename}: {error}",
        "en": "  ❌ {filename}: {error}",
    },
    "prov.restore_missing": {
        "ru": "  ⚠️  {filename} не найден в {path}",
        "en": "  ⚠️  {filename} not found at {path}",
    },
    "prov.no_map": {
        "ru": "Нет карты восстановления в state",
        "en": "No restore map in state",
    },

    # ── Cleanup ──
    "cleanup.no_files": {
        "ru": "Нет перемещённых файлов для очистки.",
        "en": "No moved files to clean up.",
    },
    "cleanup.all_cleaned": {
        "ru": "Все исходные файлы уже удалены.",
        "en": "All source files already removed.",
    },
    "cleanup.found": {
        "ru": "Найдено {count} исходных файлов для удаления:",
        "en": "Found {count} source files to delete:",
    },
    "cleanup.target_exists": {
        "ru": "  ✓ целевой существует",
        "en": "  ✓ target exists",
    },
    "cleanup.target_missing": {
        "ru": "  ✗ целевой ОТСУТСТВУЕТ",
        "en": "  ✗ target MISSING",
    },
    "cleanup.dry": {
        "ru": "[DRY-RUN] Удалил бы {count} файлов",
        "en": "[DRY-RUN] Would delete {count} files",
    },
    "cleanup.cancelled": {
        "ru": "Отмена.",
        "en": "Cancelled.",
    },
    "cleanup.skipped": {
        "ru": "  ПРОПУСК: {filename} — целевой файл не найден!",
        "en": "  SKIP: {filename} — target file not found!",
    },
    "cleanup.deleted": {
        "ru": "  Удалён: {filename}",
        "en": "  Deleted: {filename}",
    },
    "cleanup.error": {
        "ru": "  Ошибка удаления {path}: {error}",
        "en": "  Error deleting {path}: {error}",
    },
    "cleanup.done": {
        "ru": "Удалено файлов: {count}",
        "en": "Deleted files: {count}",
    },

    # ── Reprocess ──
    "reprocess.files": {
        "ru": "Reprocess: {count} файлов из organized/",
        "en": "Reprocess: {count} files from organized/",
    },
    "reprocess.single": {
        "ru": "Тест одного файла: {path}",
        "en": "Single file test: {path}",
    },
    "reprocess.first_level": {
        "ru": "Файлов первого уровня: {count}",
        "en": "First level files: {count}",
    },

    # ── State ──
    "state.reset": {
        "ru": "State сброшен",
        "en": "State reset",
    },

    # ── Errors ──
    "error.no_local_config": {
        "ru": "Не удалось загрузить config.local.json. Скопируйте config.example.json в config.local.json и отредактируйте.",
        "en": "Could not load config.local.json. Copy config.example.json to config.local.json and edit.",
    },
}

# ── API ───────────────────────────────────────────────────────────────

def t(key: str, **kwargs: object) -> str:
    """Translate a string key. Falls back to key if not found.

    Usage:
        t("run.done")                         -> "Готово." / "Done."
        t("status.file", i=1, total=10)      -> "  ── [1/10] ── test.txt"
    """
    entry = STRINGS.get(key, {})
    lang = LANGUAGE
    text = entry.get(lang) or entry.get("en") or key

    if kwargs:
        try:
            text = text.format(**{k: str(v) for k, v in kwargs.items()})
        except KeyError:
            pass  # Ignore missing format args

    return text
