-- 028_user_settings_table.sql
-- Migration for User Settings (cross-device PIN hash, preferences)

CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id    TEXT PRIMARY KEY,
  pin_hash   TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
      AND tablename = 'user_settings' 
      AND policyname = 'own_settings'
  ) THEN
    CREATE POLICY "own_settings"
      ON public.user_settings FOR ALL
      USING (auth.uid()::text = user_id)
      WITH CHECK (auth.uid()::text = user_id);
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.update_user_settings_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_user_settings_updated ON public.user_settings;
CREATE TRIGGER set_user_settings_updated
  BEFORE UPDATE ON public.user_settings
  FOR EACH ROW EXECUTE PROCEDURE public.update_user_settings_timestamp();
