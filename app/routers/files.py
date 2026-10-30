from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import FileOut
from app.services import file_service

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileOut, status_code=201)
def upload_file(
    file: UploadFile | None = File(default=None, description="PDF, JPG, PNG or DOCX, max 5 MB"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file is None:
        raise HTTPException(400, "No file provided. Send the file in the 'file' form field")
    return file_service.save_uploaded_file(db, user, file)


@router.get("", response_model=list[FileOut])
def list_my_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return file_service.list_user_files(db, user)
