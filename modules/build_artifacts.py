"""Модуль: build-артефакты (приоритет 10 — самый первый)."""

from __future__ import annotations

from typing import Optional

from modules.base import BaseAnalyzer
from models import FileInfo
from projects import find_project_root, is_build_artifact


class BuildArtifactsAnalyzer(BaseAnalyzer):
    """Определяет build-артефакты в проектах."""

    @property
    def priority(self) -> int:
        return 10

    @property
    def name(self) -> str:
        return "build_artifacts"

    def can_handle(self, filepath: str) -> bool:
        proj_root = find_project_root(filepath)
        if not proj_root:
            return False
        return is_build_artifact(filepath, proj_root)

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        proj_root = find_project_root(filepath)
        info = self._make_info(filepath)
        info.is_build_artifact = True
        info.is_part_of_project = True
        info.project_root = proj_root or ""
        info.should_delete = True
        info.ai_category = "build_artifact"
        info.ai_description = f"Build-артефакт проекта {proj_root and (proj_root.split('/')[-1] or '?')}"
        return info
