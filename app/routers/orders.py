from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Order, OrderStatus, User
from app.schemas import OrderOut, OrderPage, OrderStatusUpdate
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders (Customer)"])
admin_router = APIRouter(prefix="/admin/orders", tags=["Orders (Admin)"], dependencies=[Depends(require_admin)])


def _list_orders(db: Session, user_id: int | None, status: OrderStatus | None,
                 date_from: date | None, date_to: date | None, page: int, limit: int) -> OrderPage:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from must be on or before date_to")
    stmt = select(Order)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    if date_from:
        stmt = stmt.where(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (stmt.options(selectinload(Order.items)).order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * limit).limit(limit))
    return OrderPage(items=db.scalars(stmt).all(), total=total, page=page, limit=limit)


# ---------------- Customer ----------------
@router.post("", response_model=OrderOut, status_code=201)
def place_order(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return order_service.place_order(db, user)


@router.get("", response_model=OrderPage)
def my_orders(
    status: OrderStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _list_orders(db, user.id, status, date_from, date_to, page, limit)


@router.get("/{order_id}", response_model=OrderOut)
def get_my_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).options(selectinload(Order.items))
                      .where(Order.id == order_id, Order.user_id == user.id))
    if not order:  # 404 (not 403) so we don't reveal that someone else's order exists
        raise HTTPException(404, "Order not found")
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_my_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return order_service.transition_order(db, order_id, OrderStatus.CANCELLED, owner_id=user.id)


# ---------------- Admin ----------------
@admin_router.get("", response_model=OrderPage)
def all_orders(
    status: OrderStatus | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return _list_orders(db, user_id, status, date_from, date_to, page, limit)


@admin_router.get("/{order_id}", response_model=OrderOut)
def admin_get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@admin_router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(order_id: int, body: OrderStatusUpdate, db: Session = Depends(get_db)):
    return order_service.transition_order(db, order_id, body.status)
