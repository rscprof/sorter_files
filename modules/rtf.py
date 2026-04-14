"""Модуль: RTF документы (приоритет 72).

RTF (Rich Text Format) — формат текстовых документов Microsoft.
Извлекаем текст из RTF → AI классификация.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo

logger = logging.getLogger(__name__)


class RtfAnalyzer(BaseAnalyzer):
    """RTF документы → извлечение текста → AI классификация."""

    @property
    def priority(self) -> int:
        return 72

    @property
    def name(self) -> str:
        return "rtf"

    def can_handle(self, filepath: str) -> bool:
        from pathlib import Path
        return Path(filepath).suffix.lower().lstrip(".") == "rtf"

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        localai = existing_context.get("localai")
        existing_categories = existing_context.get("categories_context", "")
        from pathlib import Path
        p = Path(filepath)

        info = self._make_info(filepath)

        # Извлекаем текст из RTF
        text_content = self._extract_rtf_text(filepath)

        if not localai:
            info.ai_category = "Документы"
            info.ai_description = f"RTF документ: {len(text_content)} символов текста"
            return info

        # AI анализирует текст
        context = f"Имя: {p.name}, Каталог: {p.parent.name}"
        ai_result = localai.analyze_content(
            text_content=text_content,
            file_context=context,
            existing_categories=existing_categories,
        )

        if ai_result:
            info.ai_category = ai_result.get("category", "Документы")
            info.ai_subcategory = ai_result.get("subcategory", "")
            info.ai_suggested_name = ai_result.get("suggested_name", "")
            info.ai_description = ai_result.get("description", "")
            info.ai_reasoning = ai_result.get("reasoning", "")
            info.is_distributable = ai_result.get("is_distributable", False)
        else:
            info.ai_category = "Документы"
            info.ai_description = f"RTF документ: {len(text_content)} символов текста"

        return info

    def _extract_rtf_text(self, filepath: str) -> str:
        r"""Извлечь текст из RTF файла.
        
        Стековый парсер: отслеживает вложенность групп { },
        пропускает команды, сохраняет только текст.
        Обрабатывает \uN? и hex escapes.
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                rtf_content = f.read()
        except Exception:
            return ""

        text_parts = []
        i = 0
        depth = 0
        
        while i < len(rtf_content):
            ch = rtf_content[i]
            
            if ch == '{':
                depth += 1
                i += 1
                continue
            
            if ch == '}':
                depth -= 1
                i += 1
                continue
            
            if ch == '\\':
                i += 1
                if i >= len(rtf_content):
                    break
                
                cmd_char = rtf_content[i]
                
                # \uN? - Unicode символ
                if cmd_char == 'u':
                    i += 1
                    num_str = ""
                    while i < len(rtf_content) and (rtf_content[i].isdigit() or (rtf_content[i] == '-' and not num_str)):
                        num_str += rtf_content[i]
                        i += 1
                    # Пропускаем fallback-символ (?)
                    if i < len(rtf_content) and rtf_content[i] == '?':
                        i += 1
                    if num_str:
                        try:
                            text_parts.append(chr(int(num_str)))
                        except (ValueError, OverflowError):
                            pass
                    continue
                
                # \'XX - hex-символ
                if cmd_char == "'":
                    if i + 2 < len(rtf_content):
                        hex_str = rtf_content[i+1:i+3]
                        try:
                            text_parts.append(chr(int(hex_str, 16)))
                            i += 3
                            continue
                        except ValueError:
                            pass
                    i += 3
                    continue
                
                # Остальные команды — пропускаем имя (только строчные буквы)
                i += 1
                while i < len(rtf_content) and rtf_content[i].isalpha() and rtf_content[i].islower():
                    i += 1
                # Числовой параметр (может быть со знаком)
                has_param = False
                if i < len(rtf_content) and rtf_content[i] == '-':
                    has_param = True
                    i += 1
                while i < len(rtf_content) and rtf_content[i].isdigit():
                    has_param = True
                    i += 1
                # Пробел или newline-делитер (только если был параметр)
                if has_param and i < len(rtf_content) and rtf_content[i] in (' ', '\n', '\r'):
                    i += 1
                continue
            
            # Обычный символ
            if depth > 0:
                text_parts.append(ch)
            i += 1
        
        text = ''.join(text_parts)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:5000]
