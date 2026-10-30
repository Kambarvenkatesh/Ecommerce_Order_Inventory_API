# E-Commerce Order & Inventory Management API

FastAPI + MySQL + SQLAlchemy 2.0 + Pydantic v2 + JWT (Admin / Customer roles).

## Requirements
- Python 3.10+
- MySQL 8.0.16+ (CHECK constraints are enforced from this version)

## Setup
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
Create the database:
```sql
CREATE DATABASE ecommerce_db CHARACTER SET utf8mb4;
```
Edit `.env` (set your MySQL password and a long random SECRET_KEY), then run:
```bash
uvicorn app.main:app --reload
```
Open Swagger UI: http://127.0.0.1:8000/docs  (tables are created automatically on startup)

## Swagger test flow
1. `POST /auth/register` twice: one `"role": "admin"`, one `"role": "customer"`.
2. Click **Authorize** (email in the username field + password).
3. Admin: `POST /categories`, `POST /products`.
4. Customer: search/filter/sort/paginate `GET /products`; `POST /products` -> 403.
5. Cart: `POST /cart/items`, `PUT /cart/items/{id}`, `DELETE /cart/items/{id}`, `GET /cart`.
6. Quantity above stock -> 400 insufficient stock.
7. `POST /orders` -> 201; stock reduced, cart cleared.
8. `POST /orders/{id}/cancel` -> stock restored; cancel again -> 400.
9. Another customer `GET /orders/{id}` -> 404.
10. Admin `PATCH /admin/orders/{id}/status`: Pending -> Confirmed -> Shipped -> Delivered; invalid jumps -> 400.
11. Invalid body -> 422; invalid token -> 401.
12. `GET /orders?status=Cancelled&date_from=2026-10-01&date_to=2026-10-31&page=1&limit=5`.

## Database relationships
- Category 1—N Product
- User 1—N CartItem (unique per user+product), CartItem N—1 Product
- User 1—N Order, Order 1—N OrderItem, OrderItem N—1 Product
- OrderItem is the join table between Orders and Products and stores quantity and `unit_price` (price snapshot).
- Constraints: unique email, price > 0, stock >= 0, quantity > 0, FK RESTRICT/CASCADE rules, timestamps.

## Business logic
- Totals and prices are always computed on the server from the database.
- Stock is validated when adding to cart and again when placing an order.
- Order status machine: Pending -> Confirmed -> Shipped -> Delivered; Pending/Confirmed -> Cancelled. Delivered and Cancelled are final.

## Transactions
`place_order` locks product rows with `SELECT ... FOR UPDATE` (ordered by id to avoid deadlocks), validates all stock, creates the order and items, deducts stock, clears the cart, then commits once. Any error triggers a rollback, so nothing is partially saved. Cancellation restores stock in the same transaction as the status change; the state machine guarantees stock is restored only once.

## Authorization
- JWT bearer tokens; passwords hashed with bcrypt.
- `get_current_user` -> 401 for missing/invalid/expired tokens.
- `require_admin` -> 403 for non-admins (product writes, category creation, `/admin/orders`).
- Customer order queries always filter by `user_id`; other users' orders return 404.

## Note
Role is selectable at registration only for demo purposes. Never allow this in production.

---

# File Upload Module

Authenticated users can upload PDF / JPG / PNG / DOCX files (max 5 MB). The file is stored in the
`uploads/` directory; only its metadata is stored in MySQL. Built into the existing project, reusing the
same database session, JWT dependency (`get_current_user`) and service layer.

## Setup (only what is new)
1. `python-multipart` is already listed in `requirements.txt` (needed by FastAPI for `UploadFile`).
   If you installed packages earlier: `pip install -r requirements.txt`.
2. No migration is needed. The new `uploaded_files` table is created automatically on startup
   (`Base.metadata.create_all`), and the `uploads/` folder is created automatically on the first upload.
3. Optional `.env` settings (defaults shown):
```
UPLOAD_DIR=uploads
MAX_UPLOAD_SIZE_MB=5
```
4. Run as before: `uvicorn app.main:app --reload`, then open http://127.0.0.1:8000/docs

## Project structure (new/changed files marked)
```
ecommerce_backend/
|-- .env
|-- .gitignore                  (NEW: ignores venv, .env and uploaded files)
|-- requirements.txt
|-- README.md                   (UPDATED)
|-- uploads/                    (NEW: uploaded files are saved here)
|   `-- .gitkeep
`-- app/
    |-- main.py                 (UPDATED: registers the files router)
    |-- config.py               (UPDATED: UPLOAD_DIR, MAX_UPLOAD_SIZE_MB)
    |-- database.py
    |-- deps.py                 (reused: get_current_user)
    |-- security.py
    |-- models.py               (UPDATED: UploadedFile model)
    |-- schemas.py              (UPDATED: FileOut schema)
    |-- routers/
    |   |-- files.py            (NEW: POST /files/upload, GET /files)
    |   `-- ...
    `-- services/
        |-- file_service.py     (NEW: validation, storage, metadata)
        `-- order_service.py
