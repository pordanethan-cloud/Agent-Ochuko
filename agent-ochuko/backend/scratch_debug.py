# scratch_debug.py
import sys
import os
import json
from dotenv import load_dotenv

# Add parent directory to path so app can be imported
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Load environment variables
load_dotenv()

from app.services.supabase_admin import get_supabase_admin
supabase = get_supabase_admin()

def main():
    print("Checking Supabase connection and schema state...")
    try:
        # Check profiles table
        profiles_res = supabase.table("profiles").select("*").execute()
        print(f"Profiles count: {len(profiles_res.data)}")
        if profiles_res.data:
            print("Profiles:")
            for p in profiles_res.data:
                print(f" - ID: {p.get('id')}, Role: {p.get('role')}, Display Name: {p.get('display_name')}, google_sub: {p.get('google_sub')}")
        else:
            print("No profiles found.")

        # Check admin_settings table
        settings_res = supabase.table("admin_settings").select("*").execute()
        print(f"Admin Settings count: {len(settings_res.data)}")
        for s in settings_res.data:
            print(f" - {s.get('key')}: {s.get('value')} ({s.get('description')})")

        # Check auth users
        users_res = supabase.auth.admin.list_users()
        print("Auth Users Response Type:", type(users_res))
        
        # If it is a list
        if isinstance(users_res, list):
            print(f"Auth Users count: {len(users_res)}")
            for u in users_res:
                # u is typically a User object or a dict
                if hasattr(u, 'id'):
                    print(f" - ID: {u.id}, Email: {u.email}, Created At: {u.created_at}")
                elif isinstance(u, dict):
                    print(f" - ID: {u.get('id')}, Email: {u.get('email')}, Created At: {u.get('created_at')}")
                else:
                    print(" - User object:", u)
        elif hasattr(users_res, 'users'):
            print(f"Auth Users count: {len(users_res.users)}")
            for u in users_res.users:
                print(f" - ID: {u.id}, Email: {u.email}, Created At: {u.created_at}")
        else:
            # Maybe it has .data
            data = getattr(users_res, 'data', None)
            if data:
                print(f"Auth Users count: {len(data)}")
                for u in data:
                    print(" - User:", u)
            else:
                print("Unknown users response structure:", users_res)

        # Check trigger_logs table
        try:
            logs_res = supabase.table("trigger_logs").select("*").order("created_at", desc=True).execute()
            print(f"Trigger Logs count: {len(logs_res.data)}")
            if logs_res.data:
                print("Trigger Logs:")
                for log in logs_res.data:
                    print(f" - [{log.get('created_at')}] {log.get('error_message')}")
            else:
                print("No trigger logs found.")
        except Exception as log_err:
            print(f"Failed to query trigger_logs (maybe table doesn't exist yet): {log_err}")

    except Exception as e:
        print(f"Error checking Supabase: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
