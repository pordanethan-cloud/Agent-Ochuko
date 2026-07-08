import sys
import os
import json
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from app.services.supabase_admin import get_supabase_admin

def main():
    db = get_supabase_admin()
    
    print("Searching admin_settings...")
    try:
        res = db.table("admin_settings").select("*").execute()
        for row in res.data:
            row_str = json.dumps(row)
            if "vertex" in row_str.lower():
                print("Found in admin_settings:", row)
    except Exception as e:
        print("Error checking admin_settings:", e)

    print("Searching profiles...")
    try:
        res = db.table("profiles").select("*").execute()
        for row in res.data:
            row_str = json.dumps(row)
            if "vertex" in row_str.lower():
                print("Found in profiles:", row)
    except Exception as e:
        print("Error checking profiles:", e)

if __name__ == "__main__":
    main()
