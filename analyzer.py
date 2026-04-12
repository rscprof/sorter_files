"""Анализ файлов: извлечение текста, хеши, определение типов."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import subprocess
from pathlib import Path

from config import ARCHIVE_EXTS, EXECUTABLE_EXTS, IMAGE_EXTS


def compute_file_hash(filepath: str, max_size: int = 100 * 1024 * 1024) -> str:
    """SHA-256 хеш. Для больших файлов — partial hash."""
    h = hashlib.sha256()
    try:
        size = os.path.getsize(filepath)
        with open(filepath, "rb") as f:
            if size <= max_size:
                while chunk := f.read(8192):
                    h.update(chunk)
            else:
                # Первые и последние 64KB
                h.update(f.read(65536))
                f.seek(size - 65536)
                h.update(f.read(65536))
        return h.hexdigest()
    except Exception as e:
        print(f"[hash] Ошибка {filepath}: {e}")
        return ""


def extract_text(filepath: str) -> str:
    """Извлечь текст из файла."""
    ext = Path(filepath).suffix.lower().lstrip(".")
    size = os.path.getsize(filepath)

    # Маленькие файлы > 10MB не читаем
    if size > 10 * 1024 * 1024:
        return _quick_signature(filepath, ext)

    try:
        if ext in ("txt", "md", "csv", "json", "yaml", "yml", "xml", "log",
                    "cfg", "ini", "conf", "py", "js", "ts", "java", "c", "cpp",
                    "h", "cs", "go", "rs", "sh", "bat", "ps1", "sql", "gpx",
                    "opml", "vcf", "ics", "toml"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:5000]

        # Office-файлы через python-docx / openpyxl / pptx
        if ext == "docx":
            return _extract_docx(filepath)
        if ext == "xlsx":
            return _extract_xlsx(filepath)
        if ext == "pptx":
            return _extract_pptx(filepath)

        if ext == "pdf":
            return _extract_pdf(filepath)

        return _quick_signature(filepath, ext)
    except Exception:
        return _quick_signature(filepath, ext)


def _extract_docx(filepath: str) -> str:
    """Текст из .docx."""
    try:
        import docx
        doc = docx.Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs if p.text)[:5000]
    except ImportError:
        # Fallback: zip-распаковка
        return _extract_office_text(filepath)
    except Exception:
        return _extract_office_text(filepath)


def _extract_xlsx(filepath: str) -> str:
    """Текст из .xlsx."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, data_only=True)
        texts = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell is not None:
                        texts.append(str(cell))
        return "\n".join(texts)[:5000]
    except ImportError:
        return _extract_office_text(filepath)
    except Exception:
        return _extract_office_text(filepath)


def _extract_pptx(filepath: str) -> str:
    """Текст из .pptx."""
    try:
        from pptx import Presentation
        prs = Presentation(filepath)
        texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        if para.text.strip():
                            texts.append(para.text)
        return "\n".join(texts)[:5000]
    except ImportError:
        return _extract_office_text(filepath)
    except Exception:
        return _extract_office_text(filepath)


def _extract_office_text(filepath: str) -> str:
    """Fallback: извлечь текст из Office XML внутри zip."""
    import zipfile
    try:
        with zipfile.ZipFile(filepath) as zf:
            text = ""
            for name in zf.namelist():
                if name.endswith(".xml") and "document" in name.lower():
                    import re
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                    # Убираем XML-теги, оставляем текст
                    clean = re.sub(r"<[^>]+>", " ", raw)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    text += clean + "\n"
            return text[:5000] if text else _quick_signature(filepath, "office")
    except Exception:
        return _quick_signature(filepath, "office")


def _extract_pdf(filepath: str) -> str:
    """Текст из PDF."""
    # pdftotext
    try:
        result = subprocess.run(
            ["pdftotext", "-l", "5", "-q", filepath, "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return result.stdout[:5000]
    except (FileNotFoundError, Exception):
        pass

    # pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            text = ""
            for page in pdf.pages[:5]:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            return text[:5000]
    except (ImportError, Exception):
        pass

    return _quick_signature(filepath, "pdf")


def _quick_signature(filepath: str, ext: str) -> str:
    """Быстрое описание для файлов без содержимого."""
    size = os.path.getsize(filepath)
    size_str = _human_size(size)
    return f"[{ext.upper()} файл, {size_str}]"


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def is_archive(filepath: str) -> bool:
    return Path(filepath).suffix.lower().lstrip(".") in ARCHIVE_EXTS


def is_executable(filepath: str) -> bool:
    return Path(filepath).suffix.lower().lstrip(".") in EXECUTABLE_EXTS


def is_image(filepath: str) -> bool:
    ext = Path(filepath).suffix.lower().lstrip(".")
    if ext in IMAGE_EXTS:
        return True
    mime, _ = mimetypes.guess_type(filepath)
    return mime is not None and mime.startswith("image/")
