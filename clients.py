"""Клиенты для LocalAI и SearXNG."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional

import requests

from config import LOCALAI_URL, LOCALAI_MODEL, LOCALAI_TEXT_MODEL, LOCALAI_VL_MODEL, SEARXNG_URL, LOCALAI_FALLBACK_MODEL, LOCALAI_FALLBACK_TEXT_MODEL, ANALYSIS_VL_MAX_PIXELS

logger = logging.getLogger(__name__)
DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


class LocalAIClient:
    """Клиент для LocalAI (текст + мультимодальный анализ)."""

    def __init__(self, base_url: str = LOCALAI_URL,
                 model: str = LOCALAI_MODEL,
                 text_model: str = LOCALAI_TEXT_MODEL,
                 vl_model: str = LOCALAI_VL_MODEL,
                 fallback_model: str = LOCALAI_FALLBACK_MODEL,
                 fallback_text_model: str = LOCALAI_FALLBACK_TEXT_MODEL,
                 max_consecutive_errors: int = 3,
                 max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.model = model  # мультимодальная (изображения)
        self.text_model = text_model  # только текст (быстрее)
        self.vl_model = vl_model  # vision-language (описание изображений)
        self.fallback_model = fallback_model  # резервная мультимодальная
        self.fallback_text_model = fallback_text_model  # резервная текстовая
        self.session = requests.Session()
        self.session.timeout = 600
        self.max_consecutive_errors = max_consecutive_errors
        self.consecutive_errors = 0  # счётчик подряд идущих ошибок
        self.max_retries = max_retries
        self._last_error_reason = None  # причина последней ошибки
    
    def _get_retry_delay(self, attempt: int) -> float:
        """
        Вычисляет задержку для повторной попытки с экспоненциальным ростом.
        Последняя задержка (для max_retries) должна быть 10 минут (600 секунд).
        
        Формула: delay = base * (multiplier ^ attempt), где last_delay = 600s
        Для max_retries=2: attempt=0 -> ~1.5s, attempt=1 -> ~15s, attempt=2 -> 600s
        """
        if self.max_retries == 0:
            return 0.0
        
        # Последняя попытка (attempt == max_retries) должна иметь задержку 600 секунд
        # Используем экспоненциальный рост: delay = base * (multiplier ^ attempt)
        # Где multiplier ^ max_retries * base = 600
        # Для плавного роста используем multiplier = 10, base = 600 / (10 ^ max_retries)
        multiplier = 10.0
        base_delay = 600.0 / (multiplier ** self.max_retries)
        delay = base_delay * (multiplier ** attempt)
        
        # Округляем до целых для читаемости
        return round(delay, 1)

    def _record_error(self, reason: str = ""):
        self.consecutive_errors += 1
        if reason:
            self._last_error_reason = reason

    def _record_success(self):
        self.consecutive_errors = 0
        self._last_error_reason = None

    def _prepare_image_for_vl(self, image_path: str) -> tuple[bytes, str]:
        """Уменьшить изображение если оно слишком большое для VL-модели."""
        import tempfile
        import struct
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size
                max_pixels = ANALYSIS_VL_MAX_PIXELS
                if w * h <= max_pixels * max_pixels:
                    with open(image_path, "rb") as f:
                        return f.read(), "jpeg"
                
                ratio = min(max_pixels / w, max_pixels / h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                resized.save(tmp.name, "JPEG", quality=85, optimize=True)
                tmp.close()
                
                with open(tmp.name, "rb") as f:
                    data = f.read()
                os.unlink(tmp.name)
                return data, "jpeg"
        except ImportError:
            with open(image_path, "rb") as f:
                return f.read(), "jpeg"
        except Exception:
            with open(image_path, "rb") as f:
                return f.read(), "jpeg"

    def is_fatal(self) -> bool:
        """True если LocalAI перестал отвечать (превышен лимит ошибок)."""
        return self.consecutive_errors >= self.max_consecutive_errors

    def fatal_message(self) -> str:
        reason_detail = f" Последняя ошибка: {self._last_error_reason}" if self._last_error_reason else ""
        return (f"LocalAI не ответил {self.consecutive_errors} раз подряд. "
                f"Сервер недоступен: {self.base_url}.{reason_detail}")

    def get_stop_reason(self) -> str:
        """Возвращает причину остановки: накопленные ошибки или пользовательский запрос."""
        if self.is_fatal():
            return self.fatal_message()
        return ""

    def describe_image(self, image_path: str, context: str = "") -> str:
        """Описать изображение через VL-модель. Возвращает текст описания."""
        import time
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                img_data, img_type = self._prepare_image_for_vl(image_path)
                img_b64 = base64.b64encode(img_data).decode()

                messages = [
                    {
                        "role": "system",
                        "content": "Опиши подробно что видно на изображении. Пиши на русском языке. Включай текст если он есть на картинке, людей, объекты, сцену."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Опиши это изображение.{f' Контекст: {context}' if context else ''}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/{img_type};base64,{img_b64}", "detail": "low"}},
                        ],
                    },
                ]

                if DEBUG:
                    print(f"\n{'='*70}")
                    print(f"VL IMAGE DESCRIBE (model={self.vl_model}, attempt={attempt+1}):")
                    print(f"{'='*70}\n")

                resp = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.vl_model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                    timeout=600,
                )
                resp.raise_for_status()
                result = resp.json()
                description = result["choices"][0]["message"]["content"].strip()

                if DEBUG:
                    print(f"\n{'='*70}")
                    print(f"VL DESCRIPTION:")
                    print(description[:1000])
                    print(f"{'='*70}\n")

                self._record_success()
                return description
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._get_retry_delay(attempt)
                    logger.warning(f"[VL Model] Попытка {attempt+1} не удалась: {e}. Повтор через {delay}s...")
                    time.sleep(delay)
                else:
                    self._record_error(str(e))
                    print(f"[VL Model] Ошибка описания изображения после {self.max_retries+1} попыток: {e} (ошибок подряд: {self.consecutive_errors})")
                    return ""
        
        self._record_error(str(last_exception))
        return ""

    def analyze_directory(self, dir_listing: str, dir_path: str = "") -> dict:
        """
        Проанализировать содержимое каталога.
        Возвращает: is_project (bool), project_name (str), 
                    files_to_delete (list), reasoning (str)
        """
        import time
        prompt = f"""Проанализируй содержимое каталога и ответь в JSON:
{{
  "is_project": true/false,
  "project_type": "тип проекта (web-app, python-lib, college-course, etc) или null",
  "project_name": "понятное имя проекта или null",
  "files_to_delete": ["список файлов/каталогов которые можно удалить — автогенерированные, node_modules, build, dist, __pycache__, стандартная инфраструктура и т.д."],
  "important_files": ["список важных файлов которые надо сохранить"],
  "reasoning": "краткое обоснование"
}}

