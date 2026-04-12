{ pkgs ? import <nixpkgs> {} }:

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
    poppler_utils   # pdftotext
    p7zip           # 7z
    rar             # unrar
    file            # libmagic
    exiftool        # EXIF-парсер

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
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    export PYTHONPATH="$(pwd):$PYTHONPATH"
  '';
}
