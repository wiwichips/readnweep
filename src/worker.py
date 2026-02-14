import base64
import json
import secrets
import hashlib
from urllib.parse import urlparse

from js import Uint8Array
from workers import Response, WorkerEntrypoint

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

STORE = {
    "meta": {},
    "data": {},
    "receipt_to_image": {},
    "events": {},
}


def _random_id(bytes_len: int = 12) -> str:
    return secrets.token_hex(bytes_len)


def _get_client_ip(request) -> str:
    headers = request.headers
    return (
        headers.get("cf-connecting-ip")
        or headers.get("x-forwarded-for")
        or headers.get("x-real-ip")
        or "unknown"
    )


def _json(payload, status: int = 200) -> Response:
    return Response(
        json.dumps(payload, indent=2),
        status=status,
        headers={"content-type": "application/json"},
    )


def _debug_enabled(request):
    return (request.headers.get("x-debug") == "1") or ("debug=1" in request.url)


def _log_bytes(label, data_bytes):
    if data_bytes is None:
        print(f"[debug] {label}: <none>")
        return
    head = data_bytes[:16]
    tail = data_bytes[-16:] if len(data_bytes) >= 16 else data_bytes
    sha = hashlib.sha256(data_bytes).hexdigest()
    print(
        f"[debug] {label}: size={len(data_bytes)} sha256={sha} head={head.hex()} tail={tail.hex()}"
    )


def _detect_image_type(data_bytes):
    if not data_bytes or len(data_bytes) < 12:
        return None
    if data_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data_bytes.startswith(b"GIF87a") or data_bytes.startswith(b"GIF89a"):
        return "image/gif"
    # WEBP: RIFF....WEBP
    if data_bytes.startswith(b"RIFF") and data_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _ext_from_type(content_type):
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(content_type, "bin")


