-- Migration 005 — Additional Admin Settings Seed Data
-- Seeds default parameters for max file uploads and monthly agent limits.

INSERT INTO admin_settings (key, value, description) VALUES
  ('max_file_size_mb',       '10',   'Max file upload size in MB'),
  ('max_ocr_pages_per_user', '50',   'Max OCR pages per user per month'),
  ('max_vision_calls',       '5000', 'Max vision calls per user per month'),
  ('max_speech_seconds',     '3600', 'Max speech seconds per user per month'),
  ('max_image_gen',          '100',  'Max image generations per user per month')
ON CONFLICT (key) DO NOTHING;
