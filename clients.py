"""Клиенты для LocalAI и SearXNG."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional

import requests

from config import LOCALAI_URL, LOCALAI_MODEL, LOCALAI_TEXT_MODEL, LOCALAI_VL_MODEL, SEARXNG_URL

logger = logging.getLogger(__name__)
DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


class LocalAIClient:
    """Клиент для LocalAI (текст + мультимодальный анализ)."""

    def __init__(self, base_url: str = LOCALAI_URL,
                 model: str = LOCALAI_MODEL,
                 text_model: str = LOCALAI_TEXT_MODEL,
                 vl_model: str = LOCALAI_VL_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model  # мультимодальная (изображения)
        self.text_model = text_model  # только текст (быстрее)
        self.vl_model = vl_model  # vision-language (описание изображений)
        self.session = requests.Session()
        self.session.timeout = 180

    def describe_image(self, image_path: str, context: str = "") -> str:
        """Описать изображение через VL-модель. Возвращает текст описания."""
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
                print(f"VL IMAGE DESCRIBE (model={self.vl_model}):")
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

            return description
        except Exception as e:
            print(f"[VL Model] Ошибка описания изображения: {e}")
            return ""

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

            # DEBUG: распарсенный ответ
            if DEBUG:
                print(f"\n{'='*70}")
                print(f"PARSED RESPONSE ← LocalAI:")
                print(content[:2000])
                print(f"{'='*70}\n")

            return self._parse_json_response(content)
        except Exception as e:
            print(f"[LocalAI] Ошибка: {e}")
            return {}

    def transcribe_audio(self, filepath: str, model: str = "whisperx-tiny") -> str:
        """Транскрибировать аудио через Whisper-модель в LocalAI."""
        import os
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
                return result.get("text", "")
        except requests.exceptions.Timeout:
            print(f"[LocalAI] Таймаут транскрипции {filepath}")
            return ""
        except Exception as e:
            print(f"[LocalAI] Ошибка транскрипции {filepath}: {e}")
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
        """Проверить, является ли файл общедоступным дистрибутивом."""
        queries = [f'"{filename}" download free', f'"{filename}" скачать']
        for query in queries:
            results = self.search(query, max_results=3)
            for r in results:
                title = (r.get("title", "") + " " + r.get("url", "")).lower()
                if any(kw in title for kw in ["download", "скачать", "release", "installer", "setup", "official"]):
                    return True
        return False
