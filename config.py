"""Конфигурация программы."""

import os

LOCALAI_URL = os.getenv("LOCALAI_URL", "http://localhost:11434/v1")
LOCALAI_MODEL = os.getenv("LOCALAI_MODEL", "qwen3.5-35b-a3b-apex")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
SOURCE_DIR = os.path.expanduser("~/nextcloud/files")
TARGET_DIR = os.path.join(SOURCE_DIR, "organized")
STATE_DIR = os.path.expanduser("~/.local/state/file-organizer")

# Служебные каталоги
DELETE_DIR = os.path.join(TARGET_DIR, "_на_удаление")
ARCHIVE_DIR = os.path.join(TARGET_DIR, "_архивы")
UNKNOWN_DIR = os.path.join(TARGET_DIR, "_неразобранное")
BUILD_ARTIFACTS_DIR = os.path.join(TARGET_DIR, "_build_artifacts")

# Расширения
ARCHIVE_EXTS = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"}
EXECUTABLE_EXTS = {"exe", "msi", "dmg", "deb", "rpm", "apk", "appimage", "iso"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "tiff", "ico", "heic", "heif", "raw", "cr2", "nef", "arw"}

# Build-артефакты по языкам
BUILD_ARTIFACT_PATTERNS = {
    "py": ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", "*.egg-info", "dist/", "build/", "*.egg"],
    "js": ["node_modules/", "dist/", "build/", ".next/", "out/", ".turbo/", "*.min.js", "*.min.js.map"],
    "java": ["target/", "build/", "out/", "*.class", "*.jar", "*.war", "*.ear", ".gradle/"],
    "c": ["build/", "cmake-build-debug/", "CMakeFiles/", "*.o", "*.so", "*.a", "*.exe"],
    "cs": ["bin/", "obj/", "*.dll", "*.exe", "*.pdb", ".vs/"],
    "go": ["vendor/", "*.exe", "dist/"],
    "rs": ["target/", "Cargo.lock"],
    "web": [".svelte-kit/", ".angular/", "coverage/", "dist/", "build/"],
    "general": [".DS_Store", "Thumbs.db", "*.log", "*.tmp", "*.swp", "*.swo", "*~"],
}

# Индикаторы проекта
PROJECT_INDICATORS = [
    "package.json", "requirements.txt", "setup.py", "pyproject.toml",
    "CMakeLists.txt", "Makefile", "Cargo.toml", "go.mod",
    "build.gradle", "pom.xml", ".git", ".gitignore", "Dockerfile",
]

# Исключения — каталоги, которые НЕ считать корнем проекта
PROJECT_EXCLUDE_DIRS = [
    "html", "www", "var", "etc", "usr", "lib", "node_modules",
    "vendor", "htdocs", "public_html",
]
