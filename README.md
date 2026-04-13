# File Organizer

**AI-powered file organization tool** — анализирует содержимое файлов через LocalAI, классифицирует, переименовывает и перемещает в структурированную библиотеку.

---

## 🇷🇺 Русский

### Возможности

- **Мультимодальный анализ** — текст, изображения (через VL-модель), аудио (whisper транскрипция), видео (ключевые кадры + речь)
- **Динамические категории** — AI определяет категории по содержимому, без жёсткого списка
- **Распаковка архивов** — zip, tar, 7z, rar с рекурсивной обработкой содержимого
- **Обнаружение дубликатов** — по SHA-256 хешу с контекстным решением
- **Build-артефакты** — автоматическое определение проектов и фильтрация артефактов сборки
- **Provenance** — карточная система отслеживания происхождения файлов с возможностью восстановления
- **Graceful shutdown** — Ctrl-C завершает после текущего файла, двойной Ctrl-C — немедленно
- **Модульная архитектура** — 9 независимых анализаторов с priority order
- **162 теста** — unit, mock, интеграционные

### Установка

```bash
# Клонируйте репозиторий
git clone <repo>
cd sorter

# Создайте виртуальное окружение
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Скопируйте конфиг
cp config.example.json config.local.json
# Отредактируйте config.local.json под вашу среду
```

### Использование

```bash
# Dry-run (без изменений)
.venv/bin/python organizer.py --dry-run --limit 10

# Боевой режим
.venv/bin/python organizer.py --first-level-only --limit 50

# Повторная обработка
.venv/bin/python organizer.py --reprocess --limit 10

# Восстановление каталога
.venv/bin/python organizer.py --restore-dir ~/nextcloud/files/old_folder

# Поиск файла
.venv/bin/python organizer.py --find-file "report.xlsx"

# Статистика provenance
.venv/bin/python organizer.py --provenance-stats

# Debug режим
.venv/bin/python organizer.py --single-file ~/path/to/file.pdf --debug
```

### Конфигурация

Все настройки в `config.local.json`:

| Параметр | Описание | По умолчанию |
|----------|----------|-------------|
| `language` | Язык интерфейса (ru/en) | `ru` |
| `localai.url` | Адрес LocalAI API | `http://localhost:11434/v1` |
| `localai.model` | Мультимодальная модель | `qwen3.5-35b-a3b-apex` |
| `localai.text_model` | Текстовая модель | `Qwen3.5-35B-A3B-APEX-Mini.gguf` |
| `localai.vl_model` | Vision-language модель | `qwen3-vl-4b-instruct` |
| `searxng.url` | Адрес SearXNG | `http://localhost:8080` |
| `paths.source` | Исходный каталог | `~/nextcloud/files` |
| `paths.target` | Целевой каталог | `{source}/organized` |

Переменные окружения (`FILE_ORGANIZER_*`) имеют приоритет над конфиг-файлом.

### Архитектура

```
sorter/
├── config.py            # Загрузчик конфигурации
├── config.local.json    # Локальные настройки (gitignored)
├── config.example.json  # Пример настроек
├── localization.py      # i18n (RU/EN)
├── models.py            # Dataclasses (FileInfo, ProcessingState)
├── provenance.py        # Карточная система provenance
├── clients.py           # LocalAI + SearXNG клиенты
├── analyzer.py          # Извлечение текста, хеши, типы
├── metadata.py          # EXIF + аудио-метаданные
├── archives.py          # Распаковка архивов
├── projects.py          # Определение проектов и build-артефактов
├── duplicates.py        # Обнаружение дубликатов
├── relationships.py     # Поиск связанных файлов
├── diagnostics.py       # Диагностика зависимостей
├── organizer.py         # Orchestrator + CLI
├── modules/             # Модули-анализаторы
│   ├── build_artifacts.py   # priority 10
│   ├── distributables.py    # priority 20
│   ├── archives.py          # priority 30
│   ├── audio.py             # priority 40
│   ├── video.py             # priority 45
│   ├── pdf_scans.py         # priority 50
│   ├── images.py            # priority 60
│   ├── documents.py         # priority 70
│   └── fallback.py          # priority 999
└── tests/               # 162 теста
```

### Анализаторы

Каждый файл проходит через цепочку анализаторов (по priority). Первый подходящий обрабатывает файл:

1. **build_artifacts** — определяет файлы сборки в проектах
2. **distributables** — общедоступные дистрибутивы (через SearXNG)
3. **archives** — архивы для распаковки
4. **audio** — аудио → whisper транскрипция → AI классификация
5. **video** — видео → метаданные → ключевые кадры → речь → AI
6. **pdf_scans** — PDF-сканы → JPEG → VL описание → AI классификация
7. **images** — изображения → JPEG конвертация → VL описание → AI
8. **documents** — документы с текстом → AI классификация
9. **fallback** — всё остальное по расширению

### Лицензия

MIT

---

## 🇬🇧 English

### Features

- **Multimodal analysis** — text, images (via VL model), audio (whisper transcription), video (keyframes + speech)
- **Dynamic categories** — AI determines categories by content, no hardcoded list
- **Archive extraction** — zip, tar, 7z, rar with recursive content processing
- **Duplicate detection** — by SHA-256 hash with contextual decision
- **Build artifacts** — automatic project detection and build artifact filtering
- **Provenance** — card-based file origin tracking with restore capability
- **Graceful shutdown** — Ctrl-C finishes current file, double Ctrl-C — immediate
- **Modular architecture** — 9 independent analyzers with priority order
- **162 tests** — unit, mock, integration

### Installation

```bash
git clone <repo>
cd sorter

python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.json config.local.json
# Edit config.local.json for your environment
```

### Usage

```bash
# Dry-run (no changes)
.venv/bin/python organizer.py --dry-run --limit 10

# Live mode
.venv/bin/python organizer.py --first-level-only --limit 50

# Reprocess organized files
.venv/bin/python organizer.py --reprocess --limit 10

# Restore directory
.venv/bin/python organizer.py --restore-dir ~/my_files/old_folder

# Find file
.venv/bin/python organizer.py --find-file "report.xlsx"

# Provenance stats
.venv/bin/python organizer.py --provenance-stats

# Debug mode
.venv/bin/python organizer.py --single-file ~/path/to/file.pdf --debug
```

### Configuration

All settings in `config.local.json`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `language` | UI language (ru/en) | `ru` |
| `localai.url` | LocalAI API URL | `http://localhost:11434/v1` |
| `localai.model` | Multimodal model | `qwen3.5-35b-a3b-apex` |
| `localai.text_model` | Text-only model | `Qwen3.5-35B-A3B-APEX-Mini.gguf` |
| `localai.vl_model` | Vision-language model | `qwen3-vl-4b-instruct` |
| `searxng.url` | SearXNG URL | `http://localhost:8080` |
| `paths.source` | Source directory | `~/nextcloud/files` |
| `paths.target` | Target directory | `{source}/organized` |

Environment variables (`FILE_ORGANIZER_*`) override config file.

### Architecture

See the Russian section for the full directory structure.

### Analyzers

Each file goes through the analyzer chain (by priority). First matching analyzer processes it:

1. **build_artifacts** — build files in projects
2. **distributables** — public distributions (via SearXNG)
3. **archives** — archives for extraction
4. **audio** — audio → whisper transcription → AI classification
5. **video** — video → metadata → keyframes → speech → AI
6. **pdf_scans** — PDF scans → JPEG → VL description → AI classification
7. **images** — images → JPEG conversion → VL description → AI
8. **documents** — text documents → AI classification
9. **fallback** — everything else by extension

### License

MIT
