"""Клиенты для LocalAI и SearXNG."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional

import requests

from config import LOCALAI_URL, LOCALAI_MODEL, LOCALAI_TEXT_MODEL, LOCALAI_VL_MODEL, SEARXNG_URL, LOCALAI_FALLBACK_MODEL, LOCALAI_FALLBACK_TEXT_MODEL

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
                 max_retries: int = 2,
                 retry_delay: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.model = model  # мультимодальная (изображения)
        self.text_model = text_model  # только текст (быстрее)
        self.vl_model = vl_model  # vision-language (описание изображений)
        self.fallback_model = fallback_model  # резервная мультимодальная
        self.fallback_text_model = fallback_text_model  # резервная текстовая
        self.session = requests.Session()
        self.session.timeout = 180
        self.max_consecutive_errors = max_consecutive_errors
        self.consecutive_errors = 0  # счётчик подряд идущих ошибок
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_error_reason = None  # причина последней ошибки

    def _record_error(self, reason: str = ""):
        self.consecutive_errors += 1
        if reason:
            self._last_error_reason = reason

    def _record_success(self):
        self.consecutive_errors = 0
        self._last_error_reason = None

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
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()

                messages = [
                    {
                        "role": "system",
                        "content": "Опиши подробно что видно на изображении. Пиши на русском языке. Включай текст если он есть на картинке, людей, объекты, сцену."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Опиши это изображение.{f' Контекст: {context}' if context else ''}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
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
                    timeout=120,
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
                    logger.warning(f"[VL Model] Попытка {attempt+1} не удалась: {e}. Повтор через {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
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
                        timeout=120,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Парсим JSON
                    import re
                    json_match = re.search(r"\{[\s\S]*\}", content)
                    if json_match:
                        data = json.loads(json_match.group())
                        if DEBUG:
                            print(f"DIR ANALYSIS RESULT: {json.dumps(data, indent=2, ensure_ascii=False)}")
                        self._record_success()
                        return data
                    return {}
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[Directory Analysis] Модель {model} не удалась: {e}")
                    continue
            
            if attempt < self.max_retries:
                logger.warning(f"[Directory Analysis] Попытка {attempt+1} не удалась. Повтор через {self.retry_delay}s...")
                time.sleep(self.retry_delay)
        
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
                        timeout=300,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    self._record_success()
                    return result.get("text", "")
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(f"[LocalAI] Таймаут транскрипции {filepath}, попытка {attempt+1}. Повтор через {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    self._record_error("Timeout")
                    print(f"[LocalAI] Таймаут транскрипции {filepath} после {self.max_retries+1} попыток (ошибок подряд: {self.consecutive_errors})")
                    return ""
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(f"[LocalAI] Ошибка транскрипции {filepath}, попытка {attempt+1}: {e}. Повтор через {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
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
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"category": "неразобранное", "reasoning": f"Не удалось распарсить ответ: {content[:200]}"}


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
