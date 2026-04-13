# Тесты File Organizer

## Запуск

```bash
# Все тесты
.venv/bin/python -m pytest

# Конкретный модуль
.venv/bin/python -m pytest tests/test_analyzer.py

# Один тест
.venv/bin/python -m pytest tests/test_analyzer.py::TestComputeHash::test_small_file

# С coverage (нужен pytest-cov)
.venv/bin/pip install pytest-cov
.venv/bin/python -m pytest --cov=. --cov-report=html

# Только упавшие тесты (после первого прогона)
.venv/bin/python -m pytest --lf
```

## Структура

| Файл | Что тестирует |
|------|--------------|
| `test_analyzer.py` | Хеш-функции, фильтры temp-файлов, определение типов, извлечение текста |
| `test_archives.py` | Распаковка zip/tar/gz |
| `test_config.py` | Константы, паттерны, наборы расширений |
| `test_duplicates.py` | Обнаружение дубликатов по хешу |
| `test_models.py` | FileInfo, ProcessingState, ImageMetadata, AudioMetadata |
| `test_projects.py` | Определение проектов, build-артефактов, листинг каталогов |
| `test_provenance.py` | Карточная система provenance (сохранение, поиск, статистика) |
| `test_relationships.py` | Поиск связанных файлов в каталоге |

## Что НЕ тестируется

- **clients.py** — требует реальный LocalAI/SearXNG (интеграционные тесты)
- **organizer.py** — требует полный цикл с AI (интеграционные тесты)
- **metadata.py** — требует реальные файлы с EXIF/аудио-тегами

## Добавление новых тестов

1. Создать `test_<module>.py` в `tests/`
2. Классы `Test*`, методы `test_*`
3. Использовать `tmp_path` fixture для временных файлов
4. Запустить `pytest` для проверки
