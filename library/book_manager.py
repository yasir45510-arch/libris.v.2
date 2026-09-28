"""Persistent management of the local LIBRIS book library."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "library.json"
BOOKS_DIR = PROJECT_ROOT / "books" / "library"
INBOX_DIR = PROJECT_ROOT / "books" / "inbox"
IMPORTED_INBOX_DIR = INBOX_DIR / "imported"
CURRENT_BOOK_FILE = PROJECT_ROOT / "books" / "current.json"
SUPPORTED_FORMATS = {".txt", ".pdf", ".epub"}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_library_folders() -> None:
    """Create the visible book folders used by LIBRIS."""
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTED_INBOX_DIR.mkdir(parents=True, exist_ok=True)


def list_books() -> list[dict[str, str]]:
    return _read_json(DATA_FILE, [])


def get_book(book_id: str) -> dict[str, str] | None:
    return next((book for book in list_books() if book["id"] == book_id), None)


def add_book(source_path: str, title: str | None = None, author: str = "Unknown") -> dict[str, str]:
    """Copy one supported book into LIBRIS and register its metadata."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("That book file does not exist.")
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError("Choose a TXT, PDF, or EPUB book.")

    ensure_library_folders()
    book_id = uuid.uuid4().hex[:8]
    destination = BOOKS_DIR / f"{book_id}{source.suffix.lower()}"
    shutil.copy2(source, destination)

    book = {
        "id": book_id,
        "title": title.strip() if title and title.strip() else source.stem,
        "author": author.strip() or "Unknown",
        "path": str(destination),
        "format": source.suffix.lower().lstrip("."),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    books = list_books()
    books.append(book)
    _write_json(DATA_FILE, books)
    return book


def select_book(book_id: str) -> dict[str, str]:
    book = get_book(book_id)
    if book is None:
        raise ValueError("Book not found in the LIBRIS library.")
    _write_json(CURRENT_BOOK_FILE, {"book_id": book_id})
    return book


def get_current_book() -> dict[str, str] | None:
    current = _read_json(CURRENT_BOOK_FILE, {})
    return get_book(current.get("book_id", ""))


def import_inbox_books() -> list[dict[str, str]]:
    """Import supported files dropped into ``books/inbox`` once each."""
    ensure_library_folders()
    imported: list[dict[str, str]] = []
    for source in INBOX_DIR.iterdir():
        if not source.is_file() or source.suffix.lower() not in SUPPORTED_FORMATS:
            continue
        book = add_book(str(source))
        destination = IMPORTED_INBOX_DIR / source.name
        if destination.exists():
            destination = IMPORTED_INBOX_DIR / f"{book['id']}_{source.name}"
        shutil.move(str(source), str(destination))
        imported.append(book)
    return imported
