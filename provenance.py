"""Карточная система provenance — отслеживание происхождения файлов.

Хранится в TARGET/.provenance/ — независимо от state.json,
НИКОГДА не удаляется через --reset-state.

Формат: cards.jsonl — одна запись на файл, по file_hash.
Каждая запись — "карточка" как в библиотеке.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

PROVENANCE_DIR_NAME = ".provenance"
CARDS_FILE = "cards.jsonl"


@dataclass
class ProvenanceCard:
    """Карточка файла — откуда он, куда перемещён, история."""
    file_hash: str                      # SHA-256 — ключ
    filename: str                       # Имя файла
    first_seen_path: str                # САМЫЙ ПЕРВЫЙ путь где файл был найден (immutable)
    current_path: str                   # Текущее расположение
    first_processed: str                # ISO timestamp первого обнаружения
    last_processed: str                 # ISO timestamp последней обработки
    category: str = ""                  # Категория при обработке
    subcategory: str = ""
    description: str = ""
    
    # Если файл извлечён из архива
    archive_source: str = ""            # Путь к архиву
    archive_extract_dir: str = ""       # Куда распакован
    
    # История перемещений (для --reprocess)
    move_history: list[dict] = field(default_factory=list)
    # Каждый entry: {"from": "...", "to": "...", "timestamp": "...", "reason": "initial|reprocess"}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProvenanceCard":
        # Поддержка старых записей без всех полей
        return cls(
            file_hash=d.get("file_hash", ""),
            filename=d.get("filename", ""),
            first_seen_path=d.get("first_seen_path", ""),
            current_path=d.get("current_path", ""),
            first_processed=d.get("first_processed", ""),
            last_processed=d.get("last_processed", ""),
            category=d.get("category", ""),
            subcategory=d.get("subcategory", ""),
            description=d.get("description", ""),
            archive_source=d.get("archive_source", ""),
            archive_extract_dir=d.get("archive_extract_dir", ""),
            move_history=d.get("move_history", []),
        )


class ProvenanceStore:
    """Хранилище карточек provenance.
    
    Чтение/запись в JSONL файл в TARGET/.provenance/
    """

    def __init__(self, target_dir: str):
        self.prov_dir = os.path.join(target_dir, PROVENANCE_DIR_NAME)
        self.cards_path = os.path.join(self.prov_dir, CARDS_FILE)
        self.cards: dict[str, ProvenanceCard] = {}  # hash -> card
        self._load()

    def _load(self):
        """Загрузить карточки из JSONL."""
        if not os.path.exists(self.cards_path):
            return
        try:
            with open(self.cards_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    card = ProvenanceCard.from_dict(d)
                    self.cards[card.file_hash] = card
        except Exception as e:
            print(f"[Provenance] Ошибка загрузки: {e}")

    def save(self):
        """Сохранить карточки в JSONL."""
        os.makedirs(self.prov_dir, exist_ok=True)
        with open(self.cards_path, "w", encoding="utf-8") as f:
            for card in self.cards.values():
                f.write(json.dumps(card.to_dict(), ensure_ascii=False) + "\n")

    def get_card(self, file_hash: str) -> Optional[ProvenanceCard]:
        """Получить карточку по хешу."""
        return self.cards.get(file_hash)

    def find_by_current_path(self, path: str) -> Optional[ProvenanceCard]:
        """Найти карточку по текущему пути файла."""
        path = os.path.abspath(path)
        for card in self.cards.values():
            if os.path.abspath(card.current_path) == path:
                return card
        return None

    def find_by_original(self, original_path: str) -> list[ProvenanceCard]:
        """Найти все карточки, которые были из указанного каталога."""
        original_path = os.path.abspath(original_path).rstrip("/")
        results = []
        for card in self.cards.values():
            # Проверяем first_seen_path и всю историю перемещений
            if card.first_seen_path.startswith(original_path + "/"):
                results.append(card)
                continue
            for move in card.move_history:
                if move.get("from", "").startswith(original_path + "/"):
                    results.append(card)
                    break
        return results

    def find_by_first_seen(self, first_path: str) -> list[ProvenanceCard]:
        """Найти все карточки, первый увиденный путь которых начинается с first_path."""
        first_path = os.path.abspath(first_path).rstrip("/")
        return [
            card for card in self.cards.values()
            if card.first_seen_path.startswith(first_path + "/")
        ]

    def upsert(self, file_hash: str, filename: str, original_path: str,
               current_path: str, category: str = "", subcategory: str = "",
               description: str = "", archive_source: str = "",
               archive_extract_dir: str = "", reason: str = "initial") -> ProvenanceCard:
        """Создать или обновить карточку."""
        original_path = os.path.abspath(original_path)
        current_path = os.path.abspath(current_path)
        now = datetime.now().isoformat()

        if file_hash in self.cards:
            card = self.cards[file_hash]
            # Обновляем существующую
            if card.current_path != current_path:
                card.move_history.append({
                    "from": card.current_path,
                    "to": current_path,
                    "timestamp": now,
                    "reason": reason,
                })
            card.current_path = current_path
            card.last_processed = now
            if category:
                card.category = category
            if subcategory:
                card.subcategory = subcategory
            if description:
                card.description = description
        else:
            # Новая карточка
            card = ProvenanceCard(
                file_hash=file_hash,
                filename=filename,
                first_seen_path=original_path,
                current_path=current_path,
                first_processed=now,
                last_processed=now,
                category=category,
                subcategory=subcategory,
                description=description,
                archive_source=archive_source,
                archive_extract_dir=archive_extract_dir,
            )
            self.cards[file_hash] = card

        return card

    def get_stats(self) -> dict:
        """Статистика по карточкам."""
        cats = {}
        for card in self.cards.values():
            cat = card.category or "?"
            cats[cat] = cats.get(cat, 0) + 1
        return {
            "total_cards": len(self.cards),
            "categories": cats,
            "with_archive_source": sum(1 for c in self.cards.values() if c.archive_source),
            "with_move_history": sum(1 for c in self.cards.values() if c.move_history),
        }
