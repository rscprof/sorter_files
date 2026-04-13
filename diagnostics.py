"""Диагностика зависимостей: сервисы, утилиты, пакеты."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import LOCALAI_URL, LOCALAI_MODEL, SEARXNG_URL


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Diagnostics:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = ""):
        self.checks.append(CheckResult(name, ok, detail))

    def report(self) -> str:
        lines = ["─" * 50, "Диагностика зависимостей", "─" * 50]
        for c in self.checks:
            status = "✓" if c.ok else "✗"
            detail = f" — {c.detail}" if c.detail else ""
            lines.append(f"  [{status}] {c.name}{detail}")
        lines.append("─" * 50)
        if self.all_ok:
            lines.append("Всё в порядке")
        else:
            failed = [c.name for c in self.checks if not c.ok]
            lines.append(f"НЕ ГОТОВО: {', '.join(failed)}")
        return "\n".join(lines)


def run_diagnostics() -> Diagnostics:
    """Полная проверка всех зависимостей."""
    diag = Diagnostics()

    # ── HTTP-сервисы ──
    # LocalAI: проверяем /v1/models напрямую
    try:
        r = requests.get(f"{LOCALAI_URL.rstrip('/')}/models", timeout=10)
        if r.status_code == 200:
            diag.add("LocalAI", True, "API доступен")
            diag.add(
                f"  модель {LOCALAI_MODEL}",
                *_check_model_available(LOCALAI_MODEL),
            )
        else:
            diag.add("LocalAI", False, f"HTTP {r.status_code}")
    except Exception as e:
        diag.add("LocalAI", False, str(e)[:100])

    # SearXNG: проверяем реальный поиск
    try:
        r = requests.get(
            f"{SEARXNG_URL.rstrip('/')}/search",
            params={"q": "test", "format": "json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("results", []))
            diag.add("SearXNG", True, f"{n} результатов на 'test'")
        else:
            diag.add("SearXNG", False, f"HTTP {r.status_code}")
    except Exception as e:
        diag.add("SearXNG", False, str(e)[:100])

    # ── Системные утилиты ──
    for tool in ("pdftotext", "7z", "unrar", "tar"):
        diag.add(f"утилита {tool}", _check_tool(tool), "" if _check_tool(tool) else "не найдена в PATH")

    # ── Python-пакеты ──
    for pkg in ("requests",):
        diag.add(f"pip-пакет {pkg}", _check_package(pkg), "")

    return diag


def _check_http(url: str, name: str) -> tuple[bool, str]:
    """Проверка HTTP-сервиса. Только 200 = OK."""
    try:
        r = requests.get(url.rstrip("/") + "/health" if "searx" not in url.lower() else url, timeout=10)
        if r.status_code == 200:
            return True, f"HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:100]


def _check_model_available(model: str) -> tuple[bool, str]:
    try:
        r = requests.get(f"{LOCALAI_URL.rstrip('/')}/models", timeout=10)
        models = r.json().get("data", [])
        ids = [m.get("id", "") for m in models]
        if model in ids:
            return True, ""
        # Частичное совпадение
        partial = [m for m in ids if model.lower() in m.lower() or m.lower() in model.lower()]
        if partial:
            return True, f"найдена как {partial[0]}"
        return False, f"доступны: {', '.join(ids[:5])}..."
    except Exception as e:
        return False, str(e)[:100]


def _check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def _check_package(name: str) -> bool:
    import importlib
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def check_or_exit() -> None:
    """Запустить диагностику и выйти с ошибкой, если что-то не готово."""
    diag = run_diagnostics()
    print(diag.report())
    if not diag.all_ok:
        print("\nУстраните проблемы и повторите запуск.")
        print("Подсказка: LOCALAI_URL, LOCALAI_MODEL, SEARXNG_URL — через env.")
        sys.exit(1)


if __name__ == "__main__":
    check_or_exit()
