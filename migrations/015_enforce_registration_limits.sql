-- Migration 015 — Enforce Registration limits
-- Updates handle_new_user() trigger function to respect 'registration_open' and 'registration_limit' settings.
-- Run this script in the Supabase SQL Editor to activate limits on the OAuth/signup level.

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_limit INT;
  v_open BOOLEAN;
  v_count INT;
BEGIN
  -- 1. Fetch 'registration_open' setting (default: true if missing)
  SELECT COALESCE((value#>>'{}')::BOOLEAN, true) INTO v_open 
  FROM admin_settings 
  WHERE key = 'registration_open';
  
  IF v_open IS NULL THEN
    v_open := true;
  END IF;

  -- 2. Enforce registration status
  IF NOT v_open THEN
    RAISE EXCEPTION 'Registration is currently closed. New signups are not allowed.';
  END IF;

  -- 3. Fetch 'registration_limit' setting (default: 100 if missing)
  SELECT COALESCE((value#>>'{}')::INT, 100) INTO v_limit 
  FROM admin_settings 
  WHERE key = 'registration_limit';
  
  IF v_limit IS NULL THEN
    v_limit := 100;
  END IF;

  -- 4. Enforce registration cap
  SELECT COUNT(*) INTO v_count FROM profiles;
  IF v_count >= v_limit THEN
    RAISE EXCEPTION 'Registration limit reached (% max users). Signups are capped.', v_limit;
  END IF;

  -- 5. Insert profile
  INSERT INTO profiles (id, display_name, avatar_url, google_sub)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_user_meta_data->>'provider_id'
  );
  
  RETURN NEW;
END;
$$;
