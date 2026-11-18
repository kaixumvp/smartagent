from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .textutil import tokenize


@dataclass
class ParseResult:
    markdown: str
    parser_name: str
    ocr_used: bool = False


class OcrEngine:
    def transcribe(self, image_bytes: bytes, filename: str = "") -> str:
        raise NotImplementedError


class NullOcr(OcrEngine):
    def transcribe(self, image_bytes: bytes, filename: str = "") -> str:
        return ""


class CallableOcr(OcrEngine):
    def __init__(self, fn) -> None:
        self.fn = fn

    def transcribe(self, image_bytes: bytes, filename: str = "") -> str:
        return self.fn(image_bytes, filename)


class TesseractOcr(OcrEngine):
    """pytesseract-backed OCR; requires the `ocr` extra and a system tesseract binary."""

    def __init__(self, lang: str = "chi_sim+eng") -> None:
        self.lang = lang

    def transcribe(self, image_bytes: bytes, filename: str = "") -> str:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang=self.lang) or ""


def build_ocr(backend: str) -> OcrEngine:
    if backend in ("", "none"):
        return NullOcr()
    if backend == "tesseract":
        return TesseractOcr(settings.ocr_lang)
    raise ValueError(f"unknown OCR backend: {backend}")


def sniff_kind(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    ctype = (content_type or "").lower()
    if suffix in {".md", ".markdown"} or "markdown" in ctype:
        return "markdown"
    if suffix in {".txt", ".log", ".csv"} or ctype.startswith("text/plain"):
        return "text"
    if suffix == ".pdf" or "pdf" in ctype:
        return "pdf"
    if suffix in {".docx"} or "wordprocessingml" in ctype:
        return "docx"
    if suffix in {".xlsx", ".xlsm"} or "spreadsheetml" in ctype:
        return "xlsx"
    if suffix in {".pptx"} or "presentationml" in ctype:
        return "pptx"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"} or ctype.startswith("image/"):
        return "image"
    return "binary"


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"## Page {i}\n\n{text.strip()}")
    return "\n\n".join(pages).strip()


def _docx_text(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def _xlsx_text(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sections = []
    for sheet in wb.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells))
        body = "\n".join(rows)
        sections.append(f"## {sheet.title}\n\n{body}")
    return "\n\n".join(sections)


def _pptx_text(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        bits = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                bits.append(shape.text.strip())
        slides.append(f"## Slide {i}\n\n" + "\n\n".join(bits))
    return "\n\n".join(slides)


def parse_bytes(
    filename: str,
    content_type: str,
    data: bytes,
    ocr: OcrEngine | None = None,
) -> ParseResult:
    ocr = ocr or NullOcr()
    kind = sniff_kind(filename, content_type)
    ocr_used = False

    if kind == "markdown":
        return ParseResult(_decode_text(data), "markdown")
    if kind == "text":
        text = _decode_text(data)
        return ParseResult(f"# {Path(filename).name}\n\n{text}", "text")
    if kind == "pdf":
        text = _pdf_text(data)
        if len(tokenize(text)) < 12:
            ocr_text = ocr.transcribe(data, filename)
            if ocr_text.strip():
                ocr_used = True
                text = ocr_text
            elif not text.strip():
                text = f"*[PDF had no extractable text; OCR backend returned empty]*"
        return ParseResult(f"# {Path(filename).name}\n\n{text}", "pdf", ocr_used)
    if kind == "docx":
        return ParseResult(f"# {Path(filename).name}\n\n{_docx_text(data)}", "docx")
    if kind == "xlsx":
        return ParseResult(f"# {Path(filename).name}\n\n{_xlsx_text(data)}", "xlsx")
    if kind == "pptx":
        return ParseResult(f"# {Path(filename).name}\n\n{_pptx_text(data)}", "pptx")
    if kind == "image":
        text = ocr.transcribe(data, filename).strip()
        ocr_used = bool(text)
        if not text:
            text = "*[OCR unavailable or returned empty]*"
        return ParseResult(f"# {Path(filename).name}\n\n{text}", "image", ocr_used)

    return ParseResult(
        f"# {Path(filename).name}\n\n*[Unsupported binary; stored original only]*",
        "binary",
    )
