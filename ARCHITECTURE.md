# Read it and Weep — Architecture (Current MVP)

> **Purpose (Easy to generate read receipts, great for marketing or even just to see if your friend has seen your message, or to see who has viewed your page etc, for ex. you could put it on your github readme and see where people in the world viewed your profile):** A web app where someone uploads an image and receives:
> - a **public image URL** they can share, and
> - a **private receipt URL** that shows access events (timestamps + basic client metadata).

---

## Product surface

### Pages (current)
- `/` (served from static assets)
  - Minimal upload form.
  - After upload, shows:
    - **Image URL** (public)
    - **Receipt URL** (private “dashboard” link)
- `/image/{image_id}`
  - Serves the image bytes (stored in D1 for now).
  - Each access generates a receipt event.
- `/receipt.html?id={receipt_id}`
  - Basic receipt dashboard:
    - Table of events: timestamp, IP, user-agent, referrer.
    - Supports pagination via `limit` + `offset` query params in the API.

### No-accounts MVP (low friction)
- No user system required.
- “Private” access is handled via **unguessable IDs**:
  - `image_id`: public identifier for the image and receipt.

> You *can* add users later for “my uploads” and access control, but the MVP works without it.

---

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
5. Anyone opens `GET /image/{image_id}`:
   - backend logs an event to `receipts`
   - backend serves image (or redirects to signed bucket URL)
6. Someone (probably owner) opens `/receipt/{receipt_id}`:
   - frontend calls `GET /api/receipts/{receipt_id}?page=...`
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

### Upload
- `POST /api/images`
  - Body: `multipart/form-data` with `file`
  - Validations:
    - content-type must be `image/*`
    - size limit (e.g., 10 MB)
  - Returns:
    ```json
    {
      "imageId": "abc123...",
      "receiptId": "rct_456...",
      "imageUrl": "https://readnweep.com/image/abc123",
      "receiptUrl": "https://readnweep.com/receipt/rct_456"
    }
    ```

### Serve image (public)
- `GET /image/{image_id}`
  - Behavior:
    - log receipt event (best effort)
    - then serve:
      - **Option A:** stream bytes from object storage through backend
      - **Option B (better):** redirect to a short-lived signed URL. But this might not work ???

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

### Hosted on?
- somewhere cheap / almost free for low usage
- Cloudflare Workers (Python) + D1 for persistence.
- Image bytes are stored in D1 as base64 for MVP.
- No Turnstile yet.

---

## Abuse prevention and safety controls

This app can attract spam/abuse if left open. Minimum protections:
 **Max storage policy**: TTL cleanup (e.g., delete after 7–30 days).
- **File validation**:
  - allowlist `png/jpg/webp/gif` (or fewer)
  - reject SVG (scriptable) to avoid XSS vectors
- **Receipt access secrecy**:
  - receipt_id must be long, random, non-sequential
  - do not expose receipts via image link

---

## Observability
- Structured logs (JSON): request id, image_id, status code, latency
- Metrics:
  - uploads/day
  - image requests/day
  - error rates
- Basic admin tooling:
  - a CLI script to prune old images and receipt rows
- or maybe a lot of this can be built into aws or cloudflare or whatever platform is used?




read-it-and-weep/
  ARCHITECTURE.md
  wrangler.toml                # Worker config: assets + D1 binding
  pyproject.toml               # Python worker dev deps
  src/
    worker.py                  # Single-file Python Worker
  migrations/
    0001_init.sql              # images + receipts tables
  public/
    index.html
    app.js
    receipt.html
    receipt.js
  scripts/
    smoke_test.sh


What gets deployed where

Recommended Cloudflare-native MVP deployment:

Frontend (static assets): Served from the Worker via `assets` binding

Backend (Python Worker): Cloudflare Workers (Python via Pyodide)

Database (SQL): Cloudflare D1 (SQLite-style relational)

Object storage (images): Not yet (image bytes stored in D1 for MVP)

Upload anti-spam: Not yet

Because your domain is registered on Route53, the simplest setup is Cloudflare’s Full setup:

Add your domain as a “zone” in Cloudflare.

Cloudflare gives you two nameservers.

In Route53 Registered Domains, replace your current nameservers with Cloudflare’s.
Once the nameserver change propagates, Cloudflare can manage DNS and issue HTTPS certs automatically for Pages/Workers routes (no manual cert work in normal cases).

Routing approach (simple)

Pages serves the UI on your apex domain:

https://readnweep.com/

https://readnweep.com/receipt/{receipt_id}

Worker serves API + image route on the same domain:
- `https://readnweep.com/api/*`
- `https://readnweep.com/image/*`

Storage bindings

Your Worker gets bindings configured in Wrangler:

- D1 binding for SQL queries (images + receipts tables)
- Static assets binding for `public/`

D1 migrations live in `migrations/`.
