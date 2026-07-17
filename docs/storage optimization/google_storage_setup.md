# Google Drive Sandbox Storage: Step-by-Step Setup Guide

This guide details the implementation steps for configuring Google Drive storage for the sandbox environment and segregating user data files from execution scripts.

---

## Phase 1: Google Cloud Console Setup

1. **Create a Google Cloud Project:**
   * Go to the [Google Cloud Console](https://console.cloud.google.com/).
   * Create a new project named `Agent-Ochuko`.

2. **Enable the Google Drive API:**
   * Navigate to **APIs & Services > Library**.
   * Search for **Google Drive API** and click **Enable**.

3. **Configure the OAuth Consent Screen:**
   * Go to **APIs & Services > OAuth consent screen**.
   * Select **External** (or Internal if restricted to your organization) and click **Create**.
   * Add App Information (Name, developer email).
   * **Scopes:** Add the scope `https://www.googleapis.com/auth/drive.file`.
     > [!TIP]
     > The `drive.file` scope is highly recommended. It grants Ochuko access **only** to files that the application itself creates or that the user explicitly opens with the application. It does not expose the user's entire Google Drive.

4. **Create OAuth Client Credentials:**
   * Go to **APIs & Services > Credentials**.
   * Click **Create Credentials > OAuth client ID**.
   * Select **Web application**.
   * Add your Supabase auth redirect URL under **Authorized redirect URIs**:
     `https://<your-supabase-project>.supabase.co/auth/v1/callback`
   * Click **Create** and copy the Client ID and Client Secret.

---

## Phase 2: Supabase OAuth Configuration

1. **Configure Google Provider in Supabase:**
   * Go to the **Supabase Dashboard > Authentication > Providers > Google**.
   * Paste the **Client ID** and **Client Secret** copied from the Google Cloud Console.
   * Save the changes.

2. **Frontend Authentication Call (Requesting Scopes):**
   * Update the frontend login function (e.g., in React login screen) to request offline access and the required drive scope:
     ```typescript
     const loginWithGoogle = async () => {
       const { data, error } = await supabase.auth.signInWithOAuth({
         provider: 'google',
         options: {
           redirectTo: window.location.origin,
           queryParams: {
             access_type: 'offline', // Ensures we get a refresh token
             prompt: 'consent',     // Forces approval screen to grant refresh token
           },
           scopes: 'https://www.googleapis.com/auth/drive.file'
         }
       });
     };
     ```

---

## Phase 3: Supabase Database Trigger (Credentials Sync)

Supabase handles OAuth logins, but the backend API needs the user's `refresh_token` to make background calls. We will store these tokens in a secure table.

1. **Create Table `user_google_credentials`:**
   ```sql
   create table public.user_google_credentials (
     user_id uuid references auth.users(id) on delete cascade primary key,
     refresh_token text not null,
     access_token text,
     expires_at timestamp with time zone,
     updated_at timestamp with time zone default now()
   );

   -- Enable Row Level Security (RLS)
   alter table public.user_google_credentials enable row level security;
   ```

2. **Create Trigger to Capture Provider Tokens:**
   Whenever a user logs in, Supabase inserts/updates the provider tokens in the `auth.identities` table. We copy the refresh token to our secure table:
   ```sql
   create or replace function public.sync_google_provider_tokens()
   returns trigger as $$
   begin
     if new.provider = 'google' then
       insert into public.user_google_credentials (user_id, refresh_token, updated_at)
       values (
         new.user_id,
         new.identity_data->>'refresh_token',
         now()
       )
       on conflict (user_id) do update set
         refresh_token = excluded.refresh_token,
         updated_at = now();
     end if;
     return new;
   end;
   $$ language plpgsql security definer;

   create trigger on_google_auth_sync
     after insert or update on auth.identities
     for each row execute function public.sync_google_provider_tokens();
   ```

---

## Phase 4: Backend Implementation

### 1. File & Script Separation in `code_sandbox.py`

Modify [code_sandbox.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/services/code_sandbox.py) to segregate directories:

```python
# Create segregated directories inside workspace
work_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}"))
src_dir = os.path.join(work_dir, "src")
data_dir = os.path.join(work_dir, "data")

os.makedirs(src_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True)

# 1. Mount user files strictly under data_dir
await download_google_drive_files(user_id, conversation_id, data_dir)

# 2. Write and execute the script inside src_dir
script_path = os.path.join(src_dir, "script.py")
with open(script_path, "w", encoding="utf-8") as f:
    f.write(code)

proc = await asyncio.create_subprocess_exec(
    sys.executable, script_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env,
    cwd=src_dir # Run inside /src/
)
# Wait for execution ...

# 3. Only sync/upload files located under data_dir
await upload_to_google_drive(user_id, conversation_id, data_dir)
```

### 2. Google Drive Client Wrapper (`google_drive.py`)

Create a utility service to fetch files and upload results using the `google-api-python-client` package:

```python
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

def get_drive_client(user_id: str):
    # 1. Fetch encrypted refresh_token from public.user_google_credentials
    # 2. Build Credentials object:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
    )
    return build('drive', 'v3', credentials=creds)

async def download_google_drive_files(user_id: str, conversation_id: str, local_data_dir: str):
    drive = get_drive_client(user_id)
    # Search for files under "Ochuko Sandbox" folder and download them
    ...

async def upload_to_google_drive(user_id: str, conversation_id: str, local_data_dir: str):
    drive = get_drive_client(user_id)
    # Find/Create "Ochuko Sandbox" folder
    # Upload new/modified files from local_data_dir
    ...
```

---

## Phase 5: Model Prompt Configuration

Ensure that the AI model routes the execution files correctly. Append the following instructions to the agent's system prompt (or capability register config):

```markdown
### Code Sandbox Execution Rules:
- The environment is structured with two separate directories:
  1. `./src/` (Where your scripts are saved and executed).
  2. `./data/` (Where all user data files are stored, and where you must save outputs).
- Reading Files: If you need to read a file, read it from `../data/filename.ext`.
- Writing Files: Save all generated files (plots, tables, exports) under `../data/filename.ext`.
- Do not attempt to read or write to root (`./`) or `/workspace/`. Use the relative `../data/` path.
```
