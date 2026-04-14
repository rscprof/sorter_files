{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

pkgs.mkShell {
  name = "file-organizer";

  packages = with pkgs; [
    # ── Python ──
    python313
    python313Packages.requests
    python313Packages.pillow
    python313Packages.pdfplumber
    python313Packages.python-docx
    python313Packages.openpyxl
    python313Packages.python-pptx
    python313Packages.mutagen
    python313Packages.pytest

    # ── Обязательные утилиты ──
    poppler-utils   # pdftotext — извлечение текста из PDF
    p7zip           # 7z — распаковка 7z/CAB/WIM архивов
    ffmpeg          # ffprobe — метаданные видео/аудио, извлечение аудио

    # ── Опциональные утилиты ──
    rar             # unrar — распаковка RAR архивов (unfree)
    djvulibre       # djvutxt — извлечение текста из DJVU
    antiword        # извлечение текста из .doc (старый Word)
    catdoc          # извлечение текста из .doc (альтернатива)
    exiftool        # расширенные EXIF-метаданные
    file            # libmagic — определение MIME-типов

    # ── Инструменты ──
    git
  ];

  shellHook = ''
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  File Organizer shell"
    echo "  Python: $(python --version 2>&1)"
    echo ""
    echo "  Обязательные утилиты:"
    echo "    pdftotext: $(which pdftotext 2>/dev/null || echo 'НЕ НАЙДЕН')"
    echo "    7z:        $(which 7z 2>/dev/null || echo 'НЕ НАЙДЕН')"
    echo "    ffmpeg:    $(which ffmpeg 2>/dev/null || echo 'НЕ НАЙДЕН')"
    echo "    ffprobe:   $(which ffprobe 2>/dev/null || echo 'НЕ НАЙДЕН')"
    echo ""
    echo "  Опциональные утилиты:"
    echo "    unrar:     $(which unrar 2>/dev/null || echo '—')"
    echo "    djvutxt:   $(which djvutxt 2>/dev/null || echo '—')"
    echo "    antiword:  $(which antiword 2>/dev/null || echo '—')"
    echo "    exiftool:  $(which exiftool 2>/dev/null || echo '—')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    export PYTHONPATH="$(pwd):$PYTHONPATH"
  '';
}
