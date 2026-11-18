import io

from app.parse import NullOcr, parse_bytes, sniff_kind


def _docx_bytes():
    import docx

    document = docx.Document()
    document.add_paragraph("Quarterly report")
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _xlsx_bytes():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Value"])
    ws.append(["Revenue", "42"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pptx_bytes():
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(0, 0, 100, 50)
    box.text_frame.text = "Quarterly slide"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _pdf_bytes():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_sniff_kind():
    assert sniff_kind("a.pdf", "") == "pdf"
    assert sniff_kind("a.docx", "") == "docx"
    assert sniff_kind("a.PPTX", "") == "pptx"
    assert sniff_kind("a.xlsx", "spreadsheetml") == "xlsx"
    assert sniff_kind("a.png", "") == "image"
    assert sniff_kind("a.md", "") == "markdown"
    assert sniff_kind("a.txt", "text/plain") == "text"
    assert sniff_kind("a.bin", "") == "binary"


def test_parse_markdown():
    result = parse_bytes("a.md", "text/markdown", b"# Hi\n\nbody")
    assert result.parser_name == "markdown"
    assert "Hi" in result.markdown
    assert not result.ocr_used


def test_parse_text_wraps_filename():
    result = parse_bytes("note.txt", "text/plain", "hello".encode())
    assert result.parser_name == "text"
    assert result.markdown.startswith("# note.txt")


def test_parse_docx():
    result = parse_bytes("report.docx", "", _docx_bytes())
    assert result.parser_name == "docx"
    assert "Quarterly report" in result.markdown


def test_parse_xlsx():
    result = parse_bytes("data.xlsx", "", _xlsx_bytes())
    assert result.parser_name == "xlsx"
    assert "Revenue" in result.markdown
    assert "42" in result.markdown


def test_parse_pptx():
    result = parse_bytes("deck.pptx", "", _pptx_bytes())
    assert result.parser_name == "pptx"
    assert "Quarterly slide" in result.markdown


def test_parse_scan_pdf_uses_ocr_when_available():
    class FakeOcr(NullOcr):
        def transcribe(self, image_bytes, filename=""):
            return "OCR extracted text"

    result = parse_bytes("scan.pdf", "application/pdf", _pdf_bytes(), FakeOcr())
    assert result.parser_name == "pdf"
    assert result.ocr_used is True
    assert "OCR extracted text" in result.markdown


def test_parse_blank_pdf_without_ocr_does_not_crash():
    result = parse_bytes("scan.pdf", "application/pdf", _pdf_bytes(), NullOcr())
    assert result.parser_name == "pdf"
    assert not result.ocr_used


def test_parse_image_without_ocr():
    result = parse_bytes("img.png", "image/png", b"\x89PNGfake", NullOcr())
    assert result.parser_name == "image"
    assert "OCR unavailable" in result.markdown


def test_parse_unsupported_binary():
    result = parse_bytes("x.bin", "application/octet-stream", b"\x00\x01")
    assert result.parser_name == "binary"
    assert "Unsupported binary" in result.markdown
