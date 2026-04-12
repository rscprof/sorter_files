"""Типы данных и модели."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import STATE_DIR


@dataclass
class ImageMetadata:
    """EXIF-метаданные изображения."""
    date_taken: Optional[str] = None        # ISO-строка
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gps_area_name: Optional[str] = None
    orientation: int = 0
    iso_speed: int = 0

    def similarity(self, other: "ImageMetadata") -> float:
        """Оценить схожесть двух метаданных (0-1)."""
        score = 0.0
        checks = 0

        # Совпадающее устройство
        if self.camera_make and other.camera_make:
            checks += 1
            if self.camera_make.lower() == other.camera_make.lower():
                score += 0.4

        # Близкая дата (в пределах 1 часа)
        if self.date_taken and other.date_taken:
            checks += 1
            try:
                d1 = datetime.fromisoformat(self.date_taken)
                d2 = datetime.fromisoformat(other.date_taken)
                if abs((d1 - d2).total_seconds()) < 3600:
                    score += 0.4
            except ValueError:
                pass

        # Близкое местоположение (в пределах 1 км)
        if (self.latitude is not None and other.latitude is not None
                and self.longitude is not None and other.longitude is not None):
            checks += 1
            import math
            dlat = self.latitude - other.latitude
            dlon = self.longitude - other.longitude
            dist = math.sqrt(dlat**2 + dlon**2) * 111  # грубо в км
            if dist < 1.0:
                score += 0.2

        return score / max(checks, 1)


@dataclass
class FileInfo:
    """Информация о файле после анализа."""
    original_path: str
    filename: str
    extension: str
    size: int
    mime_type: str
    file_hash: str = ""

    # Тип файла
    is_archive: bool = False
    is_distributable: bool = False
    is_build_artifact: bool = False

    # Дубликаты
    is_duplicate: bool = False
    duplicate_of: str = ""
    duplicate_action: str = "skip"  # skip | delete | keep_as_project_part

    # Результат AI-анализа (без жёстких категорий)
    ai_category: str = ""
    ai_subcategory: str = ""
    ai_suggested_name: str = ""
    ai_description: str = ""
    ai_reasoning: str = ""

    # Контекст
    related_files: list[str] = field(default_factory=list)
    is_part_of_project: bool = False
    project_root: str = ""

    # Метаданные для фото
    image_metadata: Optional[ImageMetadata] = None

    # Решение
    should_delete: bool = False
    target_path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.image_metadata:
            d["image_metadata"] = asdict(self.image_metadata)
        return d


@dataclass
class ProcessingState:
    """Состояние обработанных файлов (персистентное)."""
    processed_files: dict[str, dict] = field(default_factory=dict)  # hash -> info
    duplicates: dict[str, list[str]] = field(default_factory=dict)  # hash -> [paths]
    last_run: str = ""
    total_processed: int = 0
    total_duplicates_found: int = 0
    total_build_artifacts: int = 0
    total_errors: int = 0

    @property
    def state_path(self) -> str:
        return os.path.join(STATE_DIR, "state.json")

    def save(self):
        """Сохранить состояние."""
        os.makedirs(STATE_DIR, exist_ok=True)
        data = {
            "last_run": datetime.now().isoformat(),
            "total_processed": self.total_processed,
            "total_duplicates_found": self.total_duplicates_found,
            "total_build_artifacts": self.total_build_artifacts,
            "total_errors": self.total_errors,
            "files": self.processed_files,
            "duplicates": self.duplicates,
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls) -> "ProcessingState":
        """Загрузить состояние."""
        state = cls()
        path = state.state_path
        if not os.path.exists(path):
            return state
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            state.last_run = data.get("last_run", "")
            state.total_processed = data.get("total_processed", 0)
            state.total_duplicates_found = data.get("total_duplicates_found", 0)
            state.total_build_artifacts = data.get("total_build_artifacts", 0)
            state.total_errors = data.get("total_errors", 0)
            state.processed_files = data.get("files", {})
            state.duplicates = data.get("duplicates", {})
        except Exception as e:
            print(f"Warning: could not load state: {e}")
        return state

    def is_already_processed(self, file_hash: str) -> bool:
        return file_hash in self.processed_files

    def get_processed_info(self, file_hash: str) -> Optional[dict]:
        return self.processed_files.get(file_hash)

    def mark_processed(self, info: FileInfo):
        if info.file_hash:
            self.processed_files[info.file_hash] = info.to_dict()
            self.total_processed += 1

    def register_duplicate(self, file_hash: str, path: str):
        if file_hash not in self.duplicates:
            self.duplicates[file_hash] = []
        self.duplicates[file_hash].append(path)
        self.total_duplicates_found += 1
