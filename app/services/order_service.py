from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CartItem, Order, OrderItem, OrderStatus, Product, User

# Allowed status transitions (state machine)
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def _lock_products(db: Session, ids: list[int]) -> dict[int, Product]:
    """Lock product rows (SELECT ... FOR UPDATE) in id order to avoid deadlocks."""
    stmt = (
        select(Product).where(Product.id.in_(sorted(set(ids)))).order_by(Product.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    return {p.id: p for p in db.scalars(stmt)}


def place_order(db: Session, user: User) -> Order:
    cart_items = db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all()
    if not cart_items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cart is empty")

    try:
        products = _lock_products(db, [ci.product_id for ci in cart_items])

        # 1. Validate stock for EVERY item before changing anything
        problems = []
        for ci in cart_items:
            p = products.get(ci.product_id)
            if p is None:
                problems.append(f"Product {ci.product_id} no longer exists")
            elif p.stock_quantity < ci.quantity:
                problems.append(f"'{p.name}': requested {ci.quantity}, available {p.stock_quantity}")
        if problems:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                detail={"message": "Insufficient stock", "items": problems})

        # 2. Create order + items, deduct stock, compute total (server-side prices)
        order = Order(user_id=user.id, status=OrderStatus.PENDING, total_amount=Decimal("0.00"))
        total = Decimal("0.00")
        for ci in cart_items:
            p = products[ci.product_id]
            p.stock_quantity -= ci.quantity
            order.items.append(OrderItem(product_id=p.id, quantity=ci.quantity, unit_price=p.price))
            total += p.price * ci.quantity
            db.delete(ci)  # 3. clear cart
        order.total_amount = total
        db.add(order)

        db.commit()  # everything succeeds together...
        db.refresh(order)
        return order
    except Exception:
        db.rollback()  # ...or nothing is saved
        raise


def transition_order(db: Session, order_id: int, new_status: OrderStatus, owner_id: int | None = None) -> Order:
    """Change status. owner_id is set for customers so they can only touch their own orders."""
    stmt = select(Order).where(Order.id == order_id).with_for_update().execution_options(populate_existing=True)
    if owner_id is not None:
        stmt = stmt.where(Order.user_id == owner_id)
    order = db.scalar(stmt)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    if new_status not in ALLOWED_TRANSITIONS[order.status]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot change order from {order.status.value} to {new_status.value}",
        )

    try:
        if new_status == OrderStatus.CANCELLED:
            products = _lock_products(db, [i.product_id for i in order.items])
            for item in order.items:
                products[item.product_id].stock_quantity += item.quantity  # restore stock (once: status guard)
        order.status = new_status
        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise
