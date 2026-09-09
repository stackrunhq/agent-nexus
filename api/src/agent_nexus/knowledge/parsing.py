"""Offline parsers. No database, network, or filesystem writes."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile

from defusedxml import ElementTree
from pypdf import PdfReader

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_PAGES = 500
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(ValueError):
    """Stable, content-free failure suitable for CLI and future job status."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Section:
    text: str
    source_kind: str
    source_index: int


@dataclass(frozen=True)
class ParsedDocument:
    sections: tuple[Section, ...]
    warnings: tuple[str, ...] = ()


def parse_document(filename: str, content: bytes) -> ParsedDocument:
    if not content:
        raise DocumentError("empty_file")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentError("file_too_large")
    extension = PurePath(filename).suffix.lower()
    if extension not in {".txt", ".md", ".pdf", ".docx"}:
        raise DocumentError("unsupported_format")
    sections = []
    warnings = []
    total = 0

    def add(text: str, kind: str, index: int):
        nonlocal total
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        total += len(text)
        if total > MAX_TEXT_CHARS:
            raise DocumentError("text_too_large")
        if text.strip():
            sections.append(Section(text, kind, index))

    try:
        if extension in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise DocumentError("invalid_text")
            add(text, "document", 1)
        elif extension == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise DocumentError("invalid_document")
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DocumentError("encrypted_pdf")
            if len(reader.pages) > MAX_PAGES:
                raise DocumentError("too_many_pages")
            for index, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                add(text, "page", index)
                if not text.strip():
                    warnings.append(f"page_without_text:{index}")
        else:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(e.file_size for e in entries) > 50 * 1024 * 1024:
                    raise DocumentError("archive_too_large")
                names = [e.filename for e in entries]
                if len(names) != len(set(names)):
                    raise DocumentError("invalid_document")
                info = archive.getinfo("word/document.xml")
                if info.file_size > 10 * 1024 * 1024:
                    raise DocumentError("text_too_large")
                root = ElementTree.fromstring(archive.read(info))
                body = root.find(f"{WORD_NS}body")
                if body is None:
                    raise DocumentError("invalid_document")
                for index, paragraph in enumerate(body.iter(f"{WORD_NS}p"), 1):
                    parts = []
                    for node in paragraph.iter():
                        if node.tag == f"{WORD_NS}t":
                            parts.append(node.text or "")
                        elif node.tag == f"{WORD_NS}tab":
                            parts.append("\t")
                        elif node.tag in {f"{WORD_NS}br", f"{WORD_NS}cr"}:
                            parts.append("\n")
                    add("".join(parts), "paragraph", index)
    except DocumentError:
        raise
    except UnicodeDecodeError:
        raise DocumentError("unsupported_encoding") from None
    except Exception:
        raise DocumentError("invalid_document") from None
    if not sections:
        raise DocumentError("no_extractable_text")
    return ParsedDocument(tuple(sections), tuple(warnings))
