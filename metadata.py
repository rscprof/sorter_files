"""EXIF-метаданные изображений."""

from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Optional

from models import ImageMetadata


def read_image_metadata(filepath: str) -> Optional[ImageMetadata]:
    """Извлечь EXIF-метаданные из изображения."""
    ext = Path(filepath).suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg", "tiff", "tif", "cr2", "nef", "arw"):
        return _read_exif(filepath)
    elif ext in ("png",):
        return _read_png_date(filepath)
    elif ext in ("heic", "heif"):
        # HEIF — упрощённо
        return ImageMetadata()
    return None


def _read_exif(filepath: str) -> ImageMetadata:
    """Чтение EXIF из JPEG/TIFF без внешних зависимостей.
    
    Используем минимальный парсер: ищем маркер APP1 (EXIF) и извлекаем
    интересующие теги. Если не получается — возвращаем пустой объект.
    """
    meta = ImageMetadata()
    try:
        with open(filepath, "rb") as f:
            data = f.read(2)
            if data != b"\xff\xd8":
                return meta  # не JPEG

            # Читаем сегменты
            while True:
                marker = f.read(2)
                if len(marker) < 2:
                    break
                if marker[0] != 0xFF:
                    break
                seg_type = marker[1]
                if seg_type == 0xD9:  # EOI
                    break
                if seg_type == 0xE1:  # APP1 — EXIF
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    seg_data = f.read(seg_len - 2)
                    if seg_data[:6] == b"Exif\x00\x00":
                        meta = _parse_exif_ifd(seg_data[6:])
                        break
                elif 0xD0 <= seg_type <= 0xD8:
                    continue  # маркеры без длины
                else:
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    f.seek(seg_len - 2, 1)
    except Exception:
        pass

    # Fallback: время модификации файла
    if not meta.date_taken:
        try:
            mtime = os.path.getmtime(filepath)
            from datetime import datetime
            meta.date_taken = datetime.fromtimestamp(mtime).isoformat()
        except Exception:
            pass

    return meta


def _parse_exif_ifd(exif_data: bytes) -> ImageMetadata:
    """Парсинг EXIF IFD."""
    meta = ImageMetadata()
    try:
        # Определяем порядок байт
        if exif_data[:2] == b"II\x2a\x00":
            endian = "<"
        elif exif_data[:2] == b"MM\x00\x2a":
            endian = ">"
        else:
            return meta

        import struct

        ifd_offset = struct.unpack(endian + "I", exif_data[4:8])[0]
        if ifd_offset >= len(exif_data):
            return meta

        # Читаем IFD0
        num_entries = struct.unpack(endian + "H", exif_data[ifd_offset:ifd_offset + 2])[0]
        offset = ifd_offset + 2

        # Теги EXIF
        TAGS = {
            0x010F: "camera_make",
            0x0110: "camera_model",
            0x0112: "orientation",
            0x829A: "exposure_time",
            0x8827: "iso_speed",
        }

        # GPS теги
        GPS_TAGS = {
            0x0001: "gps_latitude_ref",
            0x0002: "gps_latitude",
            0x0003: "gps_longitude_ref",
            0x0004: "gps_longitude",
        }

        exif_ifd_offset = 0
        gps_ifd_offset = 0

        for _ in range(num_entries):
            tag = struct.unpack(endian + "H", exif_data[offset:offset + 2])[0]
            typ = struct.unpack(endian + "H", exif_data[offset + 2:offset + 4])[0]
            count = struct.unpack(endian + "I", exif_data[offset + 4:offset + 8])[0]
            value_offset = offset + 8

            if tag == 0x8769:  # ExifIFD pointer
                exif_ifd_offset = struct.unpack(endian + "I", exif_data[offset + 8:offset + 12])[0]
            elif tag == 0x8825:  # GPSIFD pointer
                gps_ifd_offset = struct.unpack(endian + "I", exif_data[offset + 8:offset + 12])[0]
            elif tag == 0x0132:  # DateTime
                # Строка в IFD
                if count <= 4:
                    val = exif_data[offset + 8:offset + 8 + count].rstrip(b"\x00").decode("ascii", errors="ignore")
                else:
                    str_offset = struct.unpack(endian + "I", exif_data[offset + 8:offset + 12])[0]
                    if str_offset < len(exif_data):
                        val = exif_data[str_offset:str_offset + count].rstrip(b"\x00").decode("ascii", errors="ignore")
                    else:
                        val = ""
                if val:
                    meta.date_taken = _normalize_exif_datetime(val)

            offset += 12

        # Читаем ExifIFD (для DateTimeOriginal)
        if exif_ifd_offset and exif_ifd_offset < len(exif_data) - 2:
            exif_num = struct.unpack(endian + "H", exif_data[exif_ifd_offset:exif_ifd_offset + 2])[0]
            exif_off = exif_ifd_offset + 2
            for _ in range(exif_num):
                if exif_off + 12 > len(exif_data):
                    break
                tag = struct.unpack(endian + "H", exif_data[exif_off:exif_off + 2])[0]
                if tag == 0x9003:  # DateTimeOriginal
                    count = struct.unpack(endian + "I", exif_data[exif_off + 4:exif_off + 8])[0]
                    str_offset = struct.unpack(endian + "I", exif_data[exif_off + 8:exif_off + 12])[0]
                    if str_offset < len(exif_data):
                        val = exif_data[str_offset:str_offset + count].rstrip(b"\x00").decode("ascii", errors="ignore")
                        if val:
                            meta.date_taken = _normalize_exif_datetime(val)
                    break
                exif_off += 12

        # Читаем GPS IFD
        if gps_ifd_offset and gps_ifd_offset < len(exif_data) - 2:
            meta = _parse_gps_ifd(exif_data, gps_ifd_offset, endian, meta)

    except Exception:
        pass

    return meta


