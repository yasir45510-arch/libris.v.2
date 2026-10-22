"""Local, extractive summaries and book-grounded question answering."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

STOP_WORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and", "any", "are", "as", "at", "be", "because", "been", "before", "being", "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our", "out", "over", "own", "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "us", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with", "would", "you", "your",
}
_TOKEN_RE = re.compile(r"[\w]+(?:['’][\w]+)*", re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]+[\"'”’)]*|[^.!?\n]+")


@dataclass
class Passage:
    """A retrievable slice of the extracted book text."""

    text: str
    start: int
    end: int
    score: float = 0.0


def _normalise_token(word: str) -> str:
    word = word.lower().strip("'’")
    irregular = {
        "found": "find", "finds": "find", "finding": "find",
        "went": "go", "goes": "go", "gone": "go",
        "ran": "run", "runs": "run", "running": "run",
        "bought": "buy", "buys": "buy", "buying": "buy",
        "saw": "see", "seen": "see", "sees": "see",
    }
    if word in irregular:
        return irregular[word]
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        base = word[:-3]
        return base[:-1] if len(base) > 2 and base[-1] == base[-2] else base
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return [_normalise_token(word) for word in _TOKEN_RE.findall(text)]


def _keywords(text: str) -> set[str]:
    return {word for word in _tokens(text) if len(word) > 2 and word not in STOP_WORDS}


def _sentences(text: str) -> list[Passage]:
    sentences: list[Passage] = []
    for match in _SENTENCE_RE.finditer(text):
        raw = match.group()
        sentence = " ".join(raw.split())
        if not sentence:
            continue
        leading = len(raw) - len(raw.lstrip())
        start = match.start() + leading
        sentences.append(Passage(sentence, start, start + len(raw.rstrip())))
    return sentences


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[Passage]:
    """Split long extracted text into overlapping, searchable passages."""
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunk_size = max(100, chunk_size)
    overlap = min(max(0, overlap), chunk_size // 2)
    passages: list[Passage] = []
    start = 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        if end < len(clean):
            boundary = clean.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        passages.append(Passage(clean[start:end].strip(), start, end))
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return passages


def _ranked_passages(question: str, passages: list[Passage], limit: int) -> list[Passage]:
    terms = _keywords(question)
    if not terms or not passages:
        return []

    document_frequency: Counter[str] = Counter()
    passage_terms: list[set[str]] = []
    for passage in passages:
        words = _keywords(passage.text)
        passage_terms.append(words)
        document_frequency.update(words)

    total = len(passages)
    scored: list[Passage] = []
    for passage, words in zip(passages, passage_terms):
        matched = terms & words
        if not matched:
            continue
        weighted_match = sum(math.log1p((total + 1) / (document_frequency[word] + 1)) for word in matched)
        coverage = len(matched) / len(terms)
        passage.score = weighted_match * (0.5 + coverage)
        scored.append(passage)

    ranked = sorted(scored, key=lambda passage: (-passage.score, passage.start))
    selected: list[Passage] = []
    for candidate in ranked:
        if any(
            max(0, min(candidate.end, item.end) - max(candidate.start, item.start))
            / max(1, min(candidate.end - candidate.start, item.end - item.start))
            > 0.60
            for item in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= max(1, limit):
            break
    return selected


def find_relevant_passages(question: str, book_text: str, limit: int = 3) -> list[Passage]:
    """Return the strongest non-duplicate passages for a question."""
    return _ranked_passages(question, chunk_text(book_text), limit)


def _ranked_sentences(question: str, book_text: str, limit: int = 3) -> list[Passage]:
    terms = _keywords(question)
    sentences = [sentence for sentence in _sentences(book_text) if len(_keywords(sentence.text)) >= 2]
    if not terms or not sentences:
        return []

    word_frequency = Counter(_tokens(book_text))
    term_weights = {
        term: 1.0 + math.log1p((sum(word_frequency.values()) + 1) / (word_frequency[term] + 1))
        for term in terms
    }
    ranked: list[Passage] = []
    for sentence in sentences:
        words = _keywords(sentence.text)
        matched = terms & words
        if not matched or (len(terms) >= 3 and len(matched) < 2):
            continue
        coverage = len(matched) / len(terms)
        length_norm = math.sqrt(max(8, len(words)))
        sentence.score = sum(term_weights[term] for term in matched) * (0.55 + coverage) / length_norm
        ranked.append(sentence)

    ranked.sort(key=lambda sentence: (-sentence.score, sentence.start))
    return sorted(ranked[: max(1, limit)], key=lambda sentence: sentence.start)


def ask_about_book(question: str, book_text: str, book_title: str = "Selected book") -> str:
    """Find and quote evidence from only the supplied selected book."""
    if not _keywords(question):
        return "Please ask a question about a person, place, event, or idea in the selected book."

    evidence = _ranked_sentences(question, book_text, limit=3)
    if not evidence:
        return (
            f"I couldn't find supporting text for that question in {book_title}, "
            "so I don't want to guess. Try a name, place, or phrase from the book."
        )

    excerpts = []
    for index, passage in enumerate(evidence, 1):
        percent = round(passage.start / max(1, len(book_text)) * 100)
        excerpts.append(f"{index}. “{passage.text}”\n   (around {percent}% through the extracted text)")
    return (
        f"Relevant text from {book_title}:\n\n"
        + "\n\n".join(excerpts)
        + "\n\nThese are direct excerpts from your selected book. If they don't answer the question explicitly, the book may not state it."
    )


def summarise_text(text: str, max_sentences: int = 5) -> str:
    """Build a compact extractive summary using important sentences across the book."""
    candidates = [sentence for sentence in _sentences(text) if len(_tokens(sentence.text)) >= 6]
    if not candidates:
        return "There isn't enough readable text in this book to create a summary."

    count = min(max(1, max_sentences), len(candidates))
    frequencies = Counter(word for sentence in candidates for word in _keywords(sentence.text))
    scored: list[tuple[int, float, str]] = []
    for index, sentence in enumerate(candidates):
        words = _keywords(sentence.text)
        if not words:
            continue
        # Frequent content words indicate the book's recurring topics. Length normalization
        # prevents a long sentence from winning just because it contains more words.
        score = sum(math.log1p(frequencies[word]) for word in words) / math.sqrt(len(words))
        scored.append((index, score, sentence.text))

    if not scored:
        return "There isn't enough readable text in this book to create a summary."
    if len(scored) <= count:
        chosen = scored
    else:
        buckets: list[list[tuple[int, float, str]]] = [[] for _ in range(count)]
        for item in scored:
            bucket = min(item[0] * count // len(candidates), count - 1)
            buckets[bucket].append(item)
        chosen = []
        for bucket_index, bucket in enumerate(buckets):
            if not bucket:
                continue
            tie_break = (lambda item: (item[1], item[0])) if bucket_index == count - 1 else (lambda item: (item[1], -item[0]))
            chosen.append(max(bucket, key=tie_break))

    chosen.sort(key=lambda item: item[0])
    return "\n\n".join(f"{index}. {sentence}" for index, (_position, _score, sentence) in enumerate(chosen, 1))
