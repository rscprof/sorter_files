"""Модуль: FB2 электронные книги (приоритет 71).

FB2 — XML-based формат электронных книг.
Извлекаем метаданные и текст → AI классификация.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo

logger = logging.getLogger(__name__)

# XML namespace для FB2
FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"


class Fb2Analyzer(BaseAnalyzer):
    """FB2 электронные книги → текст + метаданные → AI классификация."""

    @property
    def priority(self) -> int:
        return 71

    @property
    def name(self) -> str:
        return "fb2"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        return Path(filepath).suffix.lower().lstrip(".") == "fb2"

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)

        # Извлекаем метаданные и текст
        title, authors, genre, text_content = self._extract_fb2(filepath)

        if not localai:
            info.ai_category = "Книги"
            info.ai_description = f"FB2: {title or 'без названия'}"
            return info

        # Формируем контекст для AI
        context_parts = [f"Имя: {p.name}"]
        if authors:
            context_parts.append(f"Авторы: {', '.join(authors[:3])}")
        if genre:
            context_parts.append(f"Жанр: {genre}")
        if title:
            context_parts.append(f"Название: {title}")

        context = ", ".join(context_parts)

        # AI анализирует текст + метаданные
        ai_result = localai.analyze_content(
            text_content=text_content,
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "Книги")
            info.ai_subcategory = ai_result.get("subcategory", genre or "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            # Fallback: используем метаданные
            info.ai_category = "Книги"
            info.ai_subcategory = genre or ""
            info.ai_description = f"FB2 книга: {title or p.stem}"
            if authors:
                info.ai_description += f", авторы: {', '.join(authors[:2])}"

        return info

    def _extract_fb2(self, filepath: str) -> tuple[str, list[str], str, str]:
        """Извлечь метаданные и текст из FB2.
        
        Возвращает: (title, authors, genre, text_content)
        """
        title = ""
        authors = []
        genre = ""
        text_parts = []

        try:
            # FB2 может иметь namespace или нет
            tree = ET.parse(filepath)
            root = tree.getroot()

            # Определяем namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            # Извлекаем метаданные из <description>
            desc = root.find(f"{ns}description")
            if desc is not None:
                # Title-info
                title_info = desc.find(f"{ns}title-info")
                if title_info is not None:
                    # Название
                    book_title = title_info.find(f"{ns}book-title")
                    if book_title is not None and book_title.text:
                        title = book_title.text.strip()

                    # Авторы
                    for author_elem in title_info.findall(f"{ns}author"):
                        first = author_elem.findtext(f"{ns}first-name", "")
                        last = author_elem.findtext(f"{ns}last-name", "")
                        middle = author_elem.findtext(f"{ns}middle-name", "")
                        name = " ".join(filter(None, [last, first, middle]))
                        if name:
                            authors.append(name)

                    # Жанр
                    genre_elem = title_info.find(f"{ns}genre")
                    if genre_elem is not None and genre_elem.text:
                        genre = genre_elem.text.strip()

            # Извлекаем текст (первые несколько абзацев для AI)
            body = root.find(f"{ns}body")
            if body is not None:
                for section in body.findall(f"{ns}section"):
                    for para in section.findall(f"{ns}p"):
                        if para.text:
                            text_parts.append(para.text.strip())
                        # Ограничиваем объём текста
                        if len(text_parts) >= 50:
                            break
                    if len(text_parts) >= 50:
                        break

        except ET.ParseError as e:
            logger.debug(f"FB2 parse error: {e}")
            # Fallback: читаем как plain text
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()[:5000]
                return "", [], "", text
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"FB2 extract error: {e}")

        text_content = "\n".join(text_parts)[:5000]
        return title, authors, genre, text_content
