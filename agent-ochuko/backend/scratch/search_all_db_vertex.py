import sys
import os
import json
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from app.services.supabase_admin import get_supabase_admin

def check_table(db, table_name):
    print(f"Searching {table_name}...")
    try:
        res = db.table(table_name).select("*").limit(1000).execute()
        for row in res.data:
            row_str = json.dumps(row)
            if "vertex" in row_str.lower():
                print(f"Found in {table_name}:", row)
    except Exception as e:
        print(f"Error checking {table_name}:", e)

def main():
    db = get_supabase_admin()
    
    tables = [
        "admin_settings",
        "profiles",
        "conversations",
        "messages",
        "audit_log",
        "blocked_identities",
        "agent_quotas",
        "user_attributes",
        "access_policies"
    ]
    
    for t in tables:
        check_table(db, t)

if __name__ == "__main__":
    main()
