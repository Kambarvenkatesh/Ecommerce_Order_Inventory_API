from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Category, Product
from app.schemas import ProductCreate, ProductOut, ProductPage, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductPage)
def list_products(
    search: str | None = Query(None, description="Search in name/description"),
    category_id: int | None = None,
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    in_stock: bool | None = None,
    sort_by: Literal["name", "price", "created_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Product)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Product.name.like(like) | Product.description.like(like))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if in_stock is True:
        stmt = stmt.where(Product.stock_quantity > 0)
    elif in_stock is False:
        stmt = stmt.where(Product.stock_quantity == 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = getattr(Product, sort_by)
    stmt = stmt.order_by(col.asc() if order == "asc" else col.desc(), Product.id)
    items = db.scalars(stmt.offset((page - 1) * limit).limit(limit)).all()
    return ProductPage(items=items, total=total, page=page, limit=limit)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(require_admin)])
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    if not db.get(Category, body.category_id):
        raise HTTPException(404, "Category not found")
    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut, dependencies=[Depends(require_admin)])
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data and not db.get(Category, data["category_id"]):
        raise HTTPException(404, "Category not found")
    for key, value in data.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Product is part of existing orders and cannot be deleted")
