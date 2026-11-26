from __future__ import annotations

from pathlib import Path
import shutil

from PIL import Image, ImageOps
from pypdf import PdfReader
import pypdfium2 as pdfium
import pytesseract

from app.core.config import settings
from app.core.exceptions import AppError


PROCESSABLE_FILE_TYPES = {"pdf", "png", "jpg", "jpeg"}
IMAGE_FILE_TYPES = {"png", "jpg", "jpeg"}


class TextExtractionError(Exception):
    pass


def configure_tesseract() -> None:
    candidates: list[str] = []
    configured = (settings.TESSERACT_CMD or "").strip().strip('"').strip("'")
    if configured:
        candidates.append(configured)
    which = shutil.which("tesseract")
    if which:
        candidates.append(which)
    candidates.append(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and path.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(path)
            return


def clean_text(value: str) -> str:
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned = "\n".join(lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


OCR_MIN_WIDTH = 1800
OCR_MAX_UPSCALE = 3.0


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Grayscale + contrast stretch + upscale small images.

    Tesseract misreads small, low-resolution text (e.g. 900px-wide screenshots), so
    images narrower than OCR_MIN_WIDTH are enlarged before recognition.
    """
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    if 0 < gray.width < OCR_MIN_WIDTH:
        scale = min(OCR_MAX_UPSCALE, OCR_MIN_WIDTH / gray.width)
        gray = gray.resize(
            (round(gray.width * scale), round(gray.height * scale)),
            Image.LANCZOS,
        )
    return gray


def ocr_image(image: Image.Image) -> str:
    configure_tesseract()
    try:
        raw = pytesseract.image_to_string(preprocess_for_ocr(image), lang=settings.OCR_LANGUAGE)
    except pytesseract.TesseractNotFoundError as exc:
        raise TextExtractionError(
            "Tesseract OCR is not installed or TESSERACT_CMD is not configured correctly."
        ) from exc
    except Exception as exc:
        raise TextExtractionError(f"OCR failed: {exc}") from exc
    return clean_text(raw)


def ocr_image_file(path: Path) -> str:
    try:
        with Image.open(path) as image:
            return ocr_image(image.convert("RGB"))
    except TextExtractionError:
        raise
    except Exception as exc:
        raise TextExtractionError(f"Unable to read image for OCR: {exc}") from exc


def extract_selectable_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            cleaned = clean_text(page_text)
            if cleaned:
                pages.append(f"--- Page {index} ---\n{cleaned}")
        return "\n\n".join(pages).strip()
    except Exception as exc:
        raise TextExtractionError(f"PDF text extraction failed: {exc}") from exc


def ocr_pdf_pages(path: Path) -> str:
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as exc:
        raise TextExtractionError(f"Unable to open PDF for OCR: {exc}") from exc

    if len(pdf) == 0:
        raise TextExtractionError("PDF has no pages to process.")

    pages: list[str] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            page_text = ocr_image(image)
            if page_text:
                pages.append(f"--- Page {index + 1} ---\n{page_text}")
    finally:
        pdf.close()

    return "\n\n".join(pages).strip()


def extract_pdf_text(path: Path) -> str:
    selectable = extract_selectable_pdf_text(path)
    if len(selectable) >= settings.PDF_TEXT_MIN_CHARS:
        return selectable
    ocr_text = ocr_pdf_pages(path)
    if ocr_text:
        return ocr_text
    if selectable:
        return selectable
    raise TextExtractionError("No readable text could be extracted from the PDF.")


def extract_text_from_file(path: Path, file_type: str) -> str:
    normalized = file_type.lower()
    if normalized not in PROCESSABLE_FILE_TYPES:
        raise AppError(
            "Text extraction is only supported for PDF, PNG, JPG, and JPEG files.",
            status_code=400,
        )

    if not path.exists() or not path.is_file():
        raise TextExtractionError("Stored document file was not found on disk.")

    if normalized == "pdf":
        return extract_pdf_text(path)
    return ocr_image_file(path)
