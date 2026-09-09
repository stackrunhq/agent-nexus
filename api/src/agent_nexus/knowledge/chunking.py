"""Deterministic character windows within source sections, never across pages."""

from dataclasses import dataclass

from agent_nexus.knowledge.parsing import ParsedDocument


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    source_kind: str
    source_index: int
    start: int
    end: int


def chunk_document(document: ParsedDocument, size: int = 1000, overlap: int = 150):
    """Offsets are Python character offsets in normalized section text, end exclusive."""
    if not 100 <= size <= 4000 or not 0 <= overlap <= size // 2:
        raise ValueError("Require 100 <= size <= 4000 and 0 <= overlap <= size / 2")
    chunks = []
    for section in document.sections:
        start = 0
        while start < len(section.text):
            end = min(start + size, len(section.text))
            chunks.append(Chunk(len(chunks), section.text[start:end], section.source_kind,
                                section.source_index, start, end))
            if end == len(section.text):
                break
            start = end - overlap
    return chunks
