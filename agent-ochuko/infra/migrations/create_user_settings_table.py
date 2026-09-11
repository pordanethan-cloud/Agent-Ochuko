"""
Run once: creates the user_settings table in Supabase.
Usage: python create_user_settings_table.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../backend/.env'))

from supabase import create_client

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
sb  = create_client(url, key)

sql = """
create table if not exists public.user_settings (
  user_id   text primary key,
  pin_hash  text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_settings enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies 
    where schemaname = 'public' 
      and tablename = 'user_settings' 
      and policyname = 'own_settings'
  ) then
    create policy "own_settings"
      on public.user_settings for all
      using  (auth.uid()::text = user_id)
      with check (auth.uid()::text = user_id);
  end if;
end
$$;

create or replace function public.update_user_settings_timestamp()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

drop trigger if exists set_user_settings_updated on public.user_settings;
create trigger set_user_settings_updated
  before update on public.user_settings
  for each row execute procedure public.update_user_settings_timestamp();
"""

result = sb.rpc("exec_sql", {"sql": sql}).execute()
print("Done:", result)
