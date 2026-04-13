"""Configuration loader — reads config.local.json with env override and defaults."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ── Defaults ───────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "language": "ru",

    "localai": {
        "url": "http://localhost:11434/v1",
        "model": "qwen3.5-35b-a3b-apex",
        "text_model": "Qwen3.5-35B-A3B-APEX-Mini.gguf",
        "vl_model": "qwen3-vl-4b-instruct",
        "timeout": 600,
        "max_tokens": 4096,
        "temperature": 0.15,
    },

    "searxng": {
        "url": "http://localhost:8080",
    },

    "paths": {
        "source": "~/nextcloud/files",
        "target": "~/nextcloud/files/organized",
    },

    "state_dir": "~/.local/state/file-organizer",

    "analysis": {
        "max_text_length": 5000,
        "pdf_max_pages": 5,
        "audio_transcribe_seconds": 60,
        "video_keyframes": 2,
        "large_file_threshold_mb": 500,
    },

    "temp_file_patterns": [
        "~$*", "~*", "*.tmp", "*.temp", "*.bak", "*.backup",
        "*.swp", "*.swo", "*~", ".DS_Store", "Thumbs.db",
        "desktop.ini", ".localized", "._*", ".AppleDouble",
        ".Spotlight-V100", ".Trash*", ".cache",
    ],

    "project_indicators": [
        "package.json", "requirements.txt", "setup.py", "pyproject.toml",
        "CMakeLists.txt", "Makefile", "Cargo.toml", "go.mod",
        "build.gradle", "pom.xml", ".git", ".gitignore", "Dockerfile",
    ],

    "project_exclude_dirs": [
        "html", "www", "var", "etc", "usr", "lib", "node_modules",
        "vendor", "htdocs", "public_html",
    ],

    "build_artifact_patterns": {
        "py": ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", "*.egg-info", "dist/", "build/", "*.egg"],
        "js": ["node_modules/", "dist/", "build/", ".next/", "out/", ".turbo/", "*.min.js", "*.min.js.map"],
        "java": ["target/", "build/", "out/", "*.class", "*.jar", "*.war", "*.ear", ".gradle/"],
        "c": ["build/", "cmake-build-debug/", "CMakeFiles/", "*.o", "*.so", "*.a", "*.exe"],
        "cs": ["bin/", "obj/", "*.dll", "*.exe", "*.pdb", ".vs/"],
        "go": ["vendor/", "*.exe", "dist/"],
        "rs": ["target/", "Cargo.lock"],
        "web": [".svelte-kit/", ".angular/", "coverage/", "dist/", "build/"],
        "general": [".DS_Store", "Thumbs.db", "*.log", "*.tmp", "*.swp", "*.swo", "*~"],
    },

    "extensions": {
        "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"],
        "executable": ["exe", "msi", "dmg", "deb", "rpm", "apk", "appimage", "iso"],
        "image": ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "tiff", "ico", "heic", "heif", "raw", "cr2", "nef", "arw"],
        "audio": ["ogg", "mp3", "wav", "flac", "aac", "wma", "m4a", "opus", "aiff"],
        "video": ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "3gp", "mpg", "mpeg"],
    },
}

# ── Load config.local.json ────────────────────────────────────────────

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_LOCAL = os.path.join(_CONFIG_DIR, "config.local.json")


def _load_config() -> dict[str, Any]:
    """Load config.local.json and merge with defaults."""
    cfg = dict(DEFAULTS)

    if os.path.exists(_CONFIG_LOCAL):
        try:
            with open(_CONFIG_LOCAL, "r", encoding="utf-8") as f:
                local = json.load(f)
            _deep_merge(cfg, local)
        except Exception as e:
            print(f"[config] Warning: could not load config.local.json: {e}")

    # Env variables override everything
    env_map = {
        "FILE_ORGANIZER_LANGUAGE": ("language", None),
        "FILE_ORGANIZER_LOCALAI_URL": ("localai", "url"),
        "FILE_ORGANIZER_LOCALAI_MODEL": ("localai", "model"),
        "FILE_ORGANIZER_LOCALAI_TEXT_MODEL": ("localai", "text_model"),
        "FILE_ORGANIZER_LOCALAI_VL_MODEL": ("localai", "vl_model"),
        "FILE_ORGANIZER_SEARXNG_URL": ("searxng", "url"),
        "FILE_ORGANIZER_SOURCE": ("paths", "source"),
        "FILE_ORGANIZER_TARGET": ("paths", "target"),
        "FILE_ORGANIZER_STATE_DIR": ("state_dir", None),
    }
    for env_key, path in env_map.items():
        val = os.environ.get(env_key)
        if val:
            if path[1] is None:
                cfg[path[0]] = val
            else:
                cfg.setdefault(path[0], {})[path[1]] = val

    return cfg


def _deep_merge(base: dict, override: dict):
    """Recursively merge override into base."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


