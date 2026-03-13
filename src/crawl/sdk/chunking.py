"""Text chunking and query relevance helpers."""

import math
import re
from collections import Counter

WORD_RE = re.compile(r"[A-Za-z0-9_]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def tokenize_text(text: str) -> list[str]:
    """Tokenize text into lowercase word tokens.

    Args:
        text: Text to tokenize.

    Returns:
        Token list.
    """
    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def sentence_chunks(text: str) -> list[str]:
    """Chunk text by sentences.

    Args:
        text: Source text.

    Returns:
        Sentence chunk list.
    """
    parts = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def sliding_word_chunks(text: str, chunk_size: int = 120, overlap: int = 30) -> list[str]:
    """Chunk text with a sliding word window.

    Args:
        text: Source text.
        chunk_size: Words per chunk.
        overlap: Overlap between adjacent chunks.

    Returns:
        Sliding-window chunk list.
    """
    words = text.split()
    if not words:
        return []

    chunk_size = max(1, chunk_size)
    overlap = max(0, min(overlap, chunk_size - 1))
    step = max(1, chunk_size - overlap)

    chunks = []
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            continue
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


def chunk_text(
    text: str,
    strategy: str = "sentence",
    chunk_size: int = 120,
    overlap: int = 30,
) -> list[str]:
    """Chunk text using a named strategy.

    Args:
        text: Source text.
        strategy: ``sentence`` or ``sliding``.
        chunk_size: Words per chunk for sliding mode.
        overlap: Overlap between chunks for sliding mode.

    Returns:
        Chunk list.
    """
    if strategy == "sliding":
        return sliding_word_chunks(text, chunk_size=chunk_size, overlap=overlap)
    return sentence_chunks(text)


def score_text_chunk(chunk: str, query: str) -> float:
    """Score a text chunk against a query.

    Args:
        chunk: Candidate chunk.
        query: Query text.

    Returns:
        Relevance score.
    """
    query_tokens = tokenize_text(query)
    chunk_tokens = tokenize_text(chunk)
    if not query_tokens or not chunk_tokens:
        return 0.0

    chunk_counts = Counter(chunk_tokens)
    score = 0.0
    unique_chunk_tokens = len(set(chunk_tokens))

    for token in query_tokens:
        if token in chunk_counts:
            tf = chunk_counts[token] / len(chunk_tokens)
            density = chunk_counts[token] / max(1, unique_chunk_tokens)
            score += tf * 4.0 + density

    if query.lower() in chunk.lower():
        score += 2.0

    length_penalty = 1.0 / (1.0 + math.log(max(2, len(chunk_tokens))))
    return round(score * (1 + length_penalty), 6)


def rank_text_chunks(
    text: str,
    query: str,
    strategy: str = "sentence",
    chunk_size: int = 120,
    overlap: int = 30,
    top_k: int = 5,
) -> list[dict]:
    """Rank chunks from text against a query.

    Args:
        text: Source text.
        query: Query text.
        strategy: ``sentence`` or ``sliding``.
        chunk_size: Words per chunk for sliding mode.
        overlap: Overlap between chunks for sliding mode.
        top_k: Maximum ranked chunks to return.

    Returns:
        Ranked chunk payloads.
    """
    ranked = []
    for index, chunk in enumerate(chunk_text(text, strategy=strategy, chunk_size=chunk_size, overlap=overlap)):
        score = score_text_chunk(chunk, query)
        if score <= 0:
            continue
        ranked.append({"index": index, "score": score, "text": chunk})

    ranked.sort(key=lambda item: (item["score"], -item["index"]), reverse=True)
    return ranked[: max(1, top_k)]
