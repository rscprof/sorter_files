"""Диагностика зависимостей: сервисы, утилиты, пакеты."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests

from config import (
    LOCALAI_URL, LOCALAI_MODEL, LOCALAI_TEXT_MODEL, LOCALAI_VL_MODEL,
    SEARXNG_URL, SOURCE_DIR, TARGET_DIR, LANGUAGE,
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    optional: bool = False  # Опциональная зависимость


@dataclass
class Diagnostics:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok or c.optional for c in self.checks)

    @property
    def optional_missing(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok and c.optional]

    @property
    def required_missing(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok and not c.optional]

    def add(self, name: str, ok: bool, detail: str = "", optional: bool = False):
        self.checks.append(CheckResult(name, ok, detail, optional))

    def report(self) -> str:
        lines = ["─" * 60, "File Organizer — Диагностика зависимостей", "─" * 60]

        # Группируем по секциям
        sections: dict[str, list[CheckResult]] = {}
        for c in self.checks:
            # Определяем секцию по имени
            section = "Другое"
            if any(k in c.name.lower() for k in ["localai", "модель", "vl"]):
                section = "LocalAI"
            elif "searxng" in c.name.lower():
                section = "SearXNG"
            elif "утилита" in c.name.lower():
                section = "Утилиты"
            elif "pip" in c.name.lower():
                section = "Python-пакеты"
            elif "конфиг" in c.name.lower():
                section = "Конфигурация"
            sections.setdefault(section, []).append(c)

        order = ["LocalAI", "SearXNG", "Утилиты", "Python-пакеты", "Конфигурация", "Другое"]
        for section in order:
            items = sections.get(section, [])
            if not items:
                continue
            lines.append(f"\n  [{section}]")
            for c in items:
                if c.ok:
                    status = "✓"
                elif c.optional:
                    status = "○"  # optional missing
                else:
                    status = "✗"
                detail = f" — {c.detail}" if c.detail else ""
                opt_tag = " (опционально)" if c.optional and not c.ok else ""
                lines.append(f"    {status} {c.name}{detail}{opt_tag}")

        lines.append("\n" + "─" * 60)

        if self.all_ok:
            if self.optional_missing:
                lines.append(
                    f"Всё работает. Опционально не найдено: {', '.join(self.optional_missing)}"
                )
            else:
                lines.append("Всё в порядке ✓")
        else:
            lines.append(f"НЕ ГОТОВО: {', '.join(self.required_missing)}")
            lines.append("Устраните проблемы и повторите запуск.")

        return "\n".join(lines)


def run_diagnostics() -> Diagnostics:
    """Полная проверка всех зависимостей."""
    diag = Diagnostics()

    # ── Информация о среде ──
    diag.add(
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        True,
        sys.executable,
    )
    diag.add(
        "Язык интерфейса",
        True,
        f"{LANGUAGE} (ru/en)",
    )
    diag.add(
        "Исходный каталог",
        Path(SOURCE_DIR).exists(),
        SOURCE_DIR if Path(SOURCE_DIR).exists() else "не существует",
    )

    # ── LocalAI ──
    try:
        r = requests.get(f"{LOCALAI_URL.rstrip('/')}/models", timeout=15)
        if r.status_code == 200:
            diag.add("LocalAI API", True, LOCALAI_URL)
            models_data = r.json().get("data", [])
            model_ids = [m.get("id", "") for m in models_data]

            # Основная модель
            diag.add(
                f"  модель: {LOCALAI_MODEL}",
                _in_list(LOCALAI_MODEL, model_ids),
                _model_hint(LOCALAI_MODEL, model_ids),
            )
            # Текстовая модель
            diag.add(
                f"  текст: {LOCALAI_TEXT_MODEL}",
                _in_list(LOCALAI_TEXT_MODEL, model_ids),
                _model_hint(LOCALAI_TEXT_MODEL, model_ids),
            )
            # VL модель
            diag.add(
                f"  vision: {LOCALAI_VL_MODEL}",
                _in_list(LOCALAI_VL_MODEL, model_ids),
                _model_hint(LOCALAI_VL_MODEL, model_ids),
            )
        else:
            diag.add("LocalAI API", False, f"HTTP {r.status_code}")
    except requests.exceptions.ConnectionError:
        diag.add("LocalAI API", False, f"недоступен ({LOCALAI_URL})")
    except Exception as e:
        diag.add("LocalAI API", False, str(e)[:100])

    # ── SearXNG ──
    try:
        r = requests.get(
            f"{SEARXNG_URL.rstrip('/')}/search",
            params={"q": "test", "format": "json"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("results", []))
            diag.add("SearXNG", True, f"{n} результатов на 'test'")
        else:
            diag.add("SearXNG", False, f"HTTP {r.status_code}")
    except requests.exceptions.ConnectionError:
        diag.add("SearXNG", False, f"недоступен ({SEARXNG_URL})", optional=True)
    except Exception as e:
        diag.add("SearXNG", False, str(e)[:100], optional=True)

    # ── Обязательные утилиты ──
    _check_tool(diag, "pdftotext", required=True, hint="poppler-utils / nix-shell")
    _check_tool(diag, "7z", required=True, hint="p7zip")
    _check_tool(diag, "ffmpeg", required=True, hint="для видео/аудио")
    _check_tool(diag, "ffprobe", required=True, hint="входит в ffmpeg")

    # ── Опциональные утилиты ──
    _check_tool(diag, "unrar", optional=True, hint="для RAR архивов")
    _check_tool(diag, "tar", optional=True)
    _check_tool(diag, "djvutxt", optional=True, hint="для DJVU файлов (djvulibre)")
    _check_tool(diag, "antiword", optional=True, hint="для .doc файлов")
    _check_tool(diag, "catdoc", optional=True, hint="для .doc файлов")
    _check_tool(diag, "exiftool", optional=True, hint="расширенные метаданные")

    # ── Python-пакеты ──
    _check_package(diag, "requests", required=True)
    _check_package(diag, "PIL", required=True, display="Pillow")
    _check_package(diag, "pytest", optional=True)

    # Опциональные пакеты для документов
    _check_package(diag, "pdfplumber", optional=True, hint="извлечение текста из PDF")
    _check_package(diag, "docx", optional=True, display="python-docx", hint="извлечение текста из DOCX")
    _check_package(diag, "openpyxl", optional=True, hint="извлечение текста из XLSX")
    _check_package(diag, "pptx", optional=True, display="python-pptx", hint="извлечение текста из PPTX")
    _check_package(diag, "mutagen", optional=True, hint="аудио-метаданные")

    # ── Конфигурация ──
    config_local = Path(__file__).parent / "config.local.json"
    diag.add(
        "config.local.json",
        config_local.exists(),
        "найден" if config_local.exists() else "используются дефолты (скопируйте config.example.json)",
        optional=True,
    )

    return diag


def _in_list(model: str, available: list[str]) -> bool:
    """Проверить наличие модели (точное или частичное совпадение)."""
    if model in available:
        return True
    for m in available:
        if model.lower() in m.lower() or m.lower() in model.lower():
            return True
    return False


def _model_hint(model: str, available: list[str]) -> str:
    """Подсказка если модель не найдена."""
    if not available:
        return "список моделей пуст"
    if _in_list(model, available):
        # Найдена частично
        for m in available:
            if model.lower() in m.lower() or m.lower() in model.lower():
                return f"найдена как {m}"
        return ""
    return f"доступны: {', '.join(available[:4])}{'...' if len(available) > 4 else ''}"


def _check_tool(diag: Diagnostics, name: str, required: bool = False,
                optional: bool = False, hint: str = "", display: str = ""):
    """Проверить утилиту."""
    label = display or name
    found = shutil.which(name) is not None
    detail = ""
    if found:
        detail = shutil.which(name) or ""
    elif hint:
        detail = hint
    opt = optional or not required
    diag.add(f"утилита {label}", found, detail, optional=opt)


def _check_package(diag: Diagnostics, name: str, required: bool = False,
                   optional: bool = False, hint: str = "", display: str = ""):
    """Проверить Python-пакет."""
    label = display or name
    try:
        importlib.import_module(name)
        diag.add(f"pip-пакет {label}", True, optional=optional or not required)
    except ImportError:
        detail = hint if hint else "не установлен"
        diag.add(f"pip-пакет {label}", False, detail, optional=optional or not required)


def check_or_exit() -> None:
    """Запустить диагностику и выйти с ошибкой, если что-то не готово."""
    diag = run_diagnostics()
    print(diag.report())
    if not diag.all_ok:
        sys.exit(1)


if __name__ == "__main__":
    check_or_exit()
