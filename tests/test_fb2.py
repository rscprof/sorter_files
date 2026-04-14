"""Тесты модуля FB2."""

import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.fb2 import Fb2Analyzer


class TestFb2Extractor:
    def test_extract_valid_fb2(self, tmp_path):
        """Извлечение из валидного FB2 файла."""
        fb2_content = """<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description>
    <title-info>
      <author>
        <first-name>Иван</first-name>
        <last-name>Иванов</last-name>
      </author>
      <book-title>Тестовая книга</book-title>
      <genre>prose_contemporary</genre>
    </title-info>
  </description>
  <body>
    <section>
      <p>Первый абзац текста для тестирования.</p>
      <p>Второй абзац текста для проверки извлечения.</p>
    </section>
  </body>
</FictionBook>"""
        f = tmp_path / "test.fb2"
        f.write_text(fb2_content, encoding="utf-8")
        
        analyzer = Fb2Analyzer()
        title, authors, genre, text = analyzer._extract_fb2(str(f))
        
        assert title == "Тестовая книга"
        assert len(authors) == 1
        assert "Иванов Иван" in authors[0]
        assert genre == "prose_contemporary"
        assert "Первый абзац" in text
        assert "Второй абзац" in text

    def test_extract_no_namespace(self, tmp_path):
        """FB2 без namespace."""
        fb2_content = """<?xml version="1.0" encoding="UTF-8"?>
<FictionBook>
  <description>
    <title-info>
      <book-title>Книга без NS</book-title>
    </title-info>
  </description>
  <body>
    <section>
      <p>Текст без namespace.</p>
    </section>
  </body>
</FictionBook>"""
        f = tmp_path / "test.fb2"
        f.write_text(fb2_content, encoding="utf-8")
        
        analyzer = Fb2Analyzer()
        title, authors, genre, text = analyzer._extract_fb2(str(f))
        
        assert title == "Книга без NS"
        assert "Текст без namespace" in text

    def test_extract_invalid_xml(self, tmp_path):
        """Невалидный XML → fallback."""
        f = tmp_path / "test.fb2"
        f.write_text("not xml at all", encoding="utf-8")
        
        analyzer = Fb2Analyzer()
        title, authors, genre, text = analyzer._extract_fb2(str(f))
        
        assert title == ""
        assert text == "not xml at all"

    def test_extract_multiple_authors(self, tmp_path):
        """Несколько авторов."""
        fb2_content = """<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description>
    <title-info>
      <author>
        <first-name>Иван</first-name>
        <last-name>Петров</last-name>
      </author>
      <author>
        <first-name>Мария</first-name>
        <last-name>Сидорова</last-name>
      </author>
      <book-title>Совместная книга</book-title>
    </title-info>
  </description>
  <body>
    <section>
      <p>Текст книги.</p>
    </section>
  </body>
</FictionBook>"""
        f = tmp_path / "test.fb2"
        f.write_text(fb2_content, encoding="utf-8")
        
        analyzer = Fb2Analyzer()
        title, authors, genre, text = analyzer._extract_fb2(str(f))
        
        assert len(authors) == 2
        assert any("Петров" in a for a in authors)
        assert any("Сидорова" in a for a in authors)


class TestFb2Analyzer:
    def test_can_handle(self):
        analyzer = Fb2Analyzer()
        assert analyzer.can_handle("book.fb2")
        assert analyzer.can_handle("/path/to/Book.FB2")
        assert not analyzer.can_handle("book.txt")
        assert not analyzer.can_handle("book.epub")

    def test_name(self):
        analyzer = Fb2Analyzer()
        assert analyzer.name == "fb2"

    def test_priority(self):
        analyzer = Fb2Analyzer()
        assert analyzer.priority == 71
