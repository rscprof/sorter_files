"""Клиенты для LocalAI и SearXNG."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional

import requests

from config import LOCALAI_URL, LOCALAI_MODEL, SEARXNG_URL

logger = logging.getLogger(__name__)
DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


class LocalAIClient:
    """Клиент для LocalAI (текст + мультимодальный анализ)."""

    def __init__(self, base_url: str = LOCALAI_URL, model: str = LOCALAI_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = requests.Session()
        self.session.timeout = 180

    def analyze_content(self, text_content: str = "", image_path: str = "",
                        file_context: str = "") -> dict:
        """
        Универсальный анализ: текст, изображение или оба.
        Возвращает dict с ключами: category, subcategory, suggested_name,
        description, is_distributable, related_keywords, reasoning.
        Категории НЕ фиксированы — AI решает сам.
        """
        messages = []

        # Системный промпт
        system_msg = {
            "role": "system",
            "content": (
                "Ты — ассистент для организации файлового архива. "
                "Твоя задача — проанализировать содержимое и определить: "
                "1) КАТЕГОРИЮ (свою, не из списка — опиши своими словами, например "
                "'учебник по геометрии', 'рабочие документы колледжа', 'аудиокнига по философии'). "
                "2) ПОДКАТЕГОРИЮ (уточнение). "
                "3) Понятное ИМЯ ФАЙЛА. "
                "4) Краткое ОПИСАНИЕ. "
                "5) Является ли файл ОБЩЕДОСТУПНЫМ ДИСТРИБУТИВОМ (который можно скачать заново). "
                "6) Ключевые слова для поиска СВЯЗАННЫХ файлов. "
                "7) Краткое ОБОСНОВАНИЕ решения."
            ),
        }
        messages.append(system_msg)

        # Формируем контент
        if image_path and text_content:
            user_content = self._build_multimodal_prompt(text_content, image_path, file_context)
        elif image_path:
            user_content = self._build_image_prompt(file_context)
        elif text_content:
            user_content = self._build_text_prompt(text_content, file_context)
        else:
            return {}

        messages.append({"role": "user", "content": user_content})

        # DEBUG: логирование промпта
        if DEBUG:
            logger.debug("=" * 70)
            logger.debug("PROMPT → LocalAI:")
            if isinstance(user_content, str):
                logger.debug(user_content[:2000])
            else:
                for part in user_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        logger.debug(part["text"][:2000])
            logger.debug("=" * 70)

        try:
            logger.info(f"  → Запрос к LocalAI (model={self.model}, timeout=600s)...")
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.15,
                    "max_tokens": 600,
                },
                timeout=600,
            )
            logger.info(f"  ← Ответ получен, HTTP {resp.status_code}")
            resp.raise_for_status()

            # RAW ответ до любой обработки
            if DEBUG:
                logger.debug("=" * 70)
                logger.debug("RAW RESPONSE ← LocalAI:")
                logger.debug(resp.text[:4000])
                logger.debug("=" * 70)

            result = resp.json()
            content = result["choices"][0]["message"]["content"]

            # DEBUG: логирование ответа
            if DEBUG:
                logger.debug("=" * 70)
                logger.debug("RESPONSE ← LocalAI:")
                logger.debug(content[:2000])
                logger.debug("=" * 70)

            return self._parse_json_response(content)
        except Exception as e:
            print(f"[LocalAI] Ошибка: {e}")
            return {}

    def _build_text_prompt(self, text: str, context: str) -> str:
        return f"""Проанализируй содержимое файла.

{f"Контекст: {context}" if context else ""}

--- Начало содержимого ---
{text[:5000]}
--- Конец содержимого ---

Ответь ТОЛЬКО в JSON:
{{"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}}"""

    def _build_image_prompt(self, context: str) -> list:
        return [
            {"type": "text", "text": f"Опиши это изображение и классифицируй его.{f' Контекст: {context}' if context else ''}"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,{{B64}}"}},
            {"type": "text", "text": 'Ответь ТОЛЬКО в JSON: {"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}'},
        ]

    def _build_multimodal_prompt(self, text: str, image_path: str, context: str) -> list:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        return [
            {"type": "text", "text": f"Проанализируй файл. Извлечённый текст: {text[:3000]}{f' Контекст: {context}' if context else ''}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            {"type": "text", "text": 'Ответь ТОЛЬКО в JSON: {"category": "...", "subcategory": "...", "suggested_name": "...", "description": "...", "is_distributable": false, "related_keywords": ["..."], "reasoning": "..."}'},
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
