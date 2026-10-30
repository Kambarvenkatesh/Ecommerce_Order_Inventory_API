"""File upload logic: validate -> store on disk -> save metadata in MySQL."""
import io
import logging
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UploadedFile, User

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

# extension -> content type we store (never trust the client-sent Content-Type)
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# extension -> first bytes a genuine file of that type must start with
SIGNATURES = {
    ".pdf": b"%PDF-",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".docx": b"PK\x03\x04",  # DOCX is a ZIP archive
}


def upload_dir() -> Path:
    path = Path(settings.UPLOAD_DIR)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _clean_filename(name: str | None) -> str:
    """Keep only the base name (strips any folder parts such as ../../) and control characters."""
    name = PurePosixPath((name or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if len(name) > 255:
        ext = Path(name).suffix
        name = name[: 255 - len(ext)] + ext
    return name


def _is_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def read_and_validate(file: UploadFile) -> tuple[str, str, bytes]:
    """Returns (original_filename, extension, content) or raises an HTTPException."""
    original = _clean_filename(file.filename)
    if not original:
        raise HTTPException(400, "File name is missing")

    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type '{ext or 'none'}'. Allowed types: PDF, JPG, PNG, DOCX",
        )

    # read at most limit+1 bytes, so an oversized file is detected without loading all of it
    data = file.file.read(MAX_FILE_SIZE + 1)
    if len(data) == 0:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Maximum allowed size is {settings.MAX_UPLOAD_SIZE_MB} MB")

    if not data.startswith(SIGNATURES[ext]) or (ext == ".docx" and not _is_docx(data)):
        raise HTTPException(415, f"File content does not match the '{ext}' extension. The file may be corrupted or renamed")

    return original, ext, data


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove file %s", path)


def save_uploaded_file(db: Session, user: User, file: UploadFile) -> UploadedFile:
    original, ext, data = read_and_validate(file)

    stored_filename = f"{uuid.uuid4().hex}{ext}"  # unique name; the client's name is never used on disk
    directory = upload_dir()
    destination = directory / stored_filename

    # 1) store the file on disk
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with open(destination, "xb") as out:  # "x" = fail instead of overwrite
            out.write(data)
    except OSError:
        logger.exception("Could not write upload to %s", destination)
        _remove_quietly(destination)
        raise HTTPException(500, "Could not store the file on the server. Please try again later")

    # 2) store its metadata; if that fails, remove the file again so no orphan stays on disk
    record = UploadedFile(
        original_filename=original,
        stored_filename=stored_filename,
        file_path=(Path(settings.UPLOAD_DIR) / stored_filename).as_posix(),
        content_type=ALLOWED_TYPES[ext],
        file_size=len(data),
        uploaded_by=user.id,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError:
        db.rollback()
        _remove_quietly(destination)
        logger.exception("Could not save file metadata")
        raise HTTPException(500, "Could not save the file information in the database. The upload was not completed")
    return record


def list_user_files(db: Session, user: User) -> list[UploadedFile]:
    try:
        return list(db.scalars(
            select(UploadedFile)
            .where(UploadedFile.uploaded_by == user.id)  # only the caller's own files
            .order_by(UploadedFile.created_at.desc(), UploadedFile.file_id.desc())
        ))
    except SQLAlchemyError:
        logger.exception("Could not list files")
        raise HTTPException(500, "Could not retrieve the file list from the database")