```

## API endpoints
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/files/upload` | JWT | Upload one file (multipart form field `file`) |
| GET | `/files` | JWT | List the logged-in user's own files (newest first) |

(Existing endpoints: `/auth/*`, `/categories`, `/products`, `/cart`, `/orders`, `/admin/orders`.)

## Database table: `uploaded_files`
| Column | Type | Notes |
|---|---|---|
| file_id | INT, PK, auto-increment | |
| original_filename | VARCHAR(255) | name sent by the client (folder parts removed) |
| stored_filename | VARCHAR(255), UNIQUE | `<uuid4 hex>.<ext>`, the real name on disk |
| file_path | VARCHAR(500) | e.g. `uploads/9f2c...e1.pdf` |
| content_type | VARCHAR(150) | derived from the validated extension |
| file_size | INT | bytes, must be > 0 |
| uploaded_by | INT, FK -> users.id, indexed | taken from the JWT, never from the request |
| created_at | DATETIME | server default `NOW()` |

## Validation and error responses
| Case | Status | Message |
|---|---|---|
| Missing / invalid / expired token | 401 | `Not authenticated` / `Invalid or expired token` |
| No file sent | 400 | `No file provided. Send the file in the 'file' form field` |
| Empty file | 400 | `Uploaded file is empty` |
| Unsupported type (.txt, .exe, .gif, no extension) | 415 | `Unsupported file type '.txt'. Allowed types: PDF, JPG, PNG, DOCX` |
| Content does not match extension (e.g. text renamed to .pdf) | 415 | `File content does not match the '.pdf' extension...` |
| File larger than 5 MB | 413 | `File too large. Maximum allowed size is 5 MB` |
| File cannot be written to disk | 500 | `Could not store the file on the server...` |
| Database error while saving | 500 | `Could not save the file information in the database...` (the stored file is deleted again) |
| Database error while listing | 500 | `Could not retrieve the file list from the database` |

Security notes:
- The type is checked by extension **and** by the file's first bytes (PDF `%PDF-`, JPG `FF D8 FF`, PNG signature, DOCX = ZIP containing `word/document.xml`), so a renamed file is rejected.
- The client's filename is never used on disk. Files are saved under a random UUID name, so path traversal (`../../x.pdf`) and name clashes are impossible. Files are opened in exclusive mode and can never overwrite another file.
- The size is enforced while reading (at most 5 MB + 1 byte is read), so an oversized file is detected without loading all of it.
- If the database save fails after the file was written, the file is removed so no orphan stays in `uploads/`.
- `GET /files` always filters by the authenticated user's id; other users' metadata is never returned.
- Note: the framework receives the whole request body before the size check runs. For production, also limit the request body size in the reverse proxy (for example `client_max_body_size 6m;` in nginx).

## Swagger test flow (file upload)
1. `POST /auth/register` two customers (for example `john@test.com`, `mary@test.com`), then **Authorize** as john.
2. `POST /files/upload` > Try it out > choose a small valid PDF/JPG/PNG/DOCX > Execute -> **201** with the metadata.
3. `GET /files` -> **200**, a list containing only john's files.
4. Invalid type: upload a `.txt` or `.exe` file -> **415**.
5. Oversized: upload any PDF/PNG/JPG/DOCX larger than 5 MB -> **413**.
6. Empty file: upload a 0-byte `empty.pdf` -> **400**.
7. Renamed file: rename `notes.txt` to `notes.pdf` and upload -> **415** (content check).
8. Unauthorized: click **Authorize** > **Logout**, then run `GET /files` -> **401** `{"detail":"Not authenticated"}`.
   Invalid token: authorize with the text `abc123` -> **401** `{"detail":"Invalid or expired token"}`.
9. Ownership: authorize as mary, `GET /files` -> only mary's files (john's are not visible).

Creating test files on Windows (PowerShell, run in any folder):
```powershell
New-Item empty.pdf -ItemType File                                   # 0-byte file
"just text" | Set-Content notes.txt                                  # unsupported type
Copy-Item notes.txt notes.pdf                                        # text disguised as PDF
$f = [IO.File]::Create("$PWD\big.pdf"); $f.SetLength(6MB); $f.Close()   # 6 MB file -> 413
```
Any real PDF/JPG/PNG/DOCX larger than 5 MB also works. The size check runs before the content check, so `big.pdf` returns 413.

## Verify in MySQL
```sql
USE ecommerce_db;
SHOW TABLES;                       -- uploaded_files is listed
DESCRIBE uploaded_files;
SELECT * FROM uploaded_files\G
SELECT file_id, original_filename, stored_filename, file_size, uploaded_by, created_at FROM uploaded_files;
```
Also open the `uploads/` folder: it contains the files with their UUID names.
