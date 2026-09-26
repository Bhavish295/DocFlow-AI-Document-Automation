from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    content_hash: str
    character_count: int


class TextChunker(Protocol):
    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into ordered overlapping chunks."""


def normalize_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ParagraphAwareChunker:
    def __init__(
        self,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.overlap = overlap if overlap is not None else settings.RAG_CHUNK_OVERLAP
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100 characters.")
        if self.overlap < 0 or self.overlap >= self.chunk_size:
            raise ValueError("overlap must be >= 0 and less than chunk_size.")

    def chunk_text(self, text: str) -> list[TextChunk]:
        normalized = normalize_whitespace(text or "")
        if not normalized:
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        if not paragraphs:
            paragraphs = [normalized]

        raw_chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= self.chunk_size:
                current = candidate
                continue
            if current:
                raw_chunks.append(current)
            if len(paragraph) <= self.chunk_size:
                current = paragraph
                continue
            raw_chunks.extend(self._split_long_block(paragraph))
            current = ""
        if current:
            raw_chunks.append(current)

        overlapped = self._apply_overlap(raw_chunks)
        chunks: list[TextChunk] = []
        seen_hashes: set[str] = set()
        for index, content in enumerate(overlapped):
            cleaned = content.strip()
            if not cleaned:
                continue
            digest = hash_content(cleaned)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=cleaned,
                    content_hash=digest,
                    character_count=len(cleaned),
                )
            )
        return chunks

    def _split_long_block(self, block: str) -> list[str]:
        parts: list[str] = []
        start = 0
        while start < len(block):
            end = min(start + self.chunk_size, len(block))
            if end < len(block):
                split_at = block.rfind(" ", start, end)
                if split_at > start + self.chunk_size // 2:
                    end = split_at
            piece = block[start:end].strip()
            if piece:
                parts.append(piece)
            if end >= len(block):
                break
            start = max(end - self.overlap, start + 1)
        return parts

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if not chunks or self.overlap == 0:
            return chunks
        result = [chunks[0]]
        for chunk in chunks[1:]:
            previous = result[-1]
            prefix = previous[-self.overlap :].strip()
            merged = f"{prefix}\n{chunk}".strip() if prefix else chunk
            result.append(merged)
        return result


def get_default_chunker() -> TextChunker:
    return ParagraphAwareChunker()
