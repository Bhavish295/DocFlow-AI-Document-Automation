"""Safe local file storage helpers for document uploads."""

from __future__ import annotations

from pathlib import Path
import re

from app.core.config import settings
from app.core.exceptions import AppError


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
}

EXTENSION_TO_FILE_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
}

# Common Content-Type values accepted per extension (best-effort; not sole trust).
ALLOWED_CONTENT_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/x-pdf", "binary/octet-stream", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
    ".csv": {"text/csv", "application/csv", "text/plain", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "image/jpg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "image/jpg", "application/octet-stream"},
}

_UNSAFE_NAME_RE = re.compile(r"[^\w.\- ()\[\]]+", re.UNICODE)


def ensure_upload_dir() -> Path:
    upload_dir = settings.upload_dir_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def is_allowed_extension(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


def resolve_file_type(filename: str) -> str:
    return EXTENSION_TO_FILE_TYPE[get_extension(filename)]


def sanitize_original_filename(filename: str | None) -> str:
    """Return a safe display filename. Never use the result as a filesystem path."""
    if not filename or not str(filename).strip():
        raise AppError("A file is required.", status_code=400)

    raw = str(filename).replace("\x00", "")
    # Reject absolute / UNC / drive paths and traversal before basename.
    if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", raw):
        raise AppError("Invalid filename.", status_code=400)
    if ".." in Path(raw).parts or ".." in raw.replace("\\", "/").split("/"):
        raise AppError("Invalid filename.", status_code=400)

    name = Path(raw).name.strip()
    if not name or name in {".", ".."}:
        raise AppError("Invalid filename.", status_code=400)
    if "/" in name or "\\" in name:
        raise AppError("Invalid filename.", status_code=400)

    cleaned = _UNSAFE_NAME_RE.sub("_", name).strip(" ._")
    if not cleaned:
        raise AppError("Invalid filename.", status_code=400)
    if len(cleaned) > 200:
        stem = Path(cleaned).stem[:180]
        suffix = Path(cleaned).suffix[:20]
        cleaned = f"{stem}{suffix}"
    if not is_allowed_extension(cleaned):
        raise AppError(
            "Unsupported file type. Allowed types: PDF, DOCX, XLSX, CSV, PNG, JPG, JPEG.",
            status_code=400,
        )
    return cleaned


def sniff_content_matches_extension(extension: str, header: bytes) -> bool:
    """Best-effort magic-byte check against the declared extension."""
    ext = extension.lower()
    sample = header[:16]
    if not sample:
        return False
    if ext == ".pdf":
        return sample.startswith(b"%PDF")
    if ext == ".png":
        return sample.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return sample.startswith(b"\xff\xd8\xff")
    if ext in {".docx", ".xlsx"}:
        return sample.startswith(b"PK")
    if ext == ".csv":
        # CSV is text — reject obvious binary signatures
        if sample.startswith((b"%PDF", b"\x89PNG", b"\xff\xd8\xff", b"PK")):
            return False
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                sample.decode("latin-1")
                return True
            except UnicodeDecodeError:
                return False
    return False


def validate_declared_content_type(extension: str, content_type: str | None) -> None:
    if not content_type:
        return
    media = content_type.split(";")[0].strip().lower()
    if not media or media == "*/*":
        return
    allowed = ALLOWED_CONTENT_TYPES.get(extension.lower(), set())
    if allowed and media not in allowed:
        raise AppError(
            "Declared content type does not match the file extension.",
            status_code=400,
        )


def validate_upload_header(extension: str, header: bytes, content_type: str | None = None) -> None:
    validate_declared_content_type(extension, content_type)
    if not sniff_content_matches_extension(extension, header):
        raise AppError(
            "File content does not match the declared file type.",
            status_code=400,
        )