def _parse_gps_ifd(data: bytes, offset: int, endian: str, meta: ImageMetadata) -> ImageMetadata:
    """Парсинг GPS IFD."""
    import struct
    try:
        num = struct.unpack(endian + "H", data[offset:offset + 2])[0]
        off = offset + 2
        gps = {}

        for _ in range(num):
            if off + 12 > len(data):
                break
            tag = struct.unpack(endian + "H", data[off:off + 2])[0]
            typ = struct.unpack(endian + "H", data[off + 2:off + 4])[0]
            count = struct.unpack(endian + "I", data[off + 4:off + 8])[0]
            val_off = off + 8

            if tag in (0x0002, 0x0004):  # Lat/Lon — рациональные числа
                rat_offset = struct.unpack(endian + "I", data[val_off:val_off + 4])[0]
                if rat_offset + 24 <= len(data):
                    nums = []
                    for i in range(3):
                        num_val = struct.unpack(endian + "I", data[rat_offset + i * 8:rat_offset + i * 8 + 4])[0]
                        den_val = struct.unpack(endian + "I", data[rat_offset + i * 8 + 4:rat_offset + i * 8 + 8])[0]
                        if den_val:
                            nums.append(num_val / den_val)
                        else:
                            nums.append(0)
                    if tag == 0x0002:
                        gps["lat"] = nums[0] + nums[1] / 60 + nums[2] / 3600
                    else:
                        gps["lon"] = nums[0] + nums[1] / 60 + nums[2] / 3600
            elif tag == 0x0001:  # Lat ref
                ref = data[val_off:val_off + 1].decode("ascii", errors="ignore")
                gps["lat_ref"] = ref
            elif tag == 0x0003:  # Lon ref
                ref = data[val_off:val_off + 1].decode("ascii", errors="ignore")
                gps["lon_ref"] = ref

            off += 12

        if "lat" in gps:
            meta.latitude = gps["lat"] * (-1 if gps.get("lat_ref") == "S" else 1)
        if "lon" in gps:
            meta.longitude = gps["lon"] * (-1 if gps.get("lon_ref") == "W" else 1)

    except Exception:
        pass

    return meta


def _normalize_exif_datetime(s: str) -> str:
    """EXIF datetime '2023:10:15 14:30:00' -> ISO."""
    from datetime import datetime
    try:
        dt = datetime.strptime(s.strip(), "%Y:%m:%d %H:%M:%S")
        return dt.isoformat()
    except ValueError:
        return s


def _read_png_date(filepath: str) -> Optional[ImageMetadata]:
    """Извлечь дату из PNG chunk tIME."""
    meta = ImageMetadata()
    try:
        with open(filepath, "rb") as f:
            f.read(8)  # signature
            while True:
                import struct
                length_data = f.read(4)
                if len(length_data) < 4:
                    break
                length = struct.unpack(">I", length_data)[0]
                chunk_type = f.read(4).decode("ascii", errors="ignore")
                chunk_data = f.read(length)
                f.read(4)  # CRC

                if chunk_type == "tIME" and len(chunk_data) == 7:
                    year, month, day, hour, minute, second = struct.unpack(">HBBBBB", chunk_data)
                    from datetime import datetime
                    meta.date_taken = datetime(year, month, day, hour, minute, second).isoformat()
                    break
                elif chunk_type == "IEND":
                    break
    except Exception:
        pass

    return meta