_config = _load_config()


# ── Public constants (backwards-compatible) ───────────────────────────

LANGUAGE: str = _config.get("language", "ru")

LOCALAI_URL: str = _config.get("localai", {}).get("url", DEFAULTS["localai"]["url"])
LOCALAI_MODEL: str = _config.get("localai", {}).get("model", DEFAULTS["localai"]["model"])
LOCALAI_TEXT_MODEL: str = _config.get("localai", {}).get("text_model", DEFAULTS["localai"]["text_model"])
LOCALAI_VL_MODEL: str = _config.get("localai", {}).get("vl_model", DEFAULTS["localai"]["vl_model"])

SEARXNG_URL: str = _config.get("searxng", {}).get("url", DEFAULTS["searxng"]["url"])

SOURCE_DIR: str = os.path.expanduser(_config.get("paths", {}).get("source", DEFAULTS["paths"]["source"]))
TARGET_DIR: str = os.path.join(SOURCE_DIR, "organized")
_target_override = _config.get("paths", {}).get("target")
if _target_override:
    TARGET_DIR = os.path.expanduser(_target_override)

STATE_DIR: str = os.path.expanduser(_config.get("state_dir", DEFAULTS["state_dir"]))

# Extension sets
ARCHIVE_EXTS: set[str] = set(_config.get("extensions", {}).get("archive", DEFAULTS["extensions"]["archive"]))
EXECUTABLE_EXTS: set[str] = set(_config.get("extensions", {}).get("executable", DEFAULTS["extensions"]["executable"]))
IMAGE_EXTS: set[str] = set(_config.get("extensions", {}).get("image", DEFAULTS["extensions"]["image"]))
AUDIO_EXTS: set[str] = set(_config.get("extensions", {}).get("audio", DEFAULTS["extensions"]["audio"]))
VIDEO_EXTS: set[str] = set(_config.get("extensions", {}).get("video", DEFAULTS["extensions"]["video"]))

# Patterns
TEMP_FILE_PATTERNS: list[str] = _config.get("temp_file_patterns", DEFAULTS["temp_file_patterns"])
PROJECT_INDICATORS: list[str] = _config.get("project_indicators", DEFAULTS["project_indicators"])
PROJECT_EXCLUDE_DIRS: list[str] = _config.get("project_exclude_dirs", DEFAULTS["project_exclude_dirs"])
BUILD_ARTIFACT_PATTERNS: dict[str, list[str]] = _config.get("build_artifact_patterns", DEFAULTS["build_artifact_patterns"])

# Analysis settings
ANALYSIS_MAX_TEXT_LENGTH: int = _config.get("analysis", {}).get("max_text_length", DEFAULTS["analysis"]["max_text_length"])
ANALYSIS_PDF_MAX_PAGES: int = _config.get("analysis", {}).get("pdf_max_pages", DEFAULTS["analysis"]["pdf_max_pages"])
ANALYSIS_AUDIO_TRANSCRIBE_SECONDS: int = _config.get("analysis", {}).get("audio_transcribe_seconds", DEFAULTS["analysis"]["audio_transcribe_seconds"])
ANALYSIS_VIDEO_KEYFRAMES: int = _config.get("analysis", {}).get("video_keyframes", DEFAULTS["analysis"]["video_keyframes"])
ANALYSIS_LARGE_FILE_THRESHOLD_MB: int = _config.get("analysis", {}).get("large_file_threshold_mb", DEFAULTS["analysis"]["large_file_threshold_mb"])

# Derived paths (based on TARGET_DIR)
DELETE_DIR: str = os.path.join(TARGET_DIR, "_на_удаление" if LANGUAGE == "ru" else "_delete_later")
ARCHIVE_DIR: str = os.path.join(TARGET_DIR, "_архивы" if LANGUAGE == "ru" else "_archives")
UNKNOWN_DIR: str = os.path.join(TARGET_DIR, "_неразобранное" if LANGUAGE == "ru" else "_unknown")
BUILD_ARTIFACTS_DIR: str = os.path.join(TARGET_DIR, "_build_artifacts")


def get_config() -> dict[str, Any]:
    """Return full config dict."""
    return dict(_config)
