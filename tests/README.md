# Тесты File Organizer

## Запуск

```bash
# Все тесты
.venv/bin/python -m pytest

# Конкретный модуль
.venv/bin/python -m pytest tests/test_organizer.py

# Один тест
.venv/bin/python -m pytest tests/test_analyzer.py::TestComputeHash::test_small_file

# С coverage (нужен pytest-cov)
.venv/bin/pip install pytest-cov
.venv/bin/python -m pytest --cov=. --cov-report=html

# Только упавшие тесты (после первого прогона)
.venv/bin/python -m pytest --lf
```

## Структура

| Файл | Тестов | Что тестирует |
|------|--------|--------------|
| `test_analyzer.py` | 40 | Хеш-функции, фильтры temp-файлов, определение типов, извлечение текста |
| `test_archives.py` | 6 | Распаковка zip/tar/gz |
| `test_clients.py` | 9 | LocalAIClient (mock HTTP), SearXNGClient |
| `test_config.py` | 12 | Константы, паттерны, наборы расширений |
| `test_duplicates.py` | 5 | Обнаружение дубликатов по хешу |
| `test_metadata.py` | 19 | EXIF-парсер, аудио-метаданные, GPS, реальные файлы |
| `test_models.py` | 13 | FileInfo, ProcessingState, ImageMetadata, AudioMetadata |
| `test_organizer.py` | 10 | FileOrganizer (mock AI), dry-run, коллизии, сбор файлов |
| `test_projects.py` | 31 | Определение проектов, build-артефактов, листинг каталогов |
| `test_provenance.py` | 13 | Provenance cards (save/load/find/stats) |
| `test_relationships.py` | 4 | Поиск связанных файлов в каталоге |

## Итого: 162 теста (1 skipped)

### Unit-тесты (без внешних зависимостей)
- analyzer, config, duplicates, models, provenance, relationships

### Mock-тесты (фейковый HTTP-сервер)
- **clients.py** — LocalAIClient с mock responses (text, image, directory analysis)
- **organizer.py** — FileOrganizer с mock AI-сервером (dry-run интеграция)

### Интеграционные тесты (требуют реальные сервисы)
- **test_metadata.py:TestRealWorldFiles** — загрузка реальных EXIF-файлов из интернета (skip если нет сети)
- **test_clients.py:SearXNGClient** — реальный поиск через SearXNG (skip если недоступен)

## Добавление новых тестов

1. Создать `test_<module>.py` в `tests/`
2. Классы `Test*`, методы `test_*`
3. Использовать `tmp_path` fixture для временных файлов
4. Для HTTP-моков — использовать `mock_localai_server` или `mock_ai_server` fixtures
5. Запустить `pytest` для проверки

## Mock HTTP-сервер

```python
def test_something(self, mock_ai_server):
    MockAIHandler.responses = {
        "Qwen3.5-35B-A3B-APEX-Mini.gguf": {
            "choices": [{"message": {"content": '{"category": "Test"}'}}]
        }
    }
    organizer = FileOrganizer(source, target)
    organizer.localai.base_url = "http://127.0.0.1:18935"
    organizer.localai.text_model = "Qwen3.5-35B-A3B-APEX-Mini.gguf"
    organizer.run(dry_run=True, skip_diagnostics=True)
```
