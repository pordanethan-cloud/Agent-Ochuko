-- scripts/023_google_credentials_table.sql
-- Creates the user_google_credentials table and sync trigger to store OAuth refresh tokens.

create table if not exists public.user_google_credentials (
  user_id uuid references auth.users(id) on delete cascade primary key,
  refresh_token text not null,
  access_token text,
  expires_at timestamp with time zone,
  updated_at timestamp with time zone default now()
);

-- Enable Row Level Security (RLS)
alter table public.user_google_credentials enable row level security;

-- Create Trigger to Capture Provider Tokens from auth.identities
create or replace function public.sync_google_provider_tokens()
returns trigger as $$
declare
  ref_token text;
begin
  if new.provider = 'google' then
    ref_token := new.identity_data->>'refresh_token';
    if ref_token is not null and ref_token <> '' then
      insert into public.user_google_credentials (user_id, refresh_token, updated_at)
      values (
        new.user_id,
        ref_token,
        now()
      )
      on conflict (user_id) do update set
        refresh_token = excluded.refresh_token,
        updated_at = now();
    end if;
  end if;
  return new;
end;
$$ language plpgsql security definer;

-- Drop if exists and recreate trigger
drop trigger if exists on_google_auth_sync on auth.identities;

create trigger on_google_auth_sync
  after insert or update on auth.identities
  for each row execute function public.sync_google_provider_tokens();
