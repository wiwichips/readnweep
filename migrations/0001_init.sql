CREATE TABLE IF NOT EXISTS images (
  image_id TEXT PRIMARY KEY,
  receipt_id TEXT UNIQUE NOT NULL,
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  uploader_ip TEXT NOT NULL,
  filename TEXT NOT NULL,
  image_data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
  log_id TEXT PRIMARY KEY,
  image_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ip TEXT NOT NULL,
  user_agent TEXT NOT NULL,
  referrer TEXT NOT NULL,
  FOREIGN KEY (image_id) REFERENCES images(image_id)
);

CREATE INDEX IF NOT EXISTS idx_receipts_image_created ON receipts (image_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_receipt ON images (receipt_id);
