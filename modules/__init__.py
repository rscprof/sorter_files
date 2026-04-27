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
  65 — php                (PHP-файлы: проекты vs скрипты)
  70 — database           (SQL/DB файлы: дампы, миграции, проекты БД)
  75 — documents          (документы с текстом: AI)
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
from modules.php import PhpAnalyzer
from modules.database import DatabaseAnalyzer
from modules.documents import DocumentsAnalyzer
from modules.fb2 import Fb2Analyzer
from modules.rtf import RtfAnalyzer
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
        PhpAnalyzer,                # 65
        DatabaseAnalyzer,           # 70
        DocumentsAnalyzer,          # 75
        Fb2Analyzer,                # 76
        RtfAnalyzer,                # 77
        FallbackAnalyzer,           # 999
    ],
    key=lambda cls: cls().priority,
)


def get_analyzers() -> list[type[BaseAnalyzer]]:
    """Вернуть список классов анализаторов, отсортированный по priority."""
    return list(ANALYZERS)