def _coerce_bytes(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("latin1")
    if hasattr(value, "to_py"):
        try:
            py_value = value.to_py()
            if isinstance(py_value, (bytes, bytearray, memoryview)):
                return bytes(py_value)
            if isinstance(py_value, str):
                return py_value.encode("latin1")
            if isinstance(py_value, (list, tuple)):
                return bytes(py_value)
        except Exception:
            pass
    try:
        if hasattr(value, "buffer") and hasattr(value, "byteOffset") and hasattr(value, "byteLength"):
            return bytes(Uint8Array.new(value.buffer, value.byteOffset, value.byteLength))
    except Exception:
        pass
    try:
        if hasattr(value, "buffer"):
            return bytes(Uint8Array.new(value.buffer))
    except Exception:
        pass
    try:
        if hasattr(value, "byteLength"):
            return bytes(Uint8Array.new(value))
    except Exception:
        pass
    try:
        return bytes(value)
    except Exception:
        return None


async def _store_put_image(env, image_id, receipt_id, meta, data_bytes):
    db = getattr(env, "DB", None)
    if db is not None:
        encoded = base64.b64encode(data_bytes).decode("ascii")
        await db.prepare(
            """
            INSERT INTO images (
              image_id, receipt_id, content_type, byte_size, created_at,
              uploader_ip, filename, image_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        ).bind(
            meta["imageId"],
            meta["receiptId"],
            meta["contentType"],
            meta["byteSize"],
            meta["createdAt"],
            meta["uploaderIp"],
            meta["filename"],
            encoded,
        ).run()
        return

    store = getattr(env, "STORE", None)
    if store is not None:
        await store.put(f"img:{image_id}", json.dumps(meta))
        await store.put(
            f"imgdata:{image_id}",
            base64.b64encode(data_bytes).decode("ascii"),
        )
        await store.put(f"rct:{receipt_id}", image_id)
        return

    STORE["meta"][image_id] = meta
    STORE["data"][image_id] = data_bytes
    STORE["receipt_to_image"][receipt_id] = image_id


async def _store_get_image_meta(env, image_id):
    db = getattr(env, "DB", None)
    if db is not None:
        result = await db.prepare(
            """
            SELECT image_id, receipt_id, content_type, byte_size, created_at,
                   uploader_ip, filename
            FROM images WHERE image_id = ?
            """
        ).bind(image_id).run()
        row = _first_row(result)
        if not row:
            return None
        return {
            "imageId": row.get("image_id"),
            "receiptId": row.get("receipt_id"),
            "contentType": row.get("content_type"),
            "byteSize": row.get("byte_size"),
            "createdAt": row.get("created_at"),
            "uploaderIp": row.get("uploader_ip"),
            "filename": row.get("filename"),
        }

    store = getattr(env, "STORE", None)
    if store is not None:
        raw = await store.get(f"img:{image_id}")
        return json.loads(raw) if raw else None

    return STORE["meta"].get(image_id)


async def _store_get_image_bytes(env, image_id):
    db = getattr(env, "DB", None)
    if db is not None:
        result = await db.prepare(
            """SELECT image_data FROM images WHERE image_id = ?"""
        ).bind(image_id).run()
        row = _first_row(result)
        if not row:
            return None
        raw = row.get("image_data")
        return base64.b64decode(raw) if raw else None

    store = getattr(env, "STORE", None)
    if store is not None:
        raw = await store.get(f"imgdata:{image_id}")
        return base64.b64decode(raw) if raw else None

    return STORE["data"].get(image_id)


async def _store_get_image_id_by_receipt(env, receipt_id):
    db = getattr(env, "DB", None)
    if db is not None:
        result = await db.prepare(
            """SELECT image_id FROM images WHERE receipt_id = ?"""
        ).bind(receipt_id).run()
        row = _first_row(result)
        return row.get("image_id") if row else None

    store = getattr(env, "STORE", None)
    if store is not None:
        return await store.get(f"rct:{receipt_id}")

    return STORE["receipt_to_image"].get(receipt_id)


async def _store_get_events(env, image_id, limit=50, offset=0):
    db = getattr(env, "DB", None)
    if db is not None:
        result = await db.prepare(
            """
            SELECT created_at, ip, user_agent, referrer
            FROM receipts
            WHERE image_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
        ).bind(image_id, limit, offset).run()
        rows = _rows(result)
        return [
            _row_to_event(row)
            for row in rows
            if _row_to_event(row) is not None
        ]

    store = getattr(env, "STORE", None)
    if store is not None:
        raw = await store.get(f"events:{image_id}")
        return json.loads(raw) if raw else []

    return STORE["events"].get(image_id, [])


async def _store_append_event(env, image_id, event):
    db = getattr(env, "DB", None)
    if db is not None:
        await db.prepare(
            """
            INSERT INTO receipts (log_id, image_id, created_at, ip, user_agent, referrer)
            VALUES (?, ?, ?, ?, ?, ?)
            """
        ).bind(
            _random_id(),
            image_id,
            event["timestamp"],
            event["ip"],
            event["userAgent"],
            event["referrer"],
        ).run()
        return

    store = getattr(env, "STORE", None)
    if store is not None:
        events = await _store_get_events(env, image_id)
        events.insert(0, event)
        await store.put(f"events:{image_id}", json.dumps(events))
        return

    events = STORE["events"].setdefault(image_id, [])
    events.insert(0, event)


def _rows(result):
    try:
        return result.results
    except Exception:
        if isinstance(result, dict):
            return result.get("results", [])
        return []


def _first_row(result):
    rows = _rows(result)
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return row
    try:
        return row.to_py()
    except Exception:
        pass
    try:
        return dict(row)
    except Exception:
        return None


def _row_to_event(row):
    if row is None:
        return None
    if not isinstance(row, dict):
        try:
            row = row.to_py()
        except Exception:
            try:
                row = dict(row)
            except Exception:
                return None
    return {
        "timestamp": row.get("created_at"),
        "ip": row.get("ip"),
        "userAgent": row.get("user_agent"),
        "referrer": row.get("referrer"),
    }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)
        path = url.path
        method = request.method.upper()

        if path == "/api/images" and method == "POST":
            return await self._handle_upload(request)

        if path.startswith("/image/"):
            segment = path.split("/")[2] if len(path.split("/")) > 2 else ""
            if "." in segment:
                image_id = segment.split(".", 1)[0]
            else:
                image_id = segment
            if not image_id:
                return Response("Not found", status=404)
            return await self._handle_image(request, image_id)

        if path.startswith("/api/receipts/"):
            receipt_id = path.split("/")[3] if len(path.split("/")) > 3 else ""
            if not receipt_id:
                return _json({"error": "Missing receipt id"}, status=400)
            return await self._handle_receipt(request, receipt_id)

        assets = getattr(self.env, "ASSETS", None)
        if assets is not None:
            if path == "/":
                return await assets.fetch(f"{url.scheme}://{url.netloc}/index.html")
            if path == "/receipt":
                return await assets.fetch(f"{url.scheme}://{url.netloc}/receipt.html")
            return await assets.fetch(request)

        return Response("Not found", status=404)

    async def _handle_upload(self, request):
        content_type = request.headers.get("content-type") or ""
        if "multipart/form-data" not in content_type:
            return _json({"error": "Expected multipart/form-data"}, status=400)

        form = await request.form_data()
        file = None
        if form is not None:
            try:
                file = form.get("file")
            except Exception:
                file = None
            if file is None:
                try:
                    for key, value in form:
                        if key == "file":
                            file = value
                            break
                except Exception:
                    pass

        if not file:
            debug = {
                "form_type": type(form).__name__ if form is not None else None,
            }
            try:
                debug["keys"] = list(form.keys())  # type: ignore[attr-defined]
            except Exception:
                debug["keys"] = None
            return _json({"error": "Missing file", "debug": debug}, status=400)

        file_type = getattr(file, "type", "") or ""
        file_size = int(getattr(file, "size", 0) or 0)
        file_name = getattr(file, "name", "") or ""

        # Some runtimes do not populate file.type; fall back to extension.
        ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        if not file_type and ext in {"png", "jpg", "jpeg", "webp", "gif"}:
            if ext == "jpg":
                ext = "jpeg"
            file_type = f"image/{ext}"

        if file_size > MAX_IMAGE_BYTES:
            return _json({"error": "File too large"}, status=400)

        data_bytes = None
        debug_payload = {
            "file_class": type(file).__name__,
            "has_arrayBuffer": hasattr(file, "arrayBuffer"),
            "has_array_buffer": hasattr(file, "array_buffer"),
            "has_bytes": hasattr(file, "bytes"),
            "has_text": hasattr(file, "text"),
            "file_type": file_type,
            "file_name": file_name,
            "file_size": file_size,
        }

        if hasattr(file, "arrayBuffer"):
            try:
                array_buffer = await file.arrayBuffer()
                data_bytes = _coerce_bytes(array_buffer)
            except Exception:
                pass
        if data_bytes is None and hasattr(file, "array_buffer"):
            try:
                array_buffer = await file.array_buffer()
                data_bytes = _coerce_bytes(array_buffer)
            except Exception:
                pass
        if data_bytes is None and hasattr(file, "bytes"):
            try:
                data_bytes = _coerce_bytes(await file.bytes())
            except Exception:
                pass
        if data_bytes is None:
            data_bytes = _coerce_bytes(file)

        if data_bytes is None:
            return _json({"error": "Unsupported upload payload", "debug": debug_payload}, status=400)

        detected_type = _detect_image_type(data_bytes)
        if detected_type and detected_type != file_type:
            file_type = detected_type

        if file_type not in ALLOWED_TYPES:
            return _json(
                {
                    "error": "Unsupported file type",
                    "debug": {
                        "file_type": file_type,
                        "file_name": file_name,
                        "file_class": type(file).__name__,
                        "detected_type": detected_type,
                    },
                },
                status=400,
            )

        file_size = len(data_bytes)
        if _debug_enabled(request):
            _log_bytes("upload.decoded", data_bytes)
            print(
                f"[debug] upload.meta: file_type={file_type} detected_type={detected_type} name={file_name}"
            )

        image_id = _random_id()
        receipt_id = f"rct_{_random_id()}"

        meta = {
            "imageId": image_id,
            "receiptId": receipt_id,
            "contentType": file_type,
            "byteSize": file_size,
            "createdAt": self._iso_now(),
            "uploaderIp": _get_client_ip(request),
            "filename": getattr(file, "name", "upload") or "upload",
        }

        try:
            await _store_put_image(self.env, image_id, receipt_id, meta, data_bytes)
        except Exception as exc:
            err = _db_error_response(exc, "upload")
            if err is not None:
                return err
            raise

        base_url = f"{urlparse(request.url).scheme}://{urlparse(request.url).netloc}"
        ext = _ext_from_type(file_type)
        payload = {
            "imageId": image_id,
            "receiptId": receipt_id,
            "imageUrl": f"{base_url}/image/{image_id}.{ext}",
            "receiptUrl": f"{base_url}/receipt.html?id={receipt_id}",
        }
        if _debug_enabled(request):
            payload["debug"] = {
                "sha256": hashlib.sha256(data_bytes).hexdigest(),
                "size": len(data_bytes),
                "detectedType": detected_type,
                "contentType": file_type,
            }
        return _json(payload)

    async def _handle_image(self, request, image_id):
        try:
            meta = await _store_get_image_meta(self.env, image_id)
        except Exception as exc:
            err = _db_error_response(exc, "image")
            if err is not None:
                return err
            raise
        if not meta:
            return Response("Not found", status=404)

        event = {
            "timestamp": self._iso_now(),
            "ip": _get_client_ip(request),
            "userAgent": request.headers.get("user-agent") or "",
            "referrer": request.headers.get("referer") or "",
        }

        try:
            await _store_append_event(self.env, image_id, event)
        except Exception:
            pass

        try:
            data_bytes = await _store_get_image_bytes(self.env, image_id)
        except Exception as exc:
            err = _db_error_response(exc, "image")
            if err is not None:
                return err
            raise
        if not data_bytes:
            return Response("Not found", status=404)

        debug_headers = {}
        if _debug_enabled(request):
            _log_bytes("image.response", data_bytes)
            print(f"[debug] image.content_type: {meta.get('contentType')}")
            debug_headers["x-debug-sha256"] = hashlib.sha256(data_bytes).hexdigest()
            debug_headers["x-debug-size"] = str(len(data_bytes))

        try:
            body = Uint8Array.new(data_bytes)
        except Exception:
            body = data_bytes

        return Response(
            body,
            headers={
                "content-type": meta.get("contentType", "application/octet-stream"),
                "content-length": str(len(data_bytes)),
                "content-disposition": f'inline; filename="{meta.get("filename", image_id)}"',
                "cache-control": "public, max-age=3600",
                **debug_headers,
            },
        )

    async def _handle_receipt(self, request, receipt_id):
        try:
            image_id = await _store_get_image_id_by_receipt(self.env, receipt_id)
        except Exception as exc:
            err = _db_error_response(exc, "receipt")
            if err is not None:
                return err
            raise
        if not image_id:
            return _json({"error": "Receipt not found"}, status=404)

        try:
            meta = await _store_get_image_meta(self.env, image_id)
        except Exception as exc:
            err = _db_error_response(exc, "receipt")
            if err is not None:
                return err
            raise
        limit, offset = self._receipt_paging(request)
        try:
            events = await _store_get_events(self.env, image_id, limit=limit, offset=offset)
        except Exception as exc:
            err = _db_error_response(exc, "receipt")
            if err is not None:
                return err
            raise

        return _json(
            {
                "imageId": image_id,
                "receiptId": receipt_id,
                "uploaderIp": meta.get("uploaderIp") if meta else "unknown",
                "events": events,
            }
        )

    @staticmethod
    def _iso_now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _receipt_paging(request):
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(request.url)
        params = parse_qs(parsed.query)
        limit = params.get("limit", ["50"])[0]
        offset = params.get("offset", ["0"])[0]
        try:
            limit = max(1, min(200, int(limit)))
        except Exception:
            limit = 50
        try:
            offset = max(0, int(offset))
        except Exception:
            offset = 0
        return limit, offset


def _db_error_response(exc, action):
    msg = str(exc)
    if "no such table" in msg:
        return _json(
            {
                "error": "Database not initialized.",
                "detail": "D1 tables are missing. Run migrations.",
                "hint_local": "npx wrangler d1 migrations apply readnweep-db --local",
                "hint_remote": "npx wrangler d1 migrations apply readnweep-db",
                "context": action,
            },
            status=503,
        )
    return None
