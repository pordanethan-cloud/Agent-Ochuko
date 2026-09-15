-- Migration 003 — Seed Admin User
-- Sets a specific user as superadmin. Run this AFTER signing in with Google once.
-- Replace '<YOUR_USER_UUID_HERE>' with your user UUID (found in Supabase Authentication -> Users).

UPDATE profiles
SET role = 'superadmin'
WHERE id = '<YOUR_USER_UUID_HERE>';
