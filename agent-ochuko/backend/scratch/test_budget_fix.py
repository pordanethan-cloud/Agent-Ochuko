import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from app.services.admin_service import set_user_budget
from app.services.supabase_admin import get_supabase_admin

def main():
    user_id = "dac9567e-d42b-4c84-883e-57fb0f189829"
    test_limit = 250000
    
    print(f"Attempting to set budget for user {user_id} to {test_limit} using set_user_budget...")
    try:
        set_user_budget(user_id, test_limit)
        print("Success! Checking database record...")
        db = get_supabase_admin()
        res = db.table("token_budgets").select("*").eq("user_id", user_id).order("period", desc=True).limit(1).execute()
        print("Updated record from DB:", res.data)
        assert res.data[0]["budget_limit"] == test_limit, "Budget limit mismatch!"
        print("Verification passed successfully!")
    except Exception as e:
        print("Verification failed with error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
