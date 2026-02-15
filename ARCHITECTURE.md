# Read it and Weep — Architecture (Current MVP)

## High-level architecture

### Components (current)
1. **Vanilla Frontend (static assets)**
   - `public/index.html`, `public/app.js`, `public/receipt.html`, `public/receipt.js`
   - Calls backend API with `fetch`.
2. **Python Cloudflare Worker**
   - Single file: `src/worker.py`
   - Handles upload, validates images, issues IDs.
   - Serves images and logs accesses.
   - Provides receipts API with pagination.
3. **D1 Database (SQLite)**
   - Stores image metadata + receipt events.
   - Stores image bytes as base64 in a `TEXT` column for MVP (no R2 yet).

### Request flow (happy path)
1. User uploads an image on `/`.
2. Frontend `POST /api/images` with multipart form-data.
3. Backend:
   - validates type/size
   - generates `image_id` and `receipt_id`
   - stores image bytes in D1 (base64)
   - inserts row in `images`
4. Backend returns `{ imageUrl, receiptUrl }`.
5. Anyone opens `GET /image/{image_id}.{ext}`:
   - backend logs an event to `receipts`
   - backend serves image (or redirects to signed bucket URL)
6. Someone (probably owner) opens `/receipt.html?id={receipt_id}`:
   - frontend calls `GET /api/receipts/{receipt_id}?limit=50&offset=0`
   - backend returns receipt rows.

---

## Data model

### Table: `images` (current)
| column | type | notes |
|---|---|---|
| `image_id` | TEXT (PK) | public ID used in the image URL |
| `receipt_id` | TEXT (UNIQUE) | private ID used for receipts dashboard |
| `content_type` | TEXT | `image/png`, `image/jpeg`, etc |
| `byte_size` | INTEGER | enforce upload limits |
| `created_at` | TIMESTAMP | server time |
| `uploader_ip` | TEXT | ip address of uploader |
| `filename` | TEXT | original filename |
| `image_data` | TEXT | base64-encoded image bytes (MVP only) |

### Table: `receipts` (current)
| column | type | notes |
|---|---|---|
| `log_id` | TEXT (PK) | random ID |
| `image_id` | TEXT (FK → images.image_id) | which image was accessed |
| `created_at` | TIMESTAMP | access timestamp |
| `ip` | TEXT | raw IP |
| `user_agent` | TEXT | raw UA string (store capped length) |
| `referrer` | TEXT | may be empty |

---

## API design (MVP)

### Upload (current API)
- `POST /api/images`
  - Body: `multipart/form-data` with `file`
  - Validations:
    - allowlist `png/jpg/jpeg/webp/gif`
    - size limit (10 MB)
  - Returns:
    ```json
    {
      "imageId": "abc123...",
      "receiptId": "rct_456...",
      "imageUrl": "https://readnweep.com/image/abc123.jpg",
      "receiptUrl": "https://readnweep.com/receipt.html?id=rct_456"
    }
    ```

### Serve image (public)
- `GET /image/{image_id}.{ext}`
  - Behavior:
    - log receipt event (best effort)
    - then serve image bytes directly from D1

### Receipts dashboard (current API)
- `GET /api/receipts/{receipt_id}?limit=50&offset=0`
  - Returns:
    ```json
    {
      "imageId": "abc123...",
      "uploaderIp": "123.123.123.123",
      "events": [
        {
          "timestamp": "2026-02-14T20:15:01Z",
          "ip": "203.0.113.123",
          "referrer": "https://discord.com/...",
          "userAgent": " ... ",
          ... <anyting else useful>
        },
        ...
      ]
    }
    ```
- Errors:
  - `404` if receipt_id not found.

---

## Backend internals (current)

### Receipt logging details
On `GET /image/{image_id}` capture:
- timestamp (server)
- user-agent header (cap length; store raw + parsed fields)
- referrer header if present
- IP
- anything other of value

> Treat all headers as untrusted input. Use prepared statements and sanitize/cap sizes.

### Pyodide/JS interop notes
See `pyodide-notes.md` for edge cases encountered in upload/response handling.

