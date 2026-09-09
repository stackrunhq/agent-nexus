from io import BytesIO
import json
import sys
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from agent_nexus.knowledge.chunking import chunk_document
from agent_nexus.knowledge.parsing import DocumentError, parse_document
from agent_nexus_cli.document import main


def docx(xml):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


def pdf(text=True, encrypted=False):
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 100 Td (Hello manual) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("test-only-password")
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("extension", ["txt", "md", "TXT"])
def test_unicode_chunks_preserve_content_and_offsets(extension):
    original = "# 使用说明\r\n" + "企业操作流程。" * 60
    document = parse_document(f"manual.{extension}", original.encode("utf-8-sig"))
    chunks = chunk_document(document, 100, 20)
    normalized = original.replace("\r\n", "\n")
    restored = chunks[0].text + "".join(chunk.text[20:] for chunk in chunks[1:])
    assert restored == normalized
    for chunk in chunks:
        assert chunk.text == normalized[chunk.start:chunk.end]
        assert len(chunk.text) <= 100


def test_docx_paragraphs_and_table_cells_in_order():
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>开始</w:t><w:tab/><w:t>操作</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格内容</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    result = parse_document("manual.docx", docx(xml))
    assert [section.text for section in result.sections] == ["开始\t操作", "表格内容"]
    assert [chunk.source_index for chunk in chunk_document(result)] == [1, 2]


def test_pdf_page_sources_and_blank_page_warning():
    result = parse_document("manual.pdf", pdf())
    assert result.sections[0].text == "Hello manual"
    assert result.sections[0].source_kind == "page"
    assert result.sections[0].source_index == 1
    assert result.warnings == ("page_without_text:2",)


@pytest.mark.parametrize("name,content,code", [
    ("x.txt", b"", "empty_file"),
    ("x.exe", b"text", "unsupported_format"),
    ("x.txt", b"\xff", "unsupported_encoding"),
    ("x.txt", b"\x00", "invalid_text"),
    ("x.pdf", b"not a pdf", "invalid_document"),
    ("x.docx", b"not a zip", "invalid_document"),
    ("x.txt", b" " * 10, "no_extractable_text"),
])
def test_invalid_inputs(name, content, code):
    with pytest.raises(DocumentError, match=code):
        parse_document(name, content)


def test_blank_and_encrypted_pdf():
    with pytest.raises(DocumentError, match="no_extractable_text"):
        parse_document("x.pdf", pdf(text=False))
    with pytest.raises(DocumentError, match="encrypted_pdf"):
        parse_document("x.pdf", pdf(encrypted=True))


def test_limits_and_xml_entities(monkeypatch):
    from agent_nexus.knowledge import parsing
    monkeypatch.setattr(parsing, "MAX_FILE_BYTES", 10)
    with pytest.raises(DocumentError, match="file_too_large"):
        parse_document("x.txt", b"x" * 11)
    monkeypatch.setattr(parsing, "MAX_FILE_BYTES", 10000)
    monkeypatch.setattr(parsing, "MAX_TEXT_CHARS", 3)
    with pytest.raises(DocumentError, match="text_too_large"):
        parse_document("x.txt", b"abcd")
    with pytest.raises(DocumentError, match="invalid_document"):
        parse_document("x.docx", docx('<!DOCTYPE x [<!ENTITY test "secret">]><x>&test;</x>'))
    with pytest.raises(ValueError):
        chunk_document(parse_document("x.txt", b"abc"), 100, 99)


def test_cli_json_and_error(tmp_path, monkeypatch, capsys):
    path = tmp_path / "manual.txt"
    path.write_text("用户手册", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["nexus-document", str(path)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["chunks"][0]["text"] == "用户手册"
    assert len(result["sha256"]) == 64
    monkeypatch.setattr(sys, "argv", ["nexus-document", str(tmp_path / "missing.txt")])
    assert main() == 2
    assert json.loads(capsys.readouterr().err) == {"error": "invalid_input"}
