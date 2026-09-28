"""Book-grounded question answering for LIBRIS."""
from __future__ import annotations
import re
from dataclasses import dataclass

STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "that", "this", "to", "was", "what", "when", "where", "who", "why", "with", "you"}

@dataclass
class Passage:
    text: str
    start: int
    end: int
    score: int = 0

def _keywords(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z0-9']+", text) if len(word) > 2 and word.lower() not in STOP_WORDS}

def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[Passage]:
    clean = re.sub(r"\s+", " ", text).strip()
    passages, start = [], 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        if end < len(clean):
            end = clean.rfind(" ", start + chunk_size // 2, end) or end
        passages.append(Passage(clean[start:end].strip(), start, end))
        if end == len(clean): break
        start = max(end - overlap, start + 1)
    return passages

def find_relevant_passages(question: str, book_text: str, limit: int = 3) -> list[Passage]:
    terms = _keywords(question)
    matches = []
    for passage in chunk_text(book_text):
        passage.score = len(terms & _keywords(passage.text))
        if passage.score: matches.append(passage)
    return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]

def ask_about_book(question: str, book_text: str, book_title: str = "Selected book") -> str:
    """Answer with evidence from only the supplied selected book."""
    matches = find_relevant_passages(question, book_text)
    if not matches:
        return f"I could not find an answer to that in {book_title}. Try different words or another book."
    evidence = matches[0]
    return f"Here is the most relevant part I found in {book_title}:\n\n{evidence.text}\n\nSource: passage around character {evidence.start:,}."

def summarise_text(text: str, max_sentences: int = 3) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    chosen = [item for item in sentences if len(item.split()) >= 6][:max_sentences]
    return " ".join(chosen) or "There is not enough readable text to summarise."
