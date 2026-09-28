"""Book text extraction and persistent reading progress."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from library.book_manager import PROJECT_ROOT


PROGRESS_DIR = PROJECT_ROOT / "data" / "progress"


def read_book(path: str) -> str:
    """Extract readable text from a TXT, PDF, or EPUB file."""
    book = Path(path)
    extension = book.suffix.lower()
    if extension == ".txt":
        return book.read_text(encoding="utf-8", errors="replace")
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("PDF support needs pypdf. Run pip install -r requirements.txt.") from error
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(book).pages)
    if extension == ".epub":
        try:
            from bs4 import BeautifulSoup
            from ebooklib import ITEM_DOCUMENT, epub
        except ImportError as error:
            raise RuntimeError("EPUB support needs EbookLib and beautifulsoup4.") from error
        epub_book = epub.read_epub(str(book))
        return "\n\n".join(
            BeautifulSoup(item.get_content(), "html.parser").get_text(" ", strip=True)
            for item in epub_book.get_items_of_type(ITEM_DOCUMENT)
        )
    raise ValueError("Unsupported book format.")


def split_paragraphs(text: str, max_chars: int = 950) -> list[str]:
    """Return reader-friendly paragraphs, breaking very long EPUB/PDF blocks."""
    raw_paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    paragraphs: list[str] = []
    for paragraph in raw_paragraphs:
        if len(paragraph) <= max_chars:
            paragraphs.append(paragraph)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            if current and len(current) + len(sentence) + 1 > max_chars:
                paragraphs.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            paragraphs.append(current)
    return paragraphs


def _progress_path(book_id: str) -> Path:
    return PROGRESS_DIR / f"{book_id}.json"


def get_progress(book_id: str) -> dict[str, Any]:
    try:
        return json.loads(_progress_path(book_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"book_id": book_id, "paragraph_index": 0, "progress_percent": 0.0}


def save_progress(book_id: str, paragraph_index: int, total_paragraphs: int) -> dict[str, Any]:
    """Save progress after a paragraph so a user can resume safely."""
    total = max(total_paragraphs, 1)
    progress = {
        "book_id": book_id,
        "paragraph_index": max(0, paragraph_index),
        "progress_percent": round(min(paragraph_index / total * 100, 100), 1),
        "last_read_at": datetime.now(timezone.utc).isoformat(),
    }
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    _progress_path(book_id).write_text(json.dumps(progress, indent=2), encoding="utf-8")
    return progress