Содержимое каталога:
{dir_listing}

Отвечай ТОЛЬКО валидным JSON."""

        last_exception = None
        # Используем fallback если основная модель не работает
        models_to_try = [self.text_model]
        if self.fallback_text_model and self.fallback_text_model != self.text_model:
            models_to_try.append(self.fallback_text_model)
        
        for attempt in range(self.max_retries + 1):
            for model in models_to_try:
                try:
                    if DEBUG:
                        print(f"\n{'='*70}")
                        print(f"DIRECTORY ANALYSIS (model={model}, attempt={attempt+1}):")
                        print(dir_listing[:1000])
                        print(f"{'='*70}\n")

                    resp = self.session.post(
                        f"{self.base_url}/chat/completions",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "max_tokens": 1024,
                        },
                        timeout=600,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Парсим JSON с улучшенной устойчивостью
                    data = self._parse_json_response(content)
                    if DEBUG:
                        print(f"DIR ANALYSIS RESULT: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    self._record_success()
                    return data
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[Directory Analysis] Модель {model} не удалась: {e}")
                    continue
            
            if attempt < self.max_retries:
                delay = self._get_retry_delay(attempt)
                logger.warning(f"[Directory Analysis] Попытка {attempt+1} не удалась. Повтор через {delay}s...")
                time.sleep(delay)
        
        self._record_error(str(last_exception))
        print(f"[Directory Analysis] Ошибка после {self.max_retries+1} попыток: {last_exception} (ошибок подряд: {self.consecutive_errors})")
        return {}

    def is_available(self, timeout: int = 30) -> bool:
        """Проверить доступность LocalAI (ping)."""
        try:
            resp = self.session.get(
                f"{self.base_url}/models",
                timeout=timeout,
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def analyze_content(self, text_content: str = "", image_path: str = "",
                        file_context: str = "", existing_categories: str = "",
                        is_pdf_scan: bool = False) -> dict:
        """
        Универсальный анализ: текст, изображение или оба.
        is_pdf_scan=True — PDF-скан: нужно распознать текст (OCR) и классифицировать.
        
        Текстовые запросы идут на text_model (быстрее),
        мультимодальные — на model (мультимодальная).
        """
        messages = []

        # Системный промпт — акцент на тематике/месте/событии
        system_msg = {
            "role": "system",
            "content": (
                "Ты — ассистент для организации файлового архива. "
                "Твоя задача — проанализировать содержимое и определить: "
                "1) КАТЕГОРИЮ — по тематике, месту или событию (НЕ по типу контента). "
                "   Например: 'Южная Корея', 'Колледж', 'Церковные документы', а не 'Финансы' или 'Презентации'. "
                "2) ПОДКАТЕГОРИЮ — тоже по теме/событию, а не по формату. "
                "   Например: 'Бюджет', 'Лекции', 'Фотографии', а не 'Таблицы' или 'Документы'. "
                "3) Понятное ИМЯ ФАЙЛА. "
                "4) Краткое ОПИСАНИЕ. "
                "5) Является ли файл ОБЩЕДОСТУПНЫМ ДИСТРИБУТИВОМ (который можно скачать заново). "
                "6) Ключевые слова для поиска СВЯЗАННЫХ файлов. "
                "7) Краткое ОБОСНОВАНИЕ решения. "
                "Если есть уже существующие категории — старайся использовать их вместо создания новых."
            ),
        }
        messages.append(system_msg)

        # Определяем какая модель нужна
        has_image = bool(image_path)
        active_model = self.model if has_image else self.text_model

        # Формируем контент
        if image_path and text_content:
            user_content = self._build_multimodal_prompt(text_content, image_path, file_context, existing_categories)
        elif image_path:
            if is_pdf_scan:
                user_content = self._build_pdf_scan_prompt(file_context, existing_categories, image_path)
            else:
                user_content = self._build_image_prompt(file_context, existing_categories, image_path)
        elif text_content:
            user_content = self._build_text_prompt(text_content, file_context, existing_categories)
        else:
            return {}

        messages.append({"role": "user", "content": user_content})

        # DEBUG: логирование промпта
        if DEBUG:
            print(f"\n{'='*70}")
            print(f"PROMPT → LocalAI (model={active_model}):")
            if isinstance(user_content, str):
                print(user_content[:3000])
            else:
                for part in user_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        print(part["text"][:3000])
            print(f"{'='*70}\n")

        try:
            logger.info(f"  → Запрос к LocalAI (model={active_model}, timeout=600s)...")
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": active_model,
                    "messages": messages,
                    "temperature": 0.15,
                    "max_tokens": 4096,
                },
                timeout=600,
            )
            logger.info(f"  ← Ответ получен, HTTP {resp.status_code}")
            resp.raise_for_status()

            # RAW ответ до любой обработки
            if DEBUG:
                print(f"\n{'='*70}")
                print(f"RAW RESPONSE ← LocalAI:")
                print(resp.text[:4000])
                print(f"{'='*70}\n")

            result = resp.json()
            content = result["choices"][0]["message"]["content"]

            # Успех — сбрасываем счётчик ошибок
            self._record_success()

            # DEBUG: распарсенный ответ
            if DEBUG:
                print(f"\n{'='*70}")
                print(f"PARSED RESPONSE ← LocalAI:")
                print(content[:2000])
                print(f"{'='*70}\n")

            return self._parse_json_response(content)
        except requests.exceptions.Timeout as e:
            self._record_error("Timeout")
            logger.warning(f"[LocalAI] Таймаут (>600с), пропуск AI-анализа (ошибок подряд: {self.consecutive_errors})")
            return {}
        except Exception as e:
            self._record_error(str(e))
            logger.warning(f"[LocalAI] Ошибка: {e} (ошибок подряд: {self.consecutive_errors})")
            return {}

    def transcribe_audio(self, filepath: str, model: str = "whisperx-tiny") -> str:
        """Транскрибировать аудио через Whisper-модель в LocalAI."""
        import os
        import time
        
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                fname = os.path.basename(filepath)
                with open(filepath, "rb") as f:
                    files = {"file": (fname, f, "application/octet-stream")}
                    data = {"model": model}
                    resp = self.session.post(
                        f"{self.base_url}/audio/transcriptions",
                        files=files,
                        data=data,
                        timeout=600,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    self._record_success()
                    return result.get("text", "")
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._get_retry_delay(attempt)
                    logger.warning(f"[LocalAI] Таймаут транскрипции {filepath}, попытка {attempt+1}. Повтор через {delay}s...")
                    time.sleep(delay)
                else:
                    self._record_error("Timeout")
                    print(f"[LocalAI] Таймаут транскрипции {filepath} после {self.max_retries+1} попыток (ошибок подряд: {self.consecutive_errors})")
                    return ""
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._get_retry_delay(attempt)
                    logger.warning(f"[LocalAI] Ошибка транскрипции {filepath}, попытка {attempt+1}: {e}. Повтор через {delay}s...")
                    time.sleep(delay)
                else:
                    self._record_error(str(e))
                    print(f"[LocalAI] Ошибка транскрипции {filepath} после {self.max_retries+1} попыток: {e} (ошибок подряд: {self.consecutive_errors})")
                    return ""
        
        self._record_error(str(last_exception))
        return ""

    def _build_text_prompt(self, text: str, context: str, existing_categories: str = "") -> str:
        cats = existing_categories + "\n" if existing_categories else ""
        return f"""Проанализируй содержимое файла.

