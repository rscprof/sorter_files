"""Распаковка архивов."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_archive(filepath: str, target_dir: str) -> list[str]:
    """Распаковать архив, вернуть список извлечённых файлов."""
    ext = Path(filepath).suffix.lower().lstrip(".")
    os.makedirs(target_dir, exist_ok=True)

    try:
        if ext == "zip":
            import zipfile
            with zipfile.ZipFile(filepath, "r") as zf:
                zf.extractall(target_dir)
                return zf.namelist()

        elif ext in ("tar", "gz", "bz2", "xz", "tgz"):
            import tarfile
            mode = "r:*" if ext in ("gz", "tgz") else "r"
            with tarfile.open(filepath, mode) as tf:
                tf.extractall(target_dir)
                return tf.getnames()

        elif ext == "7z":
            result = subprocess.run(
                ["7z", "x", filepath, f"-o{target_dir}", "-y"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return [
                    line.split()[-1]
                    for line in result.stdout.splitlines()
                    if line.startswith("Extracting")
                ]
            logger.error(f"7z error: {result.stderr}")

        elif ext == "rar":
            result = subprocess.run(
                ["unrar", "x", filepath, target_dir, "-y"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return [
                    l.strip() for l in result.stdout.splitlines()
                    if l.strip() and not l.startswith("UNRAR")
                ]
            logger.error(f"unrar error: {result.stderr}")

    except Exception as e:
        logger.error(f"Ошибка распаковки {filepath}: {e}")

    return []
