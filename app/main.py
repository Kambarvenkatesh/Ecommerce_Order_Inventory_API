from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import Base, engine
from app.routers import auth, cart, categories, files, orders, products

Base.metadata.create_all(bind=engine)  # creates tables on startup

app = FastAPI(title="E-Commerce Order & Inventory API", version="1.0.0")

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(orders.admin_router)
app.include_router(files.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Database constraint violated"})


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(status_code=500, content={"detail": "Internal database error"})


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok"}