{f"Контекст: {context}" if context else ""}
{cats}
--- Начало содержимого ---
{text[:5000]}
--- Конец содержимого ---

Ответь ТОЛЬКО валидным JSON без markdown-оформления, без ```json, без текста — просто чистый JSON:
{{"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}}"""

    def _build_image_prompt(self, context: str, existing_categories: str = "", image_path: str = "") -> list:
        cats = existing_categories + "\n" if existing_categories else ""
        img_b64 = ""
        if image_path:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
        return [
            {"type": "text", "text": f"Опиши это изображение и классифицируй его.{f' Контекст: {context}' if context else ''}\n{cats}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
            {"type": "text", "text": 'Ответь ТОЛЬКО валидным JSON без markdown-оформления, без ```json: {"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}'},
        ]

    def _build_pdf_scan_prompt(self, context: str, existing_categories: str = "", image_path: str = "") -> list:
        """Промпт для PDF-скана: нужно распознать текст (OCR) и классифицировать."""
        cats = existing_categories + "\n" if existing_categories else ""
        img_b64 = ""
        if image_path:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
        return [
            {"type": "text", "text": (
                f"Это скан документа (PDF→изображение). "
                f"Распознай весь видимый текст (OCR), определи тематику и классифицируй документ. "
                f"{f'Контекст: {context}' if context else ''}\n{cats}"
            )},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
            {"type": "text", "text": (
                'Ответь ТОЛЬКО валидным JSON без markdown-оформления, без ```json: '
                '{"category": "...", "subcategory": "...", "suggested_name": "...", '
                '"description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}'
            )},
        ]

    def _build_multimodal_prompt(self, text: str, image_path: str, context: str, existing_categories: str = "") -> list:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        cats = existing_categories + "\n" if existing_categories else ""
        return [
            {"type": "text", "text": f"Проанализируй файл. Извлечённый текст: {text[:3000]}{f' Контекст: {context}' if context else ''}\n{cats}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
            {"type": "text", "text": 'Ответь ТОЛЬКО валидным JSON без markdown-оформления, без ```json: {"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}'},
        ]

    def _parse_json_response(self, content: str) -> dict:
        """
        Парсит JSON из ответа LLM с повышенной устойчивостью к некорректному формату.
        
        Стратегии:
        1. Поиск JSON между { и } с помощью regex (сначала жадный, потом не-жадный)
        2. Попытка исправить распространённые ошибки (лишние запятые, незакрытые кавычки)
        3. Извлечение частичных данных даже при неполном JSON
        """
        if not content or not isinstance(content, str):
            return {"category": "неразобранное", "reasoning": "Пустой или некорректный ответ"}
        
        # Стратегия 1: Поиск всех потенциальных JSON-объектов
        # Сначала жадный поиск (от первого { до последнего })
        json_patterns = [
            r'\{[\s\S]*\}',   # Жадный поиск - приоритет 1
            r'\{[\s\S]*?\}',  # Не-жадный поиск - приоритет 2
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content)
            # Сортируем по длине - сначала пробуем более длинные совпадения
            matches.sort(key=len, reverse=True)
            for match in matches:
                # Пробуем распарсить как есть
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    pass
                
                # Стратегия 2: Исправление распространённых ошибок JSON
                fixed_match = self._fix_common_json_errors(match)
                try:
                    return json.loads(fixed_match)
                except json.JSONDecodeError:
                    pass
        
        # Стратегия 3: Поиск по ключевым полям и сборка объекта вручную
        parsed = self._extract_fields_manually(content)
        if parsed:
            return parsed
        
        return {"category": "неразобранное", "reasoning": f"Не удалось распарсить ответ: {content[:300]}"}
    
    def _fix_common_json_errors(self, json_str: str) -> str:
        """
        Исправляет распространённые ошибки в JSON:
        - Лишние запятые перед закрывающими скобками
        - Незакрытые кавычки
        - Одинарные кавычки вместо двойных
        - Отсутствующие закрывающие скобки
        """
        import re
        
        result = json_str
        
        # 1. Удаляем trailing commas перед } или ]
        result = re.sub(r',(\s*[}\]])', r'\1', result)
        
        # 2. Добавляем недостающие закрывающие скобки
        open_braces = result.count('{')
        close_braces = result.count('}')
        open_brackets = result.count('[')
        close_brackets = result.count(']')
        
        if close_braces < open_braces:
            result += '}' * (open_braces - close_braces)
        if close_brackets < open_brackets:
            result += ']' * (open_brackets - close_brackets)
        
        return result
    
    def _extract_fields_manually(self, content: str) -> Optional[dict]:
        """
        Пытается извлечь известные поля из ответа вручную, если JSON не парсится.
        """
        fields_to_extract = [
            'category', 'subcategory', 'suggested_name', 'description',
            'is_distributable', 'is_project', 'project_type', 'project_name',
            'files_to_delete', 'important_files', 'related_keywords', 'reasoning'
        ]
        
        extracted = {}
        
        for field in fields_to_extract:
            # Паттерн для поиска "field": "value" или "field": [...]
            patterns = [
                rf'"{field}"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',  # Строковое значение в JSON
                rf'"{field}"\s*:\s*(true|false)',  # Булево значение в JSON
                rf'"{field}"\s*:\s*\[([\s\S]*?)\]',  # Массив в JSON
                rf'"{field}"\s*:\s*(-?\d+(?:\.\d+)?)',  # Числовое значение в JSON
                # Паттерны для свободного текста (без JSON-формата)
                rf'(?:^|[\s,.]){field}\s*[=:]\s*"([^"]+)"',  # field = "value" или field: "value"
                rf'(?:^|[\s,.]){field}\s*[=:]\s*([A-Za-zА-Яа-я][A-Za-zА-Яа-я\s\-_]*?)(?:\.|,|$|\n)',  # field = value (до точки/запятой, с поддержкой кириллицы)
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.UNICODE)
                if match:
                    value = match.group(1)
                    
                    # Обработка массивов
                    if field in ['files_to_delete', 'important_files', 'related_keywords']:
                        # Пытаемся распарсить элементы массива
                        items = re.findall(r'"([^"]*)"', match.group(0))
                        if items:
                            extracted[field] = items
                            break
                    
                    # Обработка булевых значений
                    elif field == 'is_distributable' or field == 'is_project':
                        extracted[field] = value.lower() == 'true'
                        break
                    
                    # Строковые значения
                    else:
                        extracted[field] = value.strip()
                        break
        
        # Возвращаем только если нашли хотя бы одно поле
        if extracted:
            return extracted
        
        return None


class SearXNGClient:
    """Клиент для SearXNG."""

    def __init__(self, base_url: str = SEARXNG_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 30

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            resp = self.session.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json", "language": "ru", "categories": "general,files"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception as e:
            print(f"[SearXNG] Ошибка поиска: {e}")
            return []

    def is_known_distributable(self, filename: str) -> bool:
        """Проверить, является ли файл общедоступным дистрибутивом.
        
        Поддерживает проверку для:
        - .deb пакетов
        - Архивов с исходниками (.tar.gz, .tar.bz2, .tgz и т.п.)
        - Других исполняемых дистрибутивов
        """
        # Deb-файлы часто публично доступны — проверяем особенно тщательно
        if filename.endswith(".deb"):
            pkg_name = filename.rsplit("_", 1)[0].rsplit("-", 1)[0]
            queries = [
                f'"{filename}" download',
                f'"{pkg_name}" .deb package',
                f'apt {pkg_name} download',
                f'"{filename}" debian repository',
            ]
        # Архивы с исходниками (tarball) — типичный формат распространения ПО
        elif any(filename.endswith(ext) for ext in [".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"]):
            # Извлекаем имя проекта из имени файла (например, project-1.0.tar.gz -> project)
            base_name = filename.split(".tar.")[0] if ".tar." in filename else filename.split(".t")[0]
            # Удаляем версию из имени (project-1.0 -> project)
            proj_name = base_name.rsplit("-", 1)[0] if "-" in base_name else base_name
            queries = [
                f'"{filename}" source tarball',
                f'"{base_name}" source code',
                f'"{proj_name}" github release',
                f'"{filename}" download',
            ]
        else:
            queries = [f'"{filename}" download free', f'"{filename}" скачать']

        for query in queries:
            results = self.search(query, max_results=5)
            for r in results:
                title = (r.get("title", "") + " " + r.get("url", "")).lower()
                if any(kw in title for kw in ["download", "скачать", "release", "installer", "setup", "official",
                                               "repository", "package", "apt", "debian", "ubuntu", "github", "source", "tarball"]):
                    return True
        return False
