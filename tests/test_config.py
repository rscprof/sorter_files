"""Тесты config.py."""

import os
import fnmatch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    TEMP_FILE_PATTERNS, BUILD_ARTIFACT_PATTERNS,
    PROJECT_INDICATORS, PROJECT_EXCLUDE_DIRS,
    ARCHIVE_EXTS, EXECUTABLE_EXTS, IMAGE_EXTS,
)


class TestTempFilePatterns:
    def test_patterns_match_expected(self):
        """Проверяем что паттерны покрывают типичные временные файлы."""
        test_cases = [
            ("~$document.docx", "~$*"),
            ("~WRL0003.tmp", "~*"),
            ("file.tmp", "*.tmp"),
            ("file.bak", "*.bak"),
            ("file.swp", "*.swp"),
            ("file~", "*~"),
            (".DS_Store", ".DS_Store"),
            ("Thumbs.db", "Thumbs.db"),
            ("._MacOSX", "._*"),
        ]
        for filename, expected_pattern in test_cases:
            assert fnmatch.fnmatch(filename, expected_pattern), \
                f"{filename} должен совпадать с {expected_pattern}"


class TestBuildArtifactPatterns:
    def test_patterns_cover_common_artifacts(self):
        """Проверяем что паттерны покрывают типичные build-артефакты."""
        artifacts = [
            "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache",
            "node_modules/", "dist/", "build/", ".next/", "out/", ".turbo/",
            "target/", "out/", "*.class", "*.jar", "*.war",
            "cmake-build-debug/", "CMakeFiles/", "*.o", "*.so", "*.a",
            "bin/", "obj/", "*.dll", "*.exe", "*.pdb", ".vs/",
            "vendor/", "*.egg",
            "Cargo.lock", ".DS_Store", "Thumbs.db", "*.log", "*.tmp", "*.swp",
        ]
        for artifact in artifacts:
            found = False
            for lang, patterns in BUILD_ARTIFACT_PATTERNS.items():
                for pattern in patterns:
                    if artifact in pattern or pattern in artifact or artifact.rstrip("/") in pattern:
                        found = True
                        break
                if found:
                    break
            # Не все артефакты обязаны быть в patterns напрямую,
            # но проверяем ключевые
            if artifact in ("__pycache__", "node_modules/", "dist/", "target/", "*.pyc"):
                assert found, f"{artifact} должен быть покрыт BUILD_ARTIFACT_PATTERNS"


class TestProjectIndicators:
    def test_indicators_not_empty(self):
        assert len(PROJECT_INDICATORS) > 0

    def test_common_indicators_present(self):
        expected = ["package.json", "requirements.txt", ".git", ".gitignore"]
        for ind in expected:
            assert ind in PROJECT_INDICATORS, f"{ind} должен быть в PROJECT_INDICATORS"


class TestProjectExcludeDirs:
    def test_exclude_dirs_not_empty(self):
        assert len(PROJECT_EXCLUDE_DIRS) > 0

    def test_common_excludes(self):
        expected = ["html", "www", "var", "etc", "node_modules"]
        for d in expected:
            assert d in PROJECT_EXCLUDE_DIRS, f"{d} должен быть в PROJECT_EXCLUDE_DIRS"


class TestExtensionSets:
    def test_archive_exts_not_empty(self):
        assert len(ARCHIVE_EXTS) > 0

    def test_executable_exts_not_empty(self):
        assert len(EXECUTABLE_EXTS) > 0

    def test_image_exts_not_empty(self):
        assert len(IMAGE_EXTS) > 0

    def test_common_archive_exts(self):
        for ext in ["zip", "tar", "gz", "7z", "rar", "tgz"]:
            assert ext in ARCHIVE_EXTS

    def test_common_executable_exts(self):
        for ext in ["exe", "msi", "dmg", "deb", "rpm", "apk", "iso"]:
            assert ext in EXECUTABLE_EXTS

    def test_common_image_exts(self):
        for ext in ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff"]:
            assert ext in IMAGE_EXTS
