{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

pkgs.mkShell {
  name = "file-organizer";

  packages = with pkgs; [
    # Python
    python313
    python313Packages.requests
    python313Packages.pdfplumber
    python313Packages.python-docx
    python313Packages.openpyxl
    python313Packages.python-pptx

    # Утилиты для анализа
    poppler-utils   # pdftotext
    p7zip           # 7z
    rar             # unrar (unfree)
    file            # libmagic
    exiftool        # EXIF-парсер
    ffmpeg          # ffprobe для аудио-метаданных

    # Git
    git
  ];

  shellHook = ''
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  File Organizer shell"
    echo "  Python: $(python --version 2>&1)"
    echo "  pdftotext: $(which pdftotext)"
    echo "  7z: $(which 7z)"
    echo "  unrar: $(which unrar)"
    echo "  exiftool: $(which exiftool)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    export PYTHONPATH="$(pwd):$PYTHONPATH"
  '';
}
