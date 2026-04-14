"""Пакет анализаторов файлов.

Модули вызываются в порядке priority (от меньшего к большему).
Первый модуль, который может обработать файл — делает это.

Priority order:
  10 — build_artifacts    (build-артефакты в проектах)
  20 — distributables     (общедоступные дистрибутивы)
  30 — archives           (архивы для распаковки)
  40 — audio              (аудио: whisper → AI)
  50 — pdf_scans          (PDF-сканы: конвертация → OCR → AI)
  60 — images             (изображения: EXIF → JPEG → AI)
  70 — documents          (документы с текстом: AI)
  999 — fallback          (всё остальное: по расширению)
"""

from modules.base import BaseAnalyzer
from modules.build_artifacts import BuildArtifactsAnalyzer
from modules.distributables import DistributablesAnalyzer
from modules.archives import ArchivesAnalyzer
from modules.audio import AudioAnalyzer
from modules.video import VideoAnalyzer
from modules.pdf_scans import PdfScansAnalyzer
from modules.djvu import DjvuAnalyzer
from modules.images import ImagesAnalyzer
from modules.documents import DocumentsAnalyzer
from modules.fallback import FallbackAnalyzer

# Все анализаторы, отсортированные по приоритету
ANALYZERS: list[type[BaseAnalyzer]] = sorted(
    [
        BuildArtifactsAnalyzer,     # 10
        DistributablesAnalyzer,     # 20
        ArchivesAnalyzer,           # 30
        AudioAnalyzer,              # 40
        VideoAnalyzer,              # 45
        PdfScansAnalyzer,           # 50
        DjvuAnalyzer,               # 49
        ImagesAnalyzer,             # 60
        DocumentsAnalyzer,          # 70
        FallbackAnalyzer,           # 999
    ],
    key=lambda cls: cls().priority,
)


def get_analyzers() -> list[type[BaseAnalyzer]]:
    """Вернуть список классов анализаторов, отсортированный по priority."""
    return list(ANALYZERS)
