"""Тесты модуля RTF."""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.rtf import RtfAnalyzer


class TestRtfExtractor:
    def test_extract_plain_text(self, tmp_path):
        """Простой RTF с текстом."""
        rtf_content = (
            r"{\rtf1\ansi\ansicpg1251\deff0"
            r"{\fonttbl{\f0\fswiss Arial;}}"
            r"\viewkind4\uc1\pard\f0\fs20 Hello World\par"
            r"Second line\par"
            r"}"
        )
        f = tmp_path / "test.rtf"
        f.write_text(rtf_content, encoding="utf-8")
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        assert "Hello World" in text
        assert "Second line" in text

    def test_extract_unicode(self, tmp_path):
        """RTF с Unicode символами \\u."""
        rtf_content = (
            r"{\rtf1\ansi\deff0"
            r"\uc1\u1055? \u1088? \u1080? \u1074? \u1077? \u1090?"
            r"}"
        )
        f = tmp_path / "test.rtf"
        f.write_text(rtf_content, encoding="utf-8")
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        # Должно содержать русские буквы (Привет)
        assert len(text) > 0

    def test_extract_with_formatting(self, tmp_path):
        """RTF с форматированием (bold, italic)."""
        rtf_content = (
            r"{\rtf1\ansi\deff0"
            r"{\fonttbl{\f0\fswiss Arial;}}"
            r"\pard\b Bold text\b0\par"
            r"\i Italic text\i0\par"
            r"\plain Normal text\par"
            r"}"
        )
        f = tmp_path / "test.rtf"
        f.write_text(rtf_content, encoding="utf-8")
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        assert "Bold text" in text
        assert "Italic text" in text
        assert "Normal text" in text

    def test_extract_hex_escape(self, tmp_path):
        """RTF с hex escapes \\'XX."""
        rtf_content = (
            r"{\rtf1\ansi\ansicpg1251\deff0"
            r"\f0\fs20 \\'cf\\'f0\\'e8\\'e2\\'e5\\'f2\par"
            r"}"
        )
        f = tmp_path / "test.rtf"
        f.write_text(rtf_content, encoding="utf-8")
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        assert len(text) > 0

    def test_extract_empty_rtf(self, tmp_path):
        """Пустой RTF."""
        rtf_content = r"{\rtf1\ansi\deff0}"
        f = tmp_path / "test.rtf"
        f.write_text(rtf_content, encoding="utf-8")
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        assert text == ""

    def test_extract_binary_garbage(self, tmp_path):
        """Файл с бинарным мусором в RTF обёртке."""
        rtf_content = r"{\rtf1\ansi\deff0" + "\x00\x01\x02" * 100 + "}"
        f = tmp_path / "test.rtf"
        f.write_bytes(rtf_content.encode("utf-8", errors="ignore"))
        
        analyzer = RtfAnalyzer()
        text = analyzer._extract_rtf_text(str(f))
        
        # Не должен упасть
        assert isinstance(text, str)


class TestRtfAnalyzer:
    def test_can_handle(self):
        analyzer = RtfAnalyzer()
        assert analyzer.can_handle("document.rtf")
        assert analyzer.can_handle("/path/to/Doc.RTF")
        assert not analyzer.can_handle("document.txt")
        assert not analyzer.can_handle("document.docx")

    def test_name(self):
        analyzer = RtfAnalyzer()
        assert analyzer.name == "rtf"

    def test_priority(self):
        analyzer = RtfAnalyzer()
        assert analyzer.priority == 72
