# Pyodide / JS Interop Notes (Readnweep)

## File uploads (FormData -> Python)
- `request.form_data()` returns a JS-backed FormData proxy, not a native Python dict.
- Avoid `if form` checks; some proxies don’t implement `__len__` and will throw.
- Retrieving the file may require `.get("file")` or iterating `(key, value)` pairs.

## File byte conversion pitfalls
- The uploaded `File` object may expose:
  - `arrayBuffer()` (JS)
  - `array_buffer()` (snake_case variant)
  - `bytes()` (pyodide file-like)
- Converting to bytes is tricky:
  - JS TypedArray views may have non-zero `byteOffset` and smaller `byteLength`.
  - Converting the entire underlying `buffer` without slicing can prepend garbage.
- Safe pattern:
  - Prefer `Uint8Array.new(value.buffer, value.byteOffset, value.byteLength)` when available.
  - Fall back to `Uint8Array.new(value)` for ArrayBuffer/TypedArray.
  - Avoid `bytes(value)` unless you’ve exhausted JS-backed paths.

## Response body serialization
- Returning raw Python `bytes` in a `Response` can corrupt certain payloads.
- Fix: wrap with `Uint8Array` before sending:
  - `Response(Uint8Array.new(data_bytes), headers=...)`

## Content type detection
- `file.type` can be empty in Python Workers; detect by magic bytes as a fallback.
- If `detected_type` differs from `file.type`, trust the detected type for headers.

## Debugging tips
- Add `x-debug: 1` or `?debug=1` to enable byte-level logging.
- Log SHA256 + head/tail bytes to identify corruption point.
