from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("", response_model=CategoryOut, status_code=201, dependencies=[Depends(require_admin)])
def create_category(body: CategoryCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Category).where(Category.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    cat = Category(name=body.name)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.name)).all()
