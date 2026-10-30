from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from app.models import OrderStatus, UserRole


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    # NOTE: role is selectable ONLY so you can create an admin from Swagger for the demo.
    # In production, never let users choose their own role.
    role: UserRole = UserRole.CUSTOMER


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Category ----------
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


# ---------- Product ----------
class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int = Field(ge=0)
    category_id: int


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int | None = Field(default=None, ge=0)
    category_id: int | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    price: Decimal
    stock_quantity: int
    category_id: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def in_stock(self) -> bool:
        return self.stock_quantity > 0


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    limit: int


# ---------- Cart ----------
class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=1000)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0, le=1000)


class CartItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal


class CartOut(BaseModel):
    items: list[CartItemOut]
    total: Decimal


# ---------- Orders ----------
class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    total_amount: Decimal
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]


class OrderPage(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    limit: int


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ---------- Files ----------
class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    file_id: int
    original_filename: str
    stored_filename: str
    file_path: str
    content_type: str
    file_size: int
    uploaded_by: int
    created_at: datetime
