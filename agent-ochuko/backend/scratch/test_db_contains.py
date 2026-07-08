import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from app.services.supabase_admin import get_supabase_admin

def main():
    db = get_supabase_admin()
    job_id = "00000000-0000-0000-0000-000000000000"
    
    print("Testing contains filter on messages table...")
    try:
        res = (
            db.table("messages")
            .select("id, content_parts")
            .contains("content_parts", {"image_jobs": [{"job_id": job_id}]})
            .execute()
        )
        print("Success! Queries executed, results:", res.data)
    except Exception as e:
        print("Failed with error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
