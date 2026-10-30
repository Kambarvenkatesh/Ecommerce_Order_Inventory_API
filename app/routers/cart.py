from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import CartItem, Product, User
from app.schemas import CartItemCreate, CartItemUpdate, CartOut, CartItemOut

router = APIRouter(prefix="/cart", tags=["Cart"])


def _build_cart(db: Session, user: User) -> CartOut:
    rows = db.scalars(
        select(CartItem).options(selectinload(CartItem.product))
        .where(CartItem.user_id == user.id).order_by(CartItem.id)
    ).all()
    items = [
        CartItemOut(
            id=r.id, product_id=r.product_id, product_name=r.product.name,
            unit_price=r.product.price, quantity=r.quantity,
            subtotal=r.product.price * r.quantity,
        )
        for r in rows
    ]
    return CartOut(items=items, total=sum((i.subtotal for i in items), Decimal("0.00")))


def _check_stock(product: Product, wanted: int):
    if wanted > product.stock_quantity:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Insufficient stock for '{product.name}': requested {wanted}, available {product.stock_quantity}",
        )


@router.get("", response_model=CartOut)
def view_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_cart(db, user)


@router.post("/items", response_model=CartOut, status_code=201)
def add_to_cart(body: CartItemCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.get(Product, body.product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    item = db.scalar(select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == body.product_id))
    new_qty = body.quantity + (item.quantity if item else 0)
    _check_stock(product, new_qty)
    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(user_id=user.id, product_id=body.product_id, quantity=body.quantity))
    db.commit()
    return _build_cart(db, user)


@router.put("/items/{item_id}", response_model=CartOut)
def update_cart_item(item_id: int, body: CartItemUpdate, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id))
    if not item:
        raise HTTPException(404, "Cart item not found")
    _check_stock(db.get(Product, item.product_id), body.quantity)
    item.quantity = body.quantity
    db.commit()
    return _build_cart(db, user)


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_cart_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id))
    if not item:
        raise HTTPException(404, "Cart item not found")
    db.delete(item)
    db.commit()
    return _build_cart(db, user)
